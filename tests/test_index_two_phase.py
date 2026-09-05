"""Tests for the two-phase build: precompute_embeddings → build_from_cache.

The point of the two-phase path is that the expensive half (model inference) is
paid once into a JSONL cache and the cheap half (writing vectors) can be re-run
from it.  So the load-bearing test here is *parity*: an index built from a cache
must be indistinguishable from one built in a single pass.

Model-free throughout — the stub embedder from :mod:`tests.test_index_vectors`
keeps this runnable without downloading anything.
"""

from __future__ import annotations

import gzip
import json

import pytest

from memory_kg.index import SemanticIndex, _build_index_text
from tests.test_index_vectors import _ALL, NODES, StubEmbedder, StubStore


class QueryableStubStore(StubStore):
    """StubStore plus ``query_nodes`` — the CPU precompute path reads it."""

    def query_nodes(self, kinds=None, **_kwargs):
        return list(self._select(kinds))


@pytest.fixture
def index(tmp_path):
    return SemanticIndex(tmp_path / ".memorykg" / "vectors.sqlite", embedder=StubEmbedder())


@pytest.fixture
def store():
    return QueryableStubStore()


def _read_cache(path):
    """Return ``(meta, rows)`` from a JSONL cache, transparently un-gzipping."""
    opener = gzip.open if path.name.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]
    return lines[0]["__meta__"], lines[1:]


def _index_contents(idx):
    """Return every indexed hit as comparable tuples, ordered deterministically."""
    hits = idx.search("climate", k=_ALL)
    return sorted((h.id, h.kind, h.name, h.title, h.file_path) for h in hits)


class TestPrecompute:
    def test_writes_a_meta_header_then_one_row_per_node(self, index, store, tmp_path):
        out = index.precompute_embeddings(store, tmp_path / "e.jsonl", quiet=True)
        meta, rows = _read_cache(out)

        assert meta["version"] == 1
        assert meta["dim"] == StubEmbedder.dim
        assert len(rows) == _ALL

    def test_rows_carry_the_metadata_search_reads_back(self, index, store, tmp_path):
        _, rows = _read_cache(index.precompute_embeddings(store, tmp_path / "e.jsonl", quiet=True))
        by_id = {r["id"]: r for r in rows}

        for node in NODES:
            row = by_id[node["id"]]
            assert row["kind"] == node["kind"]
            assert row["name"] == node["name"]
            assert row["title"] == node["title"]
            assert row["file_path"] == node["file_path"]

    def test_stores_the_same_embedding_text_the_one_pass_build_uses(self, index, store, tmp_path):
        _, rows = _read_cache(index.precompute_embeddings(store, tmp_path / "e.jsonl", quiet=True))
        by_id = {r["id"]: r for r in rows}
        assert by_id[NODES[0]["id"]]["text"] == _build_index_text(NODES[0])

    def test_vectors_are_the_embedders_own_output(self, index, store, tmp_path):
        _, rows = _read_cache(index.precompute_embeddings(store, tmp_path / "e.jsonl", quiet=True))
        by_id = {r["id"]: r for r in rows}
        expected = StubEmbedder().embed_texts([_build_index_text(NODES[0])])[0]
        assert by_id[NODES[0]["id"]]["vector"] == pytest.approx(expected)

    def test_writes_nothing_to_the_vector_store(self, index, store, tmp_path):
        index.precompute_embeddings(store, tmp_path / "e.jsonl", quiet=True)
        assert index.count() == 0, "precompute is a pure embedding pass"

    def test_gzip_cache_round_trips(self, index, store, tmp_path):
        out = index.precompute_embeddings(store, tmp_path / "e.jsonl.gz", quiet=True)
        meta, rows = _read_cache(out)
        assert meta["dim"] == StubEmbedder.dim
        assert len(rows) == _ALL

    def test_rejects_a_whole_file_json_cache(self, index, store, tmp_path):
        with pytest.raises(ValueError, match=r"must be \.jsonl"):
            index.precompute_embeddings(store, tmp_path / "e.json", quiet=True)

    def test_batch_size_does_not_change_the_cache(self, tmp_path, store):
        def rows_at(batch):
            idx = SemanticIndex(tmp_path / f"b{batch}" / "v.sqlite", embedder=StubEmbedder())
            out = idx.precompute_embeddings(
                store, tmp_path / f"b{batch}.jsonl", batch_size=batch, quiet=True
            )
            return [r["id"] for r in _read_cache(out)[1]]

        assert rows_at(1) == rows_at(3) == rows_at(100)


