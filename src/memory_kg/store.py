#!/usr/bin/env python3
"""
store.py

GraphStore — SQLite persistence layer for MemoryKG.

Mirrors CodeKG's GraphStore almost exactly.  SQLite is the authoritative,
canonical store.  No embeddings, no vector store, no text parsing.

Schema differences from CodeKG:
  - ``nodes.text``   replaces  ``nodes.docstring``
  - ``nodes.title``  replaces  ``nodes.qualname``
  - ``nodes.char_start`` / ``nodes.char_end``  replace  ``nodes.lineno`` / ``nodes.end_lineno``
  - ``nodes.heading_level`` is new (int, nullable)
  - DEFAULT_RELS includes SIMILAR_TO and NEXT in addition to CONTAINS/REFERENCES

Author: Eric G. Suchanek, PhD
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Sequence
from pathlib import Path

from memory_kg.memorykg import DocEdge, DocNode

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

#: The node columns, in the order every read path selects them and
#: :func:`_row_to_node` unpacks them. One tuple drives both, so a column can
#: never reach some reads and not others -- the failure that put an unselected
#: `metadata` column into three of ftree_kg's query paths and one of doc_kg's,
#: where a missing key reads as "undated" rather than raising.
_NODE_COLUMNS: tuple[str, ...] = (
    "id",
    "kind",
    "name",
    "title",
    "file_path",
    "char_start",
    "char_end",
    "heading_level",
    "text",
    "metadata",
)

#: ``"id, kind, name, ..."`` -- interpolated into every node SELECT.
_NODE_COLUMN_SQL = ", ".join(_NODE_COLUMNS)

#: Rows per upsert transaction. Bounds peak memory to one batch's worth of
#: flattened row tuples, and keeps a single huge write from holding one
#: multi-hour transaction open (WAL growth, no progress checkpoints).
_UPSERT_BATCH_SIZE = 5000

_SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS nodes (
  id            TEXT PRIMARY KEY,
  kind          TEXT NOT NULL,
  name          TEXT NOT NULL,
  title         TEXT,
  file_path     TEXT,
  char_start    INTEGER,
  char_end      INTEGER,
  heading_level INTEGER,
  text          TEXT,
  -- Added 2026-08-22. There is no in-place migration: a MemoryKG index is
  -- rebuilt from its corpus, so an older database is replaced rather than
  -- altered. Querying one before rebuilding fails loudly on this column,
  -- which is the signal to rebuild.
  metadata      TEXT
);

CREATE TABLE IF NOT EXISTS edges (
  src      TEXT NOT NULL,
  rel      TEXT NOT NULL,
  dst      TEXT NOT NULL,
  evidence TEXT,
  PRIMARY KEY (src, rel, dst)
);

CREATE INDEX IF NOT EXISTS idx_nodes_kind      ON nodes(kind);
CREATE INDEX IF NOT EXISTS idx_nodes_name      ON nodes(name);
CREATE INDEX IF NOT EXISTS idx_nodes_file_path ON nodes(file_path);

CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst);
CREATE INDEX IF NOT EXISTS idx_edges_rel ON edges(rel);
"""

# Default edge types used for graph expansion (document layer only)
DEFAULT_RELS: tuple[str, ...] = (
    "CONTAINS",
    "NEXT",
    "REFERENCES",
    "SIMILAR_TO",
    "HAS_TOPIC",
    "MENTIONS_ENTITY",
    "HAS_KEYWORD",
)

# Semantic memory layer edge types (assertions + events)
MEMORY_RELS: tuple[str, ...] = (
    "SUPPORTS",  # chunk → assertion
    "ABOUT",  # assertion → entity (subject)
    "REFERS_TO",  # assertion → entity (object)
    "INVOLVES",  # event → entity
    "DESCRIBES",  # chunk → event
    "SUPERSEDES",  # assertion → assertion
    "DERIVED_FROM",  # assertion → event
)


# ---------------------------------------------------------------------------
# Provenance metadata returned by expand()
# ---------------------------------------------------------------------------


class ProvMeta:
    """
    Provenance metadata for a node returned by :meth:`GraphStore.expand`.

    :param best_hop: Minimum hop distance from any seed node.
    :param via_seed: ID of the seed node that yielded the shortest path.
    """

    __slots__ = ("best_hop", "via_seed")

    def __init__(self, best_hop: int, via_seed: str) -> None:
        """Store provenance metadata for a graph node discovered during expansion."""
        self.best_hop = best_hop
        self.via_seed = via_seed

    def __repr__(self) -> str:
        """Return string representation."""
        return f"ProvMeta(best_hop={self.best_hop}, via_seed={self.via_seed!r})"


