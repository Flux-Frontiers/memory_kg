"""Tests for GraphStore."""

import os
import subprocess
import sys
import textwrap

from memory_kg.memorykg import DocEdge, DocNode
from memory_kg.store import GraphStore

# A hub node reachable in one hop from every seed. Which seed claims it as
# `via_seed` is decided by frontier iteration order, so this shape is what makes
# non-deterministic traversal observable.
_FAN_IN_SEEDS = 16


def _fan_in_graph():
    """Return (nodes, edges, seed_ids) where every seed reaches one shared hub."""
    seed_ids = [f"chunk:fan.md:{i:04d}" for i in range(_FAN_IN_SEEDS)]
    nodes = [
        DocNode(
            id="doc:fan.md",
            kind="document",
            name="fan",
            title="Fan",
            file_path="fan.md",
            char_start=0,
            char_end=1000,
            heading_level=None,
            text="Hub document.",
        )
    ]
    nodes += [
        DocNode(
            id=sid,
            kind="chunk",
            name=f"chunk:{i:04d}",
            title="Chunk",
            file_path="fan.md",
            char_start=i * 10,
            char_end=(i + 1) * 10,
            heading_level=None,
            text=f"Chunk {i} text.",
        )
        for i, sid in enumerate(seed_ids)
    ]
    edges = [DocEdge(src="doc:fan.md", rel="CONTAINS", dst=sid) for sid in seed_ids]
    return nodes, edges, seed_ids


def _make_nodes():
    return [
        DocNode(
            id="doc:notes.md",
            kind="document",
            name="notes",
            title="Notes",
            file_path="notes.md",
            char_start=0,
            char_end=500,
            heading_level=None,
            text="Document summary text.",
        ),
        DocNode(
            id="chunk:notes.md:0000",
            kind="chunk",
            name="chunk:0000",
            title="Introduction",
            file_path="notes.md",
            char_start=0,
            char_end=100,
            heading_level=None,
            text="This is the first chunk of text.",
        ),
        DocNode(
            id="chunk:notes.md:0001",
            kind="chunk",
            name="chunk:0001",
            title="Introduction",
            file_path="notes.md",
            char_start=100,
            char_end=200,
            heading_level=None,
            text="This is the second chunk of text.",
        ),
    ]


def _make_edges():
    return [
        DocEdge(src="doc:notes.md", rel="CONTAINS", dst="chunk:notes.md:0000"),
        DocEdge(src="doc:notes.md", rel="CONTAINS", dst="chunk:notes.md:0001"),
        DocEdge(src="chunk:notes.md:0000", rel="NEXT", dst="chunk:notes.md:0001"),
    ]


def test_store_write_and_read(tmp_path):
    db = tmp_path / "test.sqlite"
    store = GraphStore(db)
    store.write(_make_nodes(), _make_edges(), wipe=True)

    n = store.node("doc:notes.md")
    assert n is not None
    assert n["kind"] == "document"
    assert n["title"] == "Notes"
    store.close()


def test_store_stats(tmp_path):
    db = tmp_path / "test.sqlite"
    store = GraphStore(db)
    store.write(_make_nodes(), _make_edges(), wipe=True)

    s = store.stats()
    assert s["total_nodes"] == 3
    assert s["total_edges"] == 3
    assert s["node_counts"]["document"] == 1
    assert s["node_counts"]["chunk"] == 2
    store.close()


def test_store_query_nodes_by_kind(tmp_path):
    db = tmp_path / "test.sqlite"
    store = GraphStore(db)
    store.write(_make_nodes(), _make_edges(), wipe=True)

    chunks = store.query_nodes(kinds=["chunk"])
    assert len(chunks) == 2
    assert all(n["kind"] == "chunk" for n in chunks)
    store.close()


def test_store_expand(tmp_path):
    db = tmp_path / "test.sqlite"
    store = GraphStore(db)
    store.write(_make_nodes(), _make_edges(), wipe=True)

    meta = store.expand({"doc:notes.md"}, hop=1, rels=("CONTAINS",))
    assert "chunk:notes.md:0000" in meta
    assert "chunk:notes.md:0001" in meta
    store.close()


