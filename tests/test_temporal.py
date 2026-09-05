"""MemoryKG's adoption of the shared kg_utils.temporal contract.

This is the module where the contract earns its keep for personal-agent work:
real temporal memory without a large backend. Hindsight draws the same
distinction with its own ``occurred_start`` / ``occurred_end`` fields, and
personal_agent's DiaryTransformer already writes to them — so a MemoryKG index
speaking this vocabulary is a lightweight substitute for that part of it.

The distinction is the point. A note written tonight about last Tuesday
happened on Tuesday and was recorded tonight; a timeline that files it under
tonight is wrong about it.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from kg_utils.temporal import parse_temporal, read_span

from memory_kg.memorykg import _document_temporal

# 2025-06-15T15:06:40Z — deliberately long after the remembered date below,
# so "occurred" and "recorded" cannot be confused for one another.
_MTIME = 1750000000

_DATED = "---\ntimestamp: 2026-04-10\ncategory: work\n---\n\nRemembered a thing.\n"
_PLAIN = "Just a note, with no frontmatter at all.\n"


@pytest.fixture
def doc(tmp_path: Path):
    def _make(text: str, name: str = "m.md") -> Path:
        p = tmp_path / name
        p.write_text(text, encoding="utf-8")
        os.utime(p, (_MTIME, _MTIME))
        return p

    return _make


class TestOccurredVersusRecorded:
    def test_both_keys_when_the_document_is_dated(self, doc):
        p = doc(_DATED)
        assert set(_document_temporal(p, _DATED)) == {"occurred_start", "recorded_at"}

    def test_occurred_comes_from_the_frontmatter(self, doc):
        p = doc(_DATED)
        assert _document_temporal(p, _DATED)["occurred_start"] == "2026-04-10"

    def test_recorded_comes_from_the_file(self, doc):
        p = doc(_DATED)
        recorded = _document_temporal(p, _DATED)["recorded_at"]
        assert parse_temporal(recorded)[0].year == 2025

    def test_a_memory_is_filed_by_when_it_happened(self, doc):
        """Written June 2025, about April 2026. It belongs in April 2026."""
        p = doc(_DATED)
        span = read_span(_document_temporal(p, _DATED))
        assert span.overlaps("2026-04-01", "2026-04-30")

    def test_not_filed_by_when_it_was_written(self, doc):
        p = doc(_DATED)
        span = read_span(_document_temporal(p, _DATED))
        assert not span.overlaps("2025-06-01", "2025-06-30")


class TestUndatedDocuments:
    def test_plain_document_gets_recorded_only(self, doc):
        p = doc(_PLAIN)
        assert set(_document_temporal(p, _PLAIN)) == {"recorded_at"}

    def test_a_recorded_only_document_is_still_datable(self, doc):
        """The contract falls back to recorded_at, so these are not lost."""
        p = doc(_PLAIN)
        span = read_span(_document_temporal(p, _PLAIN))
        assert span.overlaps("2025-06-01", "2025-06-30")
        assert not span.overlaps("2026-01-01", "2026-12-31")

    def test_frontmatter_without_a_timestamp_is_fine(self, doc):
        text = "---\ncategory: work\n---\n\nA note.\n"
        p = doc(text)
        assert set(_document_temporal(p, text)) == {"recorded_at"}


class TestRobustness:
    def test_unparseable_timestamp_keeps_the_recorded_time(self, doc):
        """One bad date must not cost the document its date entirely."""
        text = "---\ntimestamp: sometime-last-spring\n---\n\nA note.\n"
        p = doc(text)
        out = _document_temporal(p, text)
        assert "recorded_at" in out
        assert "occurred_start" not in out

    def test_missing_file_yields_nothing(self, tmp_path):
        assert _document_temporal(tmp_path / "gone.md", _PLAIN) == {}

    def test_year_precision_is_preserved(self, doc):
        text = "---\ntimestamp: 2026\n---\n\nA note.\n"
        p = doc(text)
        span = read_span(_document_temporal(p, text))
        assert span.overlaps("2026-07-01", "2026-07-31")


class TestNodesCarryIt:
    """Documents, sections and chunks alike — a query hits chunks."""

    def test_metadata_field_defaults_empty(self):
        from memory_kg.memorykg import DocNode

        n = DocNode(
            id="d",
            kind="document",
            name="n",
            title=None,
            file_path="f.md",
            char_start=0,
            char_end=1,
            heading_level=None,
            text="t",
        )
        assert n.metadata == {}

    def test_metadata_round_trips_through_the_store(self, tmp_path):
        from memory_kg.memorykg import DocNode
        from memory_kg.store import GraphStore

        store = GraphStore(tmp_path / "g.sqlite")
        node = DocNode(
            id="doc:m.md",
            kind="document",
            name="m",
            title=None,
            file_path="m.md",
            char_start=0,
            char_end=1,
            heading_level=None,
            text="t",
            metadata={"occurred_start": "2026-04-10"},
        )
        store._upsert_nodes([node])
        got = store.node("doc:m.md")
        store.close()
        assert got is not None
        assert got["metadata"] == {"occurred_start": "2026-04-10"}


class TestReadPathsAgree:
    """Every read path must return the same keys. This is a drift guard.

    The failure it guards against is silent by construction: a SELECT that
    omits a column yields a node dict missing that key, and a missing
    ``metadata`` key reads as "this node is undated" rather than raising. That
    is exactly how an unselected column reached three of ftree_kg's query paths
    and one of doc_kg's before a test caught it.

    ``_NODE_COLUMNS`` now drives both the SELECTs and ``_row_to_node``, so the
    paths cannot disagree by construction. These pin that they don't, because a
    future hand-written query would not be covered by the constant.
    """

    def _store_with_node(self, tmp_path):
        from memory_kg.memorykg import DocNode
        from memory_kg.store import GraphStore

        store = GraphStore(tmp_path / "g.sqlite")
        store._upsert_nodes(
            [
                DocNode(
                    id="doc:m.md",
                    kind="document",
                    name="m",
                    title="T",
                    file_path="m.md",
                    char_start=0,
                    char_end=10,
                    heading_level=None,
                    text="body",
                    metadata={"occurred_start": "2026-04-10"},
                )
            ]
        )
        return store

    def test_node_and_query_nodes_return_the_same_keys(self, tmp_path):
        store = self._store_with_node(tmp_path)
        single = store.node("doc:m.md")
        listed = store.query_nodes()
        store.close()
        assert listed
        assert set(single) == set(listed[0])

    def test_iter_nodes_agrees_too(self, tmp_path):
        """`iter_nodes` streams `list[dict]` batches, not bare dicts."""
        store = self._store_with_node(tmp_path)
        single = store.node("doc:m.md")
        flattened = [n for batch in store.iter_nodes() for n in batch]
        store.close()
        assert flattened
        assert set(single) == set(flattened[0])

    def test_every_declared_column_is_a_key(self, tmp_path):
        """The mapper must expose every column the SELECTs ask for."""
        from memory_kg.store import _NODE_COLUMNS

        store = self._store_with_node(tmp_path)
        node = store.node("doc:m.md")
        store.close()
        assert set(node) == set(_NODE_COLUMNS)

    def test_metadata_survives_every_path(self, tmp_path):
        """The key existing is not enough — it must carry the value."""
        store = self._store_with_node(tmp_path)
        paths = {
            "node": store.node("doc:m.md"),
            "query_nodes": store.query_nodes()[0],
            "iter_nodes": next(iter(store.iter_nodes()))[0],
        }
        store.close()
        for name, node in paths.items():
            assert node["metadata"] == {"occurred_start": "2026-04-10"}, name

    def test_metadata_is_always_a_dict_never_missing(self, tmp_path):
        """An absent blob must read as {}, not as a missing key."""
        from memory_kg.memorykg import DocNode
        from memory_kg.store import GraphStore

        store = GraphStore(tmp_path / "g2.sqlite")
        store._upsert_nodes(
            [
                DocNode(
                    id="doc:x.md",
                    kind="document",
                    name="x",
                    title=None,
                    file_path="x.md",
                    char_start=0,
                    char_end=1,
                    heading_level=None,
                    text="t",
                )
            ]
        )
        node = store.node("doc:x.md")
        store.close()
        assert node["metadata"] == {}


class TestPipeDelimitedEntries:
    """The format real memory corpora actually arrive in.

    personal_agent's `DiaryTransformer` writes one pipe-delimited entry per
    line, each with its own timestamp::

        2024-01-15T10:30 | social | Reflection | On 2024-01-15T10:30, ...

    Not YAML frontmatter. The first version of this module parsed frontmatter
    only, so on a real corpus `occurred_start` never fired and every chunk in a
    file spanning a year was stamped with the file's mtime — one point for
    twelve months of memories, which is why it did not help.
    """

    def _entries(self):
        return [
            f"2024-{m}-{d}T10:30 | {c} | Reflection | On 2024-{m}-{d}, entry about {c}."
            for m, d, c in [
                ("01", "15", "social"),
                ("03", "02", "work"),
                ("06", "21", "hobbies"),
                ("11", "09", "health"),
            ]
        ]

    def _fallback(self):
        return {"recorded_at": "2025-06-15T15:06:40+00:00"}

    def test_a_single_entry_is_dated_by_its_stamp(self):
        from memory_kg.memorykg import _chunk_temporal

        out = _chunk_temporal(self._entries()[0], self._fallback())
        assert out["occurred_start"].startswith("2024-01-15")

    def test_a_chunk_spanning_entries_becomes_an_interval(self):
        from memory_kg.memorykg import _chunk_temporal

        out = _chunk_temporal(" ".join(self._entries()), self._fallback())
        assert out["occurred_start"].startswith("2024-01-15")
        assert out["occurred_end"].startswith("2024-11-09")

    def test_timestamps_are_found_after_whitespace_normalisation(self):
        """The chunker collapses newlines, so entries arrive on ONE line.

        A line-anchored pattern finds only the first stamp and silently dates a
        year of memories to its opening entry. That was a real bug.
        """
        from memory_kg.memorykg import _PIPE_TIMESTAMP_RE

        one_line = " ".join(self._entries())
        assert len(_PIPE_TIMESTAMP_RE.findall(one_line)) == 4

    def test_a_bare_date_in_prose_is_not_mistaken_for_a_stamp(self):
        """`On 2024-01-15, ...` has no pipe after it and must not match."""
        from memory_kg.memorykg import _PIPE_TIMESTAMP_RE

        found = _PIPE_TIMESTAMP_RE.findall(
            "2024-01-15T10:30 | social | Reflection | On 2024-03-02, a later date in prose."
        )
        assert found == ["2024-01-15T10:30"]

    def test_recorded_at_survives_alongside_the_entry_dates(self):
        from memory_kg.memorykg import _chunk_temporal

        out = _chunk_temporal(" ".join(self._entries()), self._fallback())
        assert out["recorded_at"].startswith("2025-06-15")

    def test_text_without_stamps_falls_back_to_the_document(self):
        from memory_kg.memorykg import _chunk_temporal

        assert _chunk_temporal("ordinary prose", self._fallback()) == self._fallback()


class TestRealCorpusEndToEnd:
    """A whole multi-month file, parsed the way the builder parses it."""

    def _corpus(self, tmp_path):
        import os

        lines = [
            f"2024-{m}-{d}T10:30 | {c} | Reflection | On 2024-{m}-{d}, entry about {c}."
            for m, d, c in [("01", "15", "a"), ("06", "21", "b"), ("11", "09", "c")]
        ]
        f = tmp_path / "memories.md"
        f.write_text("\n\n".join(lines) + "\n", encoding="utf-8")
        os.utime(f, (1750000000, 1750000000))  # written 2025-06
        return tmp_path

    def _dated(self, tmp_path):
        from memory_kg.memorykg import parse_corpus

        nodes, _ = parse_corpus(self._corpus(tmp_path))
        return {n.kind: read_span(n.metadata) for n in nodes if read_span(n.metadata)}

    def test_document_and_chunk_are_dated_by_content(self, tmp_path):
        spans = self._dated(tmp_path)
        for kind in ("document", "chunk"):
            assert spans[kind].start.year == 2024, kind

    def test_a_mid_range_window_matches(self, tmp_path):
        """June is inside the span but is neither endpoint."""
        spans = self._dated(tmp_path)
        assert spans["chunk"].overlaps("2024-06-01", "2024-06-30")

    def test_the_write_year_does_not_match(self, tmp_path):
        """The file was written in 2025; its memories are not from 2025."""
        spans = self._dated(tmp_path)
        assert not spans["chunk"].overlaps("2025-01-01", "2025-12-31")

    def test_recorded_at_still_records_the_write(self, tmp_path):
        from memory_kg.memorykg import parse_corpus

        nodes, _ = parse_corpus(self._corpus(tmp_path))
        doc = next(n for n in nodes if n.kind == "document")
        assert doc.metadata["recorded_at"].startswith("2025-06")


def _find_pepys() -> Path | None:
    """Locate the real Pepys corpus, or return ``None``.

    Checked in order: ``MEMORYKG_PEPYS_CORPUS``, then a ``corpus_pepys`` clone
    sitting beside this repo, which is where the fleet keeps it.

    This used to be one hardcoded absolute path that existed on no machine, so
    the class below skipped everywhere -- locally and in CI -- while reading as
    covered. These are the tests that caught both real dating bugs; they are
    worth actually running.
    """
    override = os.environ.get("MEMORYKG_PEPYS_CORPUS")
    if override:
        candidate = Path(override).expanduser()
        return candidate if candidate.exists() else None

    sibling = Path(__file__).resolve().parents[2] / "corpus_pepys" / "data" / "pepys_clean.txt"
    return sibling if sibling.exists() else None


_PEPYS = _find_pepys()


@pytest.mark.skipif(
    _PEPYS is None,
    reason="corpus_pepys not found; set MEMORYKG_PEPYS_CORPUS or clone it beside this repo",
)
class TestAgainstRealPepysCorpus:
    """The real diary, in the real format, at real scale.

    Every earlier version of these tests passed against text I invented, and
    two separate bugs survived that. Both only appeared here:

    1. The chunker normalises whitespace, so a line-anchored pattern found one
       stamp per chunk instead of all of them.
    2. Most chunks carry no stamp at all — 11,184 of 14,477 — because chunking
       splits mid-entry. Falling back to the *document's* span handed each of
       them the diary's whole decade, so 11,190 nodes matched a five-day
       window.
    """

    @pytest.fixture(scope="class")
    def parsed(self, tmp_path_factory):
        import shutil

        from memory_kg.memorykg import parse_corpus

        d = tmp_path_factory.mktemp("pepys")
        shutil.copy(_PEPYS, d / "pepys.txt")
        nodes, _ = parse_corpus(d)
        return nodes

    def _dated(self, nodes, kind=None):
        out = []
        for n in nodes:
            if kind and n.kind != kind:
                continue
            s = read_span(n.metadata)
            if s and s.start:
                out.append((n, s))
        return out

    def test_the_whole_decade_is_covered(self, parsed):
        years = {s.start.year for _, s in self._dated(parsed)}
        assert years >= set(range(1660, 1670))

    def test_no_single_year_swamps_the_rest(self, parsed):
        """The fallback bug piled 11,547 of 14,478 nodes onto 1660 alone — 80%.

        A ratio test against the smallest year would be wrong: the diary starts
        in April 1660 and ends in May 1669, so both end years are legitimately
        thin. What the bug actually looked like was one year holding most of
        the corpus.
        """
        import collections

        dated = self._dated(parsed)
        years = collections.Counter(s.start.year for _, s in dated)
        biggest = max(years.values()) / len(dated)
        assert biggest < 0.30, f"one year holds {biggest:.0%} of dated nodes"

    def test_chunks_are_points_not_decade_wide_intervals(self, parsed):
        """A chunk inheriting the document span would cover 1660-1669."""
        wide = [
            n.id for n, s in self._dated(parsed, "chunk") if s.end and (s.end - s.start).days > 366
        ]
        assert not wide, f"{len(wide)} chunks span more than a year"

    def test_the_great_fire_is_findable(self, parsed):
        """2-6 September 1666 should return the fire, and little else."""
        hits = [
            (n, s)
            for n, s in self._dated(parsed, "chunk")
            if s.overlaps("1666-09-02", "1666-09-06")
        ]
        assert 0 < len(hits) < 500, f"{len(hits)} hits — a window this narrow should be tight"
        blob = " ".join((n.text or "").lower() for n, _ in hits)
        assert "fire" in blob

    def test_a_quiet_window_returns_far_fewer_than_the_fire(self, parsed):
        """Sanity that the window is doing work, not matching everything."""

        def count(a, b):
            return sum(1 for _, s in self._dated(parsed, "chunk") if s.overlaps(a, b))

        assert count("1666-09-02", "1666-09-06") > 0
        assert count("1699-01-01", "1699-12-31") == 0
