"""Tests for MemoryKG.build_graph() — streams parsed nodes/edges into the store."""

from memory_kg.kg import MemoryKG
from memory_kg.memorykg import parse_corpus


def _write_corpus(root):
    for i in range(6):
        (root / f"doc{i}.md").write_text(f"# Title {i}\n\nContent about architecture design {i}.\n")


def test_build_graph_matches_direct_parse(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    _write_corpus(corpus)

    expected_nodes, expected_edges = parse_corpus(corpus)

    kg = MemoryKG(corpus_root=corpus, db_path=tmp_path / "graph.sqlite")
    stats = kg.build_graph(wipe=True)

    assert stats.total_nodes == len(expected_nodes)
    assert stats.total_edges == len(expected_edges)
    assert stats.node_counts.get("document") == 6
    kg.close()


def test_build_graph_wipe_clears_previous_build(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    _write_corpus(corpus)

    kg = MemoryKG(corpus_root=corpus, db_path=tmp_path / "graph.sqlite")
    kg.build_graph(wipe=True)
    first_total = kg.store.stats()["total_nodes"]

    # Re-running with wipe=True must not double the counts (no leftover batches
    # from the previous build merging with the new one).
    stats = kg.build_graph(wipe=True)
    assert stats.total_nodes == first_total
    kg.close()


def test_build_graph_streams_in_small_batches(tmp_path, monkeypatch):
    """Force a tiny batch size so extract_streaming actually flushes more than once."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    _write_corpus(corpus)

    flush_count = 0

    kg = MemoryKG(corpus_root=corpus, db_path=tmp_path / "graph.sqlite")
    original_write = kg.store.write

    def _counting_write(nodes, edges, *, wipe=False):
        nonlocal flush_count
        flush_count += 1
        return original_write(nodes, edges, wipe=wipe)

    monkeypatch.setattr(kg.store, "write", _counting_write)

    # Force extract_streaming's default batch_size=1 so it flushes per file.
    original_extract_streaming = kg.graph.extract_streaming

    def _small_batch_extract_streaming(on_batch, *, batch_size=5000):
        return original_extract_streaming(on_batch, batch_size=1)

    monkeypatch.setattr(kg.graph, "extract_streaming", _small_batch_extract_streaming)

    stats = kg.build_graph(wipe=True)

    assert flush_count > 1
    assert stats.total_nodes > 0
    kg.close()