def test_store_expand_tie_break_is_lowest_seed_id(tmp_path):
    """When several seeds reach a node at the same hop, the lowest ID claims it.

    `via_seed` selects the `base_dist` that orders the node in `kg.query`, so an
    arbitrary winner reorders the result tail. Pin the rule rather than leaving
    it to set iteration order.
    """
    db = tmp_path / "fan.sqlite"
    store = GraphStore(db)
    nodes, edges, seed_ids = _fan_in_graph()
    store.write(nodes, edges, wipe=True)

    meta = store.expand(set(seed_ids), hop=1, rels=("CONTAINS",))

    assert meta["doc:fan.md"].via_seed == min(seed_ids)
    store.close()


def test_store_expand_is_stable_across_hash_seeds(tmp_path):
    """`expand` must return the same provenance in every process.

    Python randomises string hashing per process, so iterating a `set[str]`
    frontier makes retrieval irreproducible run to run — invisible in aggregate
    metrics but enough to change which node survives `max_nodes` truncation.
    """
    db = tmp_path / "fan.sqlite"
    store = GraphStore(db)
    nodes, edges, seed_ids = _fan_in_graph()
    store.write(nodes, edges, wipe=True)
    store.close()

    script = textwrap.dedent(
        f"""
        from memory_kg.store import GraphStore

        store = GraphStore({str(db)!r})
        meta = store.expand({set(seed_ids)!r}, hop=1, rels=("CONTAINS",))
        print(meta["doc:fan.md"].via_seed)
        store.close()
        """
    )

    seen = set()
    for hash_seed in ("0", "1", "2", "3", "4"):
        env = {**os.environ, "PYTHONHASHSEED": hash_seed}
        out = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            check=True,
            env=env,
        )
        seen.add(out.stdout.strip())

    assert seen == {min(seed_ids)}, f"via_seed varies by process: {sorted(seen)}"


def test_store_edges_within(tmp_path):
    db = tmp_path / "test.sqlite"
    store = GraphStore(db)
    store.write(_make_nodes(), _make_edges(), wipe=True)

    node_ids = {"doc:notes.md", "chunk:notes.md:0000", "chunk:notes.md:0001"}
    edges = store.edges_within(node_ids)
    rels = {e["rel"] for e in edges}
    assert "CONTAINS" in rels
    assert "NEXT" in rels
    store.close()


def test_store_wipe(tmp_path):
    db = tmp_path / "test.sqlite"
    store = GraphStore(db)
    store.write(_make_nodes(), _make_edges(), wipe=False)
    store.write(_make_nodes(), _make_edges(), wipe=True)
    s = store.stats()
    assert s["total_nodes"] == 3  # no duplicates after wipe
    store.close()


def test_store_context_manager(tmp_path):
    db = tmp_path / "test.sqlite"
    with GraphStore(db) as store:
        store.write(_make_nodes(), _make_edges(), wipe=True)
        assert store.stats()["total_nodes"] == 3


def test_store_write_batches_across_multiple_commits(tmp_path, monkeypatch):
    """A node/edge count larger than the batch size must still all persist."""
    monkeypatch.setattr("memory_kg.store._UPSERT_BATCH_SIZE", 2)
    db = tmp_path / "test.sqlite"
    store = GraphStore(db)

    nodes = [
        DocNode(
            id=f"doc:file{i}.md",
            kind="document",
            name=f"file{i}",
            title=f"File {i}",
            file_path=f"file{i}.md",
            char_start=0,
            char_end=10,
            heading_level=None,
            text="text",
        )
        for i in range(5)
    ]
    edges = [
        DocEdge(src=nodes[i].id, rel="REFERENCES", dst=nodes[(i + 1) % 5].id) for i in range(5)
    ]

    store.write(nodes, edges, wipe=True)
    s = store.stats()
    assert s["total_nodes"] == 5
    assert s["total_edges"] == 5
    store.close()


def test_store_write_accepts_dict_values(tmp_path, monkeypatch):
    """semantic_builder.py hands _upsert_nodes/_upsert_edges dict_values, not lists."""
    monkeypatch.setattr("memory_kg.store._UPSERT_BATCH_SIZE", 2)
    db = tmp_path / "test.sqlite"
    store = GraphStore(db)

    nodes_by_id = {n.id: n for n in _make_nodes()}
    edges_by_key = {(e.src, e.rel, e.dst): e for e in _make_edges()}

    store._upsert_nodes(nodes_by_id.values())
    store._upsert_edges(edges_by_key.values())

    s = store.stats()
    assert s["total_nodes"] == 3
    assert s["total_edges"] == 3
    store.close()