# ---------------------------------------------------------------------------
# GraphStore
# ---------------------------------------------------------------------------


class GraphStore:
    """
    SQLite-backed authoritative store for the MemoryKG.

    Manages the ``nodes`` and ``edges`` tables and provides graph
    traversal primitives used by the query layer.

    Example::

        store = GraphStore("memorykg.sqlite")
        store.write(nodes, edges, wipe=True)
        print(store.stats())

    :param db_path: Path to the SQLite database file (created if absent).
    """

    def __init__(self, db_path: str | Path) -> None:
        """Open or create the SQLite database at *db_path*."""
        self.db_path = Path(db_path)
        self._con: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    @property
    def con(self) -> sqlite3.Connection:
        """Lazy SQLite connection (created on first access)."""
        if self._con is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._con = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
            )
            self._con.executescript(_SCHEMA_SQL)
        return self._con

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        if self._con is not None:
            self._con.close()
            self._con = None

    def __enter__(self) -> GraphStore:
        """Support context manager use."""
        return self

    def __exit__(self, *_: object) -> None:
        """Close the SQLite connection on context manager exit."""
        self.close()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Delete all nodes and edges."""
        self.con.execute("DELETE FROM edges;")
        self.con.execute("DELETE FROM nodes;")
        self.con.commit()

    def write(
        self,
        nodes: Sequence[DocNode],
        edges: Sequence[DocEdge],
        *,
        wipe: bool = False,
    ) -> None:
        """Persist a complete graph to SQLite.

        :param nodes: Node list from :class:`~memory_kg.graph.DocGraph`.
        :param edges: Edge list from :class:`~memory_kg.graph.DocGraph`.
        :param wipe: If ``True``, clear existing data before writing.
        """
        if wipe:
            self.clear()
        self._upsert_nodes(nodes)
        self._upsert_edges(edges)

    def _upsert_nodes(self, nodes: Iterable[DocNode]) -> None:
        """Upsert node rows into the ``nodes`` table, committing in batches."""
        node_list = nodes if isinstance(nodes, list) else list(nodes)
        for start in range(0, len(node_list), _UPSERT_BATCH_SIZE):
            rows = [
                (
                    n.id,
                    n.kind,
                    n.name,
                    n.title,
                    n.file_path,
                    n.char_start,
                    n.char_end,
                    n.heading_level,
                    n.text,
                    json.dumps(n.metadata, ensure_ascii=False) if n.metadata else None,
                )
                for n in node_list[start : start + _UPSERT_BATCH_SIZE]
            ]
            self.con.executemany(
                """
                INSERT INTO nodes
                  (id, kind, name, title, file_path, char_start, char_end, heading_level,
                   text, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  kind=excluded.kind,
                  name=excluded.name,
                  title=excluded.title,
                  file_path=excluded.file_path,
                  char_start=excluded.char_start,
                  char_end=excluded.char_end,
                  heading_level=excluded.heading_level,
                  text=excluded.text,
                  metadata=excluded.metadata
                """,
                rows,
            )
            self.con.commit()

    def _upsert_edges(self, edges: Iterable[DocEdge]) -> None:
        """Upsert edge rows into the ``edges`` table, committing in batches."""
        edge_list = edges if isinstance(edges, list) else list(edges)
        for start in range(0, len(edge_list), _UPSERT_BATCH_SIZE):
            rows = [
                (
                    e.src,
                    e.rel,
                    e.dst,
                    (
                        json.dumps(e.evidence, ensure_ascii=False)
                        if e.evidence is not None
                        else None
                    ),
                )
                for e in edge_list[start : start + _UPSERT_BATCH_SIZE]
            ]
            self.con.executemany(
                """
                INSERT INTO edges (src, rel, dst, evidence)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(src, rel, dst) DO UPDATE SET
                  evidence=excluded.evidence
                """,
                rows,
            )
            self.con.commit()

    # ------------------------------------------------------------------
    # Read — single node
    # ------------------------------------------------------------------

    def node(self, node_id: str) -> dict | None:
        """Fetch a single node by id.

        :param node_id: Stable node identifier.
        :return: Node dict or ``None`` if not found.
        """
        row = self.con.execute(
            f"""
            SELECT {_NODE_COLUMN_SQL}
            FROM nodes WHERE id = ?
            """,
            (node_id,),
        ).fetchone()
        return _row_to_node(row) if row else None

    # ------------------------------------------------------------------
    # Read — filtered node lists
    # ------------------------------------------------------------------

    def count_nodes(self, *, kinds: Sequence[str] | None = None) -> int:
        """Return total count of nodes matching an optional kind filter.

        Used by the index builder to size the progress bar and pre-allocate the
        SIMILAR_TO chunk-vector matrix without loading any node text into RAM.

        :param kinds: Restrict to these node kinds.
        :return: Row count.
        """
        if kinds:
            placeholders = ",".join("?" for _ in kinds)
            row = self.con.execute(
                f"SELECT COUNT(*) FROM nodes WHERE kind IN ({placeholders})",
                list(kinds),
            ).fetchone()
        else:
            row = self.con.execute("SELECT COUNT(*) FROM nodes").fetchone()
        return int(row[0]) if row else 0

    def query_nodes(
        self,
        *,
        kinds: Sequence[str] | None = None,
        file_path: str | None = None,
    ) -> list[dict]:
        """Return nodes matching optional filters.

        :param kinds: Restrict to these node kinds (e.g. ``["chunk", "section"]``).
        :param file_path: Restrict to nodes in this file path (exact match).
        :return: List of node dicts.
        """
        clauses: list[str] = []
        params: list[object] = []

        if kinds:
            placeholders = ",".join("?" for _ in kinds)
            clauses.append(f"kind IN ({placeholders})")
            params.extend(kinds)

        if file_path is not None:
            clauses.append("file_path = ?")
            params.append(file_path)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.con.execute(
            f"""
            SELECT {_NODE_COLUMN_SQL}
            FROM nodes {where}
            ORDER BY file_path, char_start
            """,
            params,
        ).fetchall()
        return [_row_to_node(r) for r in rows]

    def iter_nodes(
        self,
        *,
        kinds: Sequence[str] | None = None,
        batch_size: int = 512,
    ):
        """Yield node dicts in batches without loading all rows into RAM.

        Streams the result cursor in ``batch_size`` pages so the index builder
        never holds the full corpus text in memory at once.

        :param kinds: Restrict to these node kinds.
        :param batch_size: Rows per yielded batch.
        :return: Generator of ``list[dict]`` batches.
        """
        clauses: list[str] = []
        params: list[object] = []

        if kinds:
            placeholders = ",".join("?" for _ in kinds)
            clauses.append(f"kind IN ({placeholders})")
            params.extend(kinds)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        cursor = self.con.execute(
            f"""
            SELECT {_NODE_COLUMN_SQL}
            FROM nodes {where}
            ORDER BY file_path, char_start
            """,
            params,
        )

        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            yield [_row_to_node(r) for r in rows]

    # ------------------------------------------------------------------
    # Read — edges
    # ------------------------------------------------------------------

    def edges_within(self, node_ids: set[str]) -> list[dict]:
        """Return all edges where both src and dst are in *node_ids*.

        :param node_ids: Set of node IDs to restrict to.
        :return: List of edge dicts.
        """
        if not node_ids:
            return []

        self.con.execute("DROP TABLE IF EXISTS _tmp_ids;")
        self.con.execute("CREATE TEMP TABLE _tmp_ids (id TEXT PRIMARY KEY);")
        self.con.executemany("INSERT INTO _tmp_ids (id) VALUES (?)", [(i,) for i in node_ids])
        rows = self.con.execute(
            """
            SELECT e.src, e.rel, e.dst, e.evidence
            FROM edges e
            JOIN _tmp_ids s ON s.id = e.src
            JOIN _tmp_ids d ON d.id = e.dst
            """
        ).fetchall()
        return [{"src": r[0], "rel": r[1], "dst": r[2], "evidence": r[3]} for r in rows]

    def edges_from(
        self, node_id: str, *, rel: str | None = None, limit: int | None = None
    ) -> list[dict]:
        """Return all edges originating from *node_id*.

        :param node_id: Source node identifier.
        :param rel: Relation type filter (``None`` returns all relations).
        :param limit: Maximum number of edges to return.
        :return: List of edge dicts.
        """
        params: list[object]
        if rel is not None:
            query = "SELECT src, rel, dst, evidence FROM edges WHERE src = ? AND rel = ?"
            params = [node_id, rel]
        else:
            query = "SELECT src, rel, dst, evidence FROM edges WHERE src = ?"
            params = [node_id]
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        rows = self.con.execute(query, params).fetchall()
        return [{"src": r[0], "rel": r[1], "dst": r[2], "evidence": r[3]} for r in rows]

    # ------------------------------------------------------------------
    # Graph traversal
    # ------------------------------------------------------------------

    def expand(
        self,
        seed_ids: set[str],
        *,
        hop: int = 1,
        rels: tuple[str, ...] = DEFAULT_RELS,
    ) -> dict[str, ProvMeta]:
        """Expand the graph from *seed_ids* up to *hop* hops.

        Returns a mapping from every reachable node ID to its
        :class:`ProvMeta` (minimum hop distance and originating seed).

        When several nodes at the same hop reach the same neighbour, the first
        one to claim it supplies its ``via_seed``. The frontier is therefore
        traversed in sorted ID order: iterating the set directly would let
        Python's per-process string hash randomisation pick the winner, and
        ``via_seed`` supplies the ``base_dist`` that orders results in
        :meth:`MemoryKG.query` — so an arbitrary winner reorders the tail and
        changes which node survives ``max_nodes`` truncation.

        :param seed_ids: Starting node IDs (hop 0).
        :param hop: Maximum number of hops to traverse.
        :param rels: Edge relation types to follow.
        :return: ``{node_id: ProvMeta}`` for all reachable nodes.
        """
        rels = tuple(rels)
        meta: dict[str, ProvMeta] = {sid: ProvMeta(best_hop=0, via_seed=sid) for sid in seed_ids}
        frontier: set[str] = set(seed_ids)

        for h in range(1, hop + 1):
            nxt: set[str] = set()
            for nid in sorted(frontier):
                rows = self.con.execute(
                    f"""
                    SELECT src, dst FROM edges
                    WHERE (src = ? OR dst = ?)
                      AND rel IN ({",".join("?" for _ in rels)})
                    """,
                    (nid, nid, *rels),
                ).fetchall()
                for src, dst in rows:
                    for cand in (src, dst):
                        if cand not in meta or h < meta[cand].best_hop:
                            meta[cand] = ProvMeta(
                                best_hop=h,
                                via_seed=meta[nid].via_seed,
                            )
                            nxt.add(cand)
            frontier = nxt

        return meta

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        """Return node and edge counts by kind/relation.

        :return: dict with ``total_nodes``, ``total_edges``, ``node_counts``,
                 ``edge_counts``.
        """
        node_rows = self.con.execute("SELECT kind, COUNT(*) FROM nodes GROUP BY kind").fetchall()
        edge_rows = self.con.execute("SELECT rel, COUNT(*) FROM edges GROUP BY rel").fetchall()
        total_nodes = self.con.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        total_edges = self.con.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        return {
            "db_path": str(self.db_path),
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "node_counts": {r[0]: r[1] for r in node_rows},
            "edge_counts": {r[0]: r[1] for r in edge_rows},
        }

    def __repr__(self) -> str:
        """Return string representation."""
        return f"GraphStore(db_path={self.db_path!r})"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _row_to_node(row: tuple) -> dict:
    """Convert a raw SQLite row into a node dict.

    Built from :data:`_NODE_COLUMNS`, the same tuple every SELECT interpolates,
    so the mapper cannot fall out of step with what was actually selected.

    :param row: A row in ``_NODE_COLUMNS`` order.
    :return: Node dict keyed by column name, with ``metadata`` decoded.
    """
    node = dict(zip(_NODE_COLUMNS, row, strict=True))
    node["metadata"] = _decode_metadata(node.get("metadata"))
    return node


def _decode_metadata(blob: str | None) -> dict:
    """Decode a stored metadata blob, tolerating anything unreadable.

    Extension data is not worth making a node unreadable over, so a blob that
    fails to parse -- or that decodes to something other than an object --
    reads as ``{}`` rather than raising.

    :param blob: JSON text from the ``metadata`` column, or ``None``.
    :return: The decoded mapping, or ``{}``.
    """
    if not blob:
        return {}
    try:
        loaded = json.loads(blob)
    except (TypeError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}
