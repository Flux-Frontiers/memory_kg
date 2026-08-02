"""Tests for the sqlite-vec port of :class:`memory_kg.index.SemanticIndex`.

A deterministic stub embedder keeps the whole file model-free, so this runs
without downloading anything.

Three of these pin traps that a default-configured port walks straight into:

* ``title`` and ``file_path`` must be persisted as metadata. ``search`` reads
  both off every hit *and* filters on ``file_path``, but the backend's default
  column set carries neither — so the port would silently return blank titles
  and paths, and the haystack prefilter would reference a column that does not
  exist.
* Re-opening on each build pass. ``SqliteVecBackend`` fixes its dedup strategy
  at ``open()``; without the re-open, a second build on the same instance
  raises ``UNIQUE constraint failed: vec_meta.id``.
* Reporting on an unbuilt index must not create it — a zero-row store reads as
  "built" to every ``.exists()`` probe.
"""

from __future__ import annotations

import math
import sqlite3

import pytest
from kg_utils.embedder import Embedder

from memory_kg.index import SemanticIndex, _build_index_text, _escape


class StubEmbedder(Embedder):
    """Deterministic, model-free embedder: character codes folded into 8 dims."""

    dim = 8

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for i, ch in enumerate(text):
            v[i % self.dim] += ord(ch) % 13
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed_texts(self, texts, encode_batch_size=32):
        return [self._vec(t) for t in texts]

    def embed_query(self, query):
        return self._vec(query)


NODES = [
    {
        "id": "chunk:s1#1",
        "kind": "chunk",
        "name": "s1#1",
        "title": "Climate Policy",
        "file_path": "sessions/s1.md",
        "text": "carbon tax proposal",
    },
    {
        "id": "chunk:s2#1",
        "kind": "chunk",
        "name": "s2#1",
        "title": "Mediterranean Diet",
        "file_path": "sessions/s2.md",
        "text": "olive oil and fish",
    },
    {
        "id": "document:s1",
        "kind": "document",
        "name": "s1",
        "title": "Session One",
        "file_path": "sessions/s1.md",
        "text": "session one transcript",
    },
    {
        # A quoted id *and* a quoted path: the prefilter interpolates paths
        # into a SQL string literal, so an apostrophe must be escaped.
        "id": "entity:o'brien",
        "kind": "entity",
        "name": "O'Brien",
        "title": "",
        "file_path": "sessions/o'brien.md",
        "text": "a name with an apostrophe",
    },
]

_ALL = len(NODES)


class StubStore:
    """Minimal GraphStore stand-in — only the two methods build() calls."""

    def __init__(self, nodes=NODES):
        self._nodes = nodes

    def _select(self, kinds):
        return [n for n in self._nodes if not kinds or n["kind"] in kinds]

    def count_nodes(self, kinds=None):
        return len(self._select(kinds))

    def iter_nodes(self, kinds=None, batch_size=100):
        sel = self._select(kinds)
        for i in range(0, len(sel), batch_size):
            yield sel[i : i + batch_size]


@pytest.fixture
def index(tmp_path):
    return SemanticIndex(tmp_path / ".memorykg" / "vectors.sqlite", embedder=StubEmbedder())


@pytest.fixture
def built(index):
    index.build(StubStore(), wipe=True, batch_size=2, encode_batch_size=2, discover_similar=False)
    return index


class TestBuild:
    def test_reports_the_vector_store_path(self, index):
        stats = index.build(StubStore(), wipe=True, discover_similar=False)
        assert stats["indexed_rows"] == _ALL
        assert stats["dim"] == StubEmbedder.dim
        assert stats["vectors_path"] == str(index.vectors_path)

    def test_no_longer_reports_lancedb_keys(self, index):
        stats = index.build(StubStore(), wipe=True, discover_similar=False)
        assert "table" not in stats
        assert "lancedb_dir" not in stats

    def test_writes_a_single_sqlite_file(self, built):
        assert built.vectors_path.is_file()

    def test_batch_size_does_not_change_results(self, tmp_path):
        def ids_at(batch):
            idx = SemanticIndex(tmp_path / f"b{batch}" / "v.sqlite", embedder=StubEmbedder())
            idx.build(
                StubStore(),
                wipe=True,
                batch_size=batch,
                encode_batch_size=batch,
                discover_similar=False,
            )
            return [h.id for h in idx.search("climate", k=_ALL)]

        assert ids_at(1) == ids_at(3) == ids_at(100)