class TestBuildFromCache:
    def test_matches_a_single_pass_build_exactly(self, tmp_path, store):
        one_pass = SemanticIndex(tmp_path / "one" / "v.sqlite", embedder=StubEmbedder())
        one_pass.build(store, wipe=True, discover_similar=False)

        two_phase = SemanticIndex(tmp_path / "two" / "v.sqlite", embedder=StubEmbedder())
        cache = two_phase.precompute_embeddings(store, tmp_path / "e.jsonl", quiet=True)
        two_phase.build_from_cache(store, cache, wipe=True, discover_similar=False, quiet=True)

        assert _index_contents(two_phase) == _index_contents(one_pass)

    def test_search_ranking_survives_the_round_trip(self, tmp_path, store):
        one_pass = SemanticIndex(tmp_path / "one" / "v.sqlite", embedder=StubEmbedder())
        one_pass.build(store, wipe=True, discover_similar=False)

        two_phase = SemanticIndex(tmp_path / "two" / "v.sqlite", embedder=StubEmbedder())
        cache = two_phase.precompute_embeddings(store, tmp_path / "e.jsonl", quiet=True)
        two_phase.build_from_cache(store, cache, wipe=True, discover_similar=False, quiet=True)

        assert [h.id for h in two_phase.search("climate", k=_ALL)] == [
            h.id for h in one_pass.search("climate", k=_ALL)
        ]

    def test_reports_the_model_and_dim_from_the_cache_header(self, index, store, tmp_path):
        cache = index.precompute_embeddings(store, tmp_path / "e.jsonl", quiet=True)
        stats = index.build_from_cache(store, cache, wipe=True, discover_similar=False, quiet=True)
        assert stats["indexed_rows"] == _ALL
        assert stats["dim"] == StubEmbedder.dim
        assert stats["vectors_path"] == str(index.vectors_path)

    def test_prefilters_still_work(self, index, store, tmp_path):
        cache = index.precompute_embeddings(store, tmp_path / "e.jsonl", quiet=True)
        index.build_from_cache(store, cache, wipe=True, discover_similar=False, quiet=True)

        hits = index.search("climate", k=_ALL, haystack_files=frozenset({"sessions/s2.md"}))
        assert [h.id for h in hits] == ["chunk:s2#1"]

    def test_rebuilding_from_the_same_instance_does_not_raise(self, index, store, tmp_path):
        """The dedup-verdict trap: the backend must be re-opened per write pass."""
        cache = index.precompute_embeddings(store, tmp_path / "e.jsonl", quiet=True)
        index.build_from_cache(store, cache, wipe=True, discover_similar=False, quiet=True)
        index.build_from_cache(store, cache, wipe=True, discover_similar=False, quiet=True)
        assert index.count() == _ALL

    def test_gzip_cache_builds(self, index, store, tmp_path):
        cache = index.precompute_embeddings(store, tmp_path / "e.jsonl.gz", quiet=True)
        index.build_from_cache(store, cache, wipe=True, discover_similar=False, quiet=True)
        assert index.count() == _ALL

    def test_batch_size_does_not_change_results(self, tmp_path, store):
        def ids_at(batch):
            idx = SemanticIndex(tmp_path / f"b{batch}" / "v.sqlite", embedder=StubEmbedder())
            cache = idx.precompute_embeddings(store, tmp_path / f"b{batch}.jsonl", quiet=True)
            idx.build_from_cache(
                store, cache, wipe=True, batch_size=batch, discover_similar=False, quiet=True
            )
            return [h.id for h in idx.search("climate", k=_ALL)]

        assert ids_at(1) == ids_at(3) == ids_at(100)

    def test_rejects_a_whole_file_json_cache(self, index, store, tmp_path):
        bogus = tmp_path / "e.json"
        bogus.write_text("{}")
        with pytest.raises(ValueError, match=r"must be \.jsonl"):
            index.build_from_cache(store, bogus, quiet=True)


class TestDeviceRouting:
    """A GPU can't fan out across spawn workers; CPU should -- if it can.

    "If it can" is the whole rule: a worker process is handed a model *name*,
    never an embedder object, so only a nameable embedder can fan out.
    """

    def test_gpu_takes_the_single_process_stream(self, index, store, tmp_path, monkeypatch):
        monkeypatch.setattr("kg_utils.embedder.resolve_device", lambda _d: "mps")
        called = {}
        monkeypatch.setattr(
            SemanticIndex,
            "_precompute_embeddings_jsonl_stream",
            lambda self, *a, **kw: called.setdefault("gpu", True),
        )
        index.precompute_embeddings(store, tmp_path / "e.jsonl", quiet=True)
        assert called == {"gpu": True}

    def test_cpu_takes_the_multi_process_stream(self, index, store, tmp_path, monkeypatch):
        monkeypatch.setattr("kg_utils.embedder.resolve_device", lambda _d: "cpu")
        # Nameable, so a worker can reload it by name.
        index.embedder.model_name = "sentence-transformers/all-MiniLM-L6-v2"
        called = {}
        monkeypatch.setattr(
            SemanticIndex,
            "_precompute_embeddings_parallel_stream",
            lambda self, *a, **kw: called.setdefault("cpu", True),
        )
        index.precompute_embeddings(store, tmp_path / "e.jsonl", quiet=True)
        assert called == {"cpu": True}

    def test_an_unnameable_embedder_stays_in_process_on_cpu(
        self, index, store, tmp_path, monkeypatch
    ):
        """Otherwise the caller's embedder is silently swapped for DEFAULT_MODEL.

        A spawn worker cannot receive the object, so the parallel path would
        reload by name -- and with no ``model_name`` to use, that name is
        DEFAULT_MODEL: a different model at a different dimension than the one
        the caller passed in, with nothing raised.
        """
        monkeypatch.setattr("kg_utils.embedder.resolve_device", lambda _d: "cpu")
        assert getattr(index.embedder, "model_name", None) is None
        called = {}
        monkeypatch.setattr(
            SemanticIndex,
            "_precompute_embeddings_jsonl_stream",
            lambda self, *a, **kw: called.setdefault("in_process", True),
        )
        index.precompute_embeddings(store, tmp_path / "e.jsonl", quiet=True)
        assert called == {"in_process": True}

    def test_the_cache_carries_the_injected_embedders_dimension_on_cpu(
        self, index, store, tmp_path, monkeypatch
    ):
        """End-to-end guard for the same thing, without mocking the write path."""
        monkeypatch.setattr("kg_utils.embedder.resolve_device", lambda _d: "cpu")
        meta, rows = _read_cache(
            index.precompute_embeddings(store, tmp_path / "e.jsonl", quiet=True)
        )
        assert meta["dim"] == StubEmbedder.dim
        assert len(rows[0]["vector"]) == StubEmbedder.dim