class TestSearchMetadata:
    """The blanked-output trap: `search` reads four fields off every hit."""

    def test_kind_and_name_survive(self, built):
        for hit in built.search("climate", k=_ALL):
            assert hit.kind
            assert hit.name

    def test_title_survives(self, built):
        titles = [h.title for h in built.search("climate", k=_ALL)]
        assert any(titles), "title blanked — meta_columns is missing it"

    def test_file_path_survives(self, built):
        paths = [h.file_path for h in built.search("climate", k=_ALL)]
        assert all(paths), "file_path blanked — meta_columns is missing it"

    def test_distances_are_cosine_ranged(self, built):
        """sqlite-vec reports cosine distance in [0, 2] — not squared L2."""
        assert all(0.0 <= h.distance <= 2.0 for h in built.search("climate", k=_ALL))

    def test_ranks_are_dense_and_ordered(self, built):
        hits = built.search("climate", k=_ALL)
        assert [h.rank for h in hits] == list(range(_ALL))
        assert hits == sorted(hits, key=lambda h: h.distance)

    def test_embedding_text_is_stored_verbatim(self, built):
        con = sqlite3.connect(str(built.vectors_path))
        stored = con.execute("SELECT text FROM vec_meta WHERE id = ?", (NODES[0]["id"],)).fetchone()
        con.close()
        assert stored[0] == _build_index_text(NODES[0])


class TestPrefilters:
    """`seed_kinds` and `haystack_files` compile to the backend's SQL prefilter.

    Both are load-bearing for the benchmark suites: `haystack_files` is what
    makes retrieval apples-to-apples with flat per-question search.
    """

    def test_seed_kinds_restricts_by_kind(self, built):
        hits = built.search("session", k=_ALL, seed_kinds=("document",))
        assert [h.id for h in hits] == ["document:s1"]

    def test_haystack_files_restricts_by_path(self, built):
        hits = built.search("climate", k=_ALL, haystack_files=frozenset({"sessions/s2.md"}))
        assert [h.id for h in hits] == ["chunk:s2#1"]

    def test_filters_combine(self, built):
        hits = built.search(
            "climate", k=_ALL, seed_kinds=("chunk",), haystack_files=frozenset({"sessions/s1.md"})
        )
        assert [h.id for h in hits] == ["chunk:s1#1"]

    def test_a_quoted_path_does_not_break_the_predicate(self, built):
        hits = built.search("name", k=_ALL, haystack_files=frozenset({"sessions/o'brien.md"}))
        assert [h.id for h in hits] == ["entity:o'brien"]

    def test_a_quoted_kind_does_not_break_the_predicate(self, built):
        """Kinds are interpolated the same way, so escape them too."""
        assert built.search("x", k=_ALL, seed_kinds=("no'such",)) == []

    def test_prefilter_draws_k_from_the_matching_subset(self, built):
        """A true prefilter, not a post-filter over a global top-k.

        With k=1 and a filter that excludes the global nearest neighbour, a
        post-filter would return nothing.
        """
        nearest = built.search("climate", k=1)[0]
        other = next(n for n in NODES if n["file_path"] != nearest.file_path)
        hits = built.search("climate", k=1, haystack_files=frozenset({other["file_path"]}))
        assert len(hits) == 1
        assert hits[0].file_path == other["file_path"]


class TestRebuild:
    """`SqliteVecBackend` fixes its dedup strategy at open() and never revisits it."""

    def test_incremental_build_after_a_wipe_build(self, built):
        stats = built.build(StubStore(), wipe=False, batch_size=3, discover_similar=False)
        assert stats["indexed_rows"] == _ALL
        assert built.count() == _ALL

    def test_repeated_wipe_builds(self, built):
        built.build(StubStore(), wipe=True, discover_similar=False)
        assert built.count() == _ALL

    def test_incremental_build_from_a_cold_instance(self, built):
        cold = SemanticIndex(built.vectors_path, embedder=StubEmbedder())
        cold.build(StubStore(), wipe=False, discover_similar=False)
        assert cold.count() == _ALL

    def test_wipe_drops_nodes_that_are_gone(self, built):
        built.build(StubStore(NODES[:1]), wipe=True, discover_similar=False)
        assert built.count() == 1


class TestColdRead:
    """`memorykg query` opens a store it did not build."""

    def test_search_without_a_prior_build(self, built):
        cold = SemanticIndex(built.vectors_path, embedder=StubEmbedder())
        assert [h.id for h in cold.search("climate", k=_ALL)] == [
            h.id for h in built.search("climate", k=_ALL)
        ]

    def test_count_without_a_prior_build(self, built):
        assert SemanticIndex(built.vectors_path, embedder=StubEmbedder()).count() == _ALL


class TestAbsentStore:
    """Reporting on a store must never bring it into being."""

    def test_count_is_zero(self, index):
        assert index.count() == 0

    def test_count_does_not_create_the_store(self, index):
        index.count()
        assert not index.vectors_path.exists()

    def test_search_raises_with_an_actionable_message(self, index):
        with pytest.raises(FileNotFoundError, match="memorykg build"):
            index.search("climate", k=4)

    def test_search_does_not_create_the_store(self, index):
        with pytest.raises(FileNotFoundError):
            index.search("climate", k=4)
        assert not index.vectors_path.exists()


class TestRepr:
    def test_names_the_vector_store(self, index):
        text = repr(index)
        assert "vectors_path" in text
        assert "lancedb" not in text.lower()
        assert "table" not in text.lower()


class TestEscape:
    def test_doubles_single_quotes(self):
        assert _escape("o'brien") == "o''brien"

    def test_leaves_ordinary_text_alone(self):
        assert _escape("sessions/s1.md") == "sessions/s1.md"
