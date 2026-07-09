#!/usr/bin/env python3
"""
index.py

SemanticIndex — LanceDB vector index for MemoryKG.

Mirrors DocKG's index.py with the following additions:

1. Default model is ``BAAI/bge-small-en-v1.5`` (384-dim) via ``DEFAULT_MODEL``
   from ``kg_utils.embed``; override with ``KGRAG_MODEL_DIR`` env var or ``--model``.

2. After building the vector index, ``build()`` optionally runs a
   SIMILAR_TO edge discovery pass: each chunk is queried against its
   k-nearest neighbors and edges are written back to the GraphStore when
   cosine similarity exceeds *similarity_edge_threshold*.  This creates
   the semantic graph layer that makes MemoryKG more than a pure vector store.

3. ``_build_index_text()`` is adapted for document nodes: uses title,
   section context, and chunk text instead of kind/qualname/docstring.

Author: Eric G. Suchanek, PhD
Last Revision: 2026-07-09 14:38:45
"""

# pylint: disable=C0415

from __future__ import annotations

import contextlib
import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from kg_utils.embed import resolve_model_path
from kg_utils.embedder import Embedder, SentenceTransformerEmbedder
from rich.console import Console

if TYPE_CHECKING:
    from memory_kg.store import GraphStore

# ---------------------------------------------------------------------------
# Local model cache (same logic as CodeKG)
# ---------------------------------------------------------------------------


def _local_model_path(model_name: str) -> Path:
    """Return the local cache path for *model_name*.

    Delegates to :func:`kg_utils.embed.resolve_model_path` with
    ``.memorykg/models/`` as the local fallback.  Respects ``KGRAG_MODEL_DIR``
    for system-wide cache redirection.

    :param model_name: HuggingFace model identifier or known alias.
    :return: Absolute :class:`~pathlib.Path` to the cached model directory.
    """
    return resolve_model_path(model_name, local_fallback=Path.cwd() / ".memorykg" / "models")


def _resolve_device(explicit: str | None = None) -> str:
    """Resolve the embedding device the same way ``kg_utils.embedder`` does.

    Precedence: explicit arg > ``KG_EMBED_DEVICE`` env > auto-detect
    (``cuda`` → ``mps`` → ``cpu``).  This is a read-only mirror of the resolution
    inside :func:`kg_utils.embedder.load_sentence_transformer` — use it to *report*
    the device (e.g. in a CLI banner), not to construct the embedder.  Pinning
    ``KG_EMBED_DEVICE=cpu`` is the robust escape hatch on Apple Silicon: it
    sidesteps the MPS allocator cliff that stalls very large ingests.

    :param explicit: Explicit device (``"cpu"``/``"mps"``/``"cuda"``), or
                     ``None``/``"auto"`` to defer to env / auto-detect.
    :return: A concrete device string.
    """
    sel = (explicit or "").strip().lower()
    if sel and sel != "auto":
        return sel
    env = os.environ.get("KG_EMBED_DEVICE", "").strip().lower()
    if env:
        return env
    try:
        import torch  # pylint: disable=import-outside-toplevel

        if torch.cuda.is_available():
            return "cuda"
        return "mps" if torch.backends.mps.is_available() else "cpu"
    except (ImportError, AttributeError):
        return "cpu"


# ---------------------------------------------------------------------------
# Logging / progress suppression
# ---------------------------------------------------------------------------


def suppress_ingestion_logging() -> None:
    """Suppress verbose progress output during model loading and ingestion."""
    for name in ("sentence_transformers", "transformers", "huggingface_hub", "lancedb"):
        logging.getLogger(name).setLevel(logging.WARNING)

    try:
        import transformers  # pylint: disable=import-outside-toplevel

        transformers.logging.set_verbosity_error()
    except (ImportError, AttributeError):
        pass

    try:
        import tqdm as _tqdm  # pylint: disable=import-outside-toplevel

        _orig_init = _tqdm.tqdm.__init__

        def _silent_init(self, *args, **kwargs):
            """Patch tqdm.__init__ to always disable progress output."""
            kwargs["disable"] = True
            _orig_init(self, *args, **kwargs)

        _tqdm.tqdm.__init__ = _silent_init  # ty: ignore[invalid-assignment]

        try:
            import tqdm.auto as _tqdm_auto  # pylint: disable=import-outside-toplevel

            if _tqdm_auto.tqdm is not _tqdm.tqdm:
                _tqdm_auto.tqdm.__init__ = _silent_init  # ty: ignore[invalid-assignment]
        except ImportError:
            pass
    except (ImportError, AttributeError):
        pass


# ---------------------------------------------------------------------------
# Embedder — the concrete backend lives in ``kg_utils.embedder`` so the
# local_files_only guard, model-alias resolution, and KG_EMBED_DEVICE handling
# are defined exactly once for every KG module.  ``Embedder`` and
# ``SentenceTransformerEmbedder`` are re-exported above for backward-compatible
# imports (``from memory_kg.index import SentenceTransformerEmbedder``).
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Seed hit
# ---------------------------------------------------------------------------


@dataclass
class SeedHit:
    """A single result from a semantic vector search.

    :param id: Node ID.
    :param kind: Node kind (``document``, ``section``, ``chunk``).
    :param name: Short name.
    :param title: Section or document title.
    :param file_path: Corpus-relative file path.
    :param distance: Vector distance (lower = more similar).
    :param rank: Zero-based rank in the result list.
    """

    id: str
    kind: str
    name: str
    title: str
    file_path: str
    distance: float
    rank: int


# ---------------------------------------------------------------------------
# SemanticIndex
# ---------------------------------------------------------------------------

_DEFAULT_TABLE = "memorykg_nodes"
_DEFAULT_KINDS = ("document", "section", "chunk", "topic", "entity", "keyword")


class SemanticIndex:
    """LanceDB-backed semantic vector index for MemoryKG.

    Reads nodes from a :class:`~memory_kg.store.GraphStore`, embeds them, and
    stores the vectors in LanceDB.  The index is **derived and disposable** —
    it can be rebuilt from SQLite at any time without data loss.

    ``search`` uses an exact flat cosine scan (no ANN index): retrieval recall
    is exact, which the benchmark suites depend on.  Search cost grows linearly
    with corpus size but stays well within budget at the scales in use.

    After building the vector index, optionally runs a SIMILAR_TO edge
    discovery pass that writes semantic similarity edges back to the store.

    Example::

        embedder = SentenceTransformerEmbedder()
        idx = SemanticIndex("./lancedb", embedder=embedder)
        idx.build(store, wipe=True)

        hits = idx.search("climate change policy", k=8)
        for h in hits:
            print(h.id, h.distance)

    :param lancedb_dir: Directory for the LanceDB database.
    :param embedder: Embedding backend.
    :param table: LanceDB table name.
    :param index_kinds: Node kinds to embed.
    """

    def __init__(
        self,
        lancedb_dir: str | Path,
        *,
        embedder: Embedder | None = None,
        table: str = _DEFAULT_TABLE,
        index_kinds: Sequence[str] = _DEFAULT_KINDS,
    ) -> None:
        """Configure the LanceDB-backed semantic index; the table is opened lazily."""
        self.lancedb_dir = Path(lancedb_dir)
        self.embedder: Embedder = embedder or SentenceTransformerEmbedder()
        self.table_name = table
        self.index_kinds = tuple(index_kinds)
        self._tbl = None

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(
        self,
        store: GraphStore,
        *,
        wipe: bool = False,
        batch_size: int = 8192,
        encode_batch_size: int = 128,
        quiet: bool = True,
        discover_similar: bool = True,
        similar_k: int = 5,
        similarity_edge_threshold: float = 0.85,
        similar_max_degree: int = 0,
        n_workers: int = 8,  # pylint: disable=unused-argument
    ) -> dict:
        """Build (or rebuild) the vector index from *store*.

        Nodes are streamed from SQLite in pages (never the whole corpus in RAM),
        embedded, and written to LanceDB in large fragments.  Chunk vectors are
        accumulated into a single pre-allocated ``(n_chunks × dim)`` float32
        matrix so the SIMILAR_TO pass sees a compact array rather than hundreds
        of thousands of loose Python lists.  After indexing, optionally discovers
        SIMILAR_TO edges between semantically close chunk nodes.

        :param store: Authoritative :class:`~memory_kg.store.GraphStore`.
        :param wipe: If ``True``, delete all existing vectors first.
        :param batch_size: LanceDB write batch size (rows buffered per ``add``).
        :param encode_batch_size: Texts fed to ``model.encode()`` per call
                                  (default 128).  Attention memory scales with
                                  ``batch x seq^2``; on both CPU and MPS throughput
                                  is flat above ~128 for small models, so a larger
                                  value only inflates peak RAM.  Raise it only for
                                  large models on a large-VRAM CUDA GPU.
        :param quiet: Suppress progress output.
        :param discover_similar: If ``True``, run SIMILAR_TO edge discovery.
        :param similar_k: k-nearest neighbors to examine per chunk.
        :param similarity_edge_threshold: Minimum cosine similarity to emit a
                                          SIMILAR_TO edge (0–1).
        :param similar_max_degree: Cap total SIMILAR_TO edges per node (0 = unlimited).
        :param n_workers: Accepted for call-site compatibility; ignored. Phase 2
                          embedding runs single-process — multi-process spawn
                          deadlocks on macOS with MPS and the GPU batch loop is
                          already hardware-accelerated.
        :return: Stats dict.
        """
        if quiet:
            suppress_ingestion_logging()

        import numpy as np  # pylint: disable=import-outside-toplevel

        # Count without loading any text — used for the progress bar and chunk pre-alloc.
        n_total = store.count_nodes(kinds=list(self.index_kinds))
        n_chunks = store.count_nodes(kinds=["chunk"]) if discover_similar else 0

        if not quiet:
            Console().print(f"  nodes    : {n_total:,} to embed")
        tbl = self._open_table(wipe=wipe)

        indexed = 0
        # Buffer LanceDB writes into large fragments regardless of the (smaller)
        # encode batch: each add() commits a fragment and rewrites the manifest,
        # so many small writes make fragment count — and thus per-commit cost —
        # grow over the build.  Floor at 4096.
        write_batch_size = max(int(batch_size), int(encode_batch_size), 4096)
        pending_rows: list[dict[str, Any]] = []
        # Pre-allocate a contiguous (n_chunks x dim) matrix for chunk vectors so
        # the SIMILAR_TO pass has a compact array rather than 300K+ loose ndarrays.
        chunk_pair_ids: list[str] = []
        chunk_pair_vecs: Any = (
            np.empty((n_chunks, self.embedder.dim), dtype=np.float32)
            if discover_similar and n_chunks > 0
            else None
        )
        chunk_vec_idx = 0

        if not quiet:
            from rich.progress import (  # pylint: disable=import-outside-toplevel
                BarColumn,
                MofNCompleteColumn,
                Progress,
                SpinnerColumn,
                TextColumn,
                TimeElapsedColumn,
                TimeRemainingColumn,
            )

            _progress_ctx: contextlib.AbstractContextManager = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                TimeRemainingColumn(),
            )
        else:
            _progress_ctx = contextlib.nullcontext()

        with _progress_ctx as prog:
            task_id = prog.add_task("  Embedding", total=n_total) if prog is not None else None
            # Stream nodes in encode_batch_size pages — never hold all node dicts in
            # RAM, and keep each encode call's attention memory (batch x seq^2) bounded.
            for enc_nodes in store.iter_nodes(
                kinds=list(self.index_kinds), batch_size=encode_batch_size
            ):
                enc_texts = [_build_index_text(n) for n in enc_nodes]
                # The page is already sized to encode_batch_size (iter_nodes above),
                # so this hands the model one bounded batch — no sub-batching needed.
                enc_vecs = self.embedder.embed_texts(enc_texts)

                if discover_similar and chunk_pair_vecs is not None:
                    enc_arr = np.asarray(enc_vecs, dtype=np.float32)
                    for node, vec in zip(enc_nodes, enc_arr, strict=True):
                        if node["id"].startswith("chunk:"):
                            chunk_pair_ids.append(node["id"])
                            chunk_pair_vecs[chunk_vec_idx] = vec
                            chunk_vec_idx += 1

                ids = [n["id"] for n in enc_nodes]

                # On wipe builds the table starts empty — skip delete to avoid
                # scanning a growing fragment list (O(n²) slowdown). On incremental
                # builds, delete stale rows before re-adding.
                if not wipe:
                    pred = " OR ".join([f"id = '{_escape(nid)}'" for nid in ids])
                    tbl.delete(pred)

                rows = [
                    {
                        "id": n["id"],
                        "kind": n["kind"],
                        "name": n["name"],
                        "title": n.get("title") or "",
                        "file_path": n.get("file_path") or "",
                        "text": text,
                        "vector": vec,
                    }
                    for n, text, vec in zip(enc_nodes, enc_texts, enc_vecs, strict=True)
                ]
                pending_rows.extend(rows)

                if len(pending_rows) >= write_batch_size:
                    tbl.add(pending_rows)
                    indexed += len(pending_rows)
                    pending_rows = []

                if prog is not None and task_id is not None:
                    prog.advance(task_id, len(enc_nodes))

        if pending_rows:
            tbl.add(pending_rows)
            indexed += len(pending_rows)

        self._tbl = tbl

        # SIMILAR_TO edge discovery — blocked BLAS matmul over the compact matrix.
        similar_edges_added = 0
        if discover_similar and chunk_pair_ids and chunk_pair_vecs is not None:
            similar_edges_added = self._discover_similar_edges(
                store,
                tbl,
                chunk_pair_ids,
                chunk_pair_vecs[:chunk_vec_idx],
                k=similar_k,
                threshold=similarity_edge_threshold,
                max_degree=similar_max_degree,
                quiet=quiet,
            )

        return {
            "indexed_rows": indexed,
            "dim": self.embedder.dim,
            "model_name": getattr(self.embedder, "model_name", repr(self.embedder)),
            "table": self.table_name,
            "lancedb_dir": str(self.lancedb_dir),
            "kinds": list(self.index_kinds),
            "similar_edges_added": similar_edges_added,
        }

    # ------------------------------------------------------------------
    # SIMILAR_TO edge discovery
    # ------------------------------------------------------------------

    def _discover_similar_edges(
        self,
        store: GraphStore,
        tbl: Any,
        chunk_ids: list[str],
        chunk_vecs: Any,
        *,
        k: int,
        threshold: float,
        max_degree: int = 0,
        quiet: bool,
        flush_every: int = 1000,
        block_size: int = 512,
    ) -> int:
        """Find semantically similar chunk pairs and write SIMILAR_TO edges.

        Replaces the per-chunk LanceDB ANN loop with a blocked NumPy matmul.
        Since all chunk vectors are L2-normalised by the embedder
        (``normalize_embeddings=True``), cosine similarity equals the dot
        product, so one BLAS SGEMM call per block gives exact similarities with
        no per-query Python↔LanceDB round-trip overhead.

        The ``(block_size × n_chunks)`` sims matrix is clamped adaptively to stay
        under ~256 MB regardless of corpus size.  Pairs above *threshold* are
        emitted as undirected SIMILAR_TO edges (canonicalized as ``(lo_id,
        hi_id)`` where ``lo_id < hi_id`` lexicographically); the SQLite PRIMARY
        KEY on ``(src, rel, dst)`` deduplicates the symmetric pairs.

        When *max_degree* > 0 the scan collects candidates first, then enforces a
        hard per-node cap with a greedy high-similarity selection pass.

        :param store: GraphStore to write edges into.
        :param tbl: Accepted for call-site compatibility; not used.
        :param chunk_ids: Chunk node IDs in the same order as *chunk_vecs*.
        :param chunk_vecs: Float32 ndarray of shape ``(n_chunks, dim)``, L2-normalised.
        :param k: Maximum SIMILAR_TO out-edges per source chunk (0 = unlimited).
        :param threshold: Minimum cosine similarity for a SIMILAR_TO edge (0–1).
        :param max_degree: Cap total SIMILAR_TO edges per node (0 = unlimited).
        :param quiet: Suppress progress output.
        :param flush_every: Flush accumulated edges to SQLite after this many
            (ignored when *max_degree* > 0 — writes are deferred until pruning).
        :param block_size: Source rows per matmul block before adaptive clamping.
        :return: Total number of edges added.
        """
        import heapq  # pylint: disable=import-outside-toplevel

        import numpy as np  # pylint: disable=import-outside-toplevel

        from memory_kg.memorykg import (
            DocEdge,  # pylint: disable=import-outside-toplevel
        )

        if not chunk_ids:
            return 0

        n_chunks = len(chunk_ids)

        # Contiguous float32 is required for BLAS SGEMM.
        X = np.ascontiguousarray(chunk_vecs, dtype=np.float32)

        # Clamp block_size so the (B x N) sims matrix stays under ~256 MB.
        _bytes_per_row = n_chunks * 4
        eff_block = max(64, min(block_size, (256 * 1024 * 1024) // max(_bytes_per_row, 1)))

        # k=0 means no cap — include all neighbours above threshold.
        eff_k = min(k, n_chunks - 1) if k > 0 else n_chunks - 1

        edges: list[DocEdge] = []
        total_edges = 0

        # Per-node degree cap: {node_id: min-heap of (sim, lo_id, hi_id)}
        node_heap: dict[str, list] = {}

        if not quiet:
            from rich.progress import (  # pylint: disable=import-outside-toplevel
                BarColumn,
                MofNCompleteColumn,
                Progress,
                SpinnerColumn,
                TextColumn,
                TimeElapsedColumn,
                TimeRemainingColumn,
            )

            _sim_ctx: contextlib.AbstractContextManager = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                TimeRemainingColumn(),
            )
        else:
            _sim_ctx = contextlib.nullcontext()

        with _sim_ctx as sim_prog:
            sim_task = (
                sim_prog.add_task("  SIMILAR_TO scan", total=n_chunks)
                if sim_prog is not None
                else None
            )

            for block_start in range(0, n_chunks, eff_block):
                block_end = min(block_start + eff_block, n_chunks)

                # (B, dim) @ (dim, N) → (B, N) exact cosine similarities via BLAS.
                sims = X[block_start:block_end] @ X.T

                for i in range(block_end - block_start):
                    src_idx = block_start + i
                    src_id = chunk_ids[src_idx]
                    row = sims[i]

                    row[src_idx] = -1.0  # exclude self-match

                    # All neighbours at or above the threshold.
                    (above,) = np.where(row >= threshold)
                    if not above.size:
                        continue

                    # Keep top-eff_k by similarity (argpartition: O(N), not O(N log N)).
                    if above.size > eff_k:
                        top_idx = np.argpartition(row[above], -eff_k)[-eff_k:]
                        above = above[top_idx]

                    for j in above.tolist():
                        sim = float(row[j])
                        dst_id = chunk_ids[j]
                        lo_id, hi_id = (src_id, dst_id) if src_id < dst_id else (dst_id, src_id)

                        if max_degree > 0:
                            entry = (sim, lo_id, hi_id)
                            for nid in (lo_id, hi_id):
                                h = node_heap.setdefault(nid, [])
                                heapq.heappush(h, entry)
                                if len(h) > max_degree:
                                    heapq.heappop(h)  # drop weakest
                        else:
                            edges.append(
                                DocEdge(
                                    src=lo_id,
                                    rel="SIMILAR_TO",
                                    dst=hi_id,
                                    evidence={"similarity": round(sim, 4)},
                                )
                            )
                            if len(edges) >= flush_every:
                                store._upsert_edges(edges)
                                total_edges += len(edges)
                                edges = []

                del sims  # release block memory before next allocation

                if sim_prog is not None and sim_task is not None:
                    sim_prog.advance(sim_task, block_end - block_start)

        if max_degree > 0:
            # Candidate set: union of per-node top-max_degree heaps.
            candidates: dict[tuple[str, str], float] = {}
            for heap in node_heap.values():
                for sim, lo, hi in heap:
                    key = (lo, hi)
                    if key not in candidates or sim > candidates[key]:
                        candidates[key] = sim

            # Hard cap selection: highest-similarity edges first while both
            # endpoints still have degree budget available.
            degree: dict[str, int] = {}
            selected: list[DocEdge] = []
            ordered = sorted(candidates.items(), key=lambda item: item[1], reverse=True)
            for (lo, hi), sim in ordered:
                if degree.get(lo, 0) >= max_degree or degree.get(hi, 0) >= max_degree:
                    continue
                selected.append(
                    DocEdge(
                        src=lo,
                        rel="SIMILAR_TO",
                        dst=hi,
                        evidence={"similarity": round(sim, 4)},
                    )
                )
                degree[lo] = degree.get(lo, 0) + 1
                degree[hi] = degree.get(hi, 0) + 1

            edges = selected

        if edges:
            store._upsert_edges(edges)
            total_edges += len(edges)

        return total_edges

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        k: int = 8,
        seed_kinds: tuple[str, ...] | None = None,
        haystack_files: frozenset[str] | None = None,
    ) -> list[SeedHit]:
        """Semantic vector search.

        :param query: Natural-language query string.
        :param k: Number of results to return.
        :param seed_kinds: If set, restrict the vector search to nodes whose ``kind``
            is in this tuple. Passed as a LanceDB ``WHERE`` filter. Example:
            ``seed_kinds=("document",)`` returns only document-level hits.
        :param haystack_files: If set, restrict seeding to nodes whose ``file_path``
            is in this set. Use to limit search to the per-question haystack (e.g.
            the 50 session files for a LongMemEval question) rather than the full
            corpus. This makes retrieval apples-to-apples with flat per-question
            search approaches like MemPalace.
        :return: List of :class:`SeedHit` ordered by ascending distance.
        """
        tbl = self._get_table()
        qvec = self.embedder.embed_query(query)
        s = tbl.search(qvec).limit(k)
        filters: list[str] = []
        if seed_kinds:
            kind_list = ", ".join(f"'{k}'" for k in seed_kinds)
            filters.append(f"kind IN ({kind_list})")
        if haystack_files:
            file_list = ", ".join(f"'{f}'" for f in haystack_files)
            filters.append(f"file_path IN ({file_list})")
        if filters:
            s = s.where(" AND ".join(filters))
        raw = s.to_list()

        hits: list[SeedHit] = []
        for rank, row in enumerate(raw):
            dist = _extract_distance(row, rank)
            hits.append(
                SeedHit(
                    id=row["id"],
                    kind=row.get("kind", ""),
                    name=row.get("name", ""),
                    title=row.get("title", ""),
                    file_path=row.get("file_path", ""),
                    distance=dist,
                    rank=rank,
                )
            )
        return hits

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _open_table(self, *, wipe: bool = False):
        """Open (or create) the LanceDB table, optionally wiping first."""
        import lancedb  # pylint: disable=import-outside-toplevel

        self.lancedb_dir.mkdir(parents=True, exist_ok=True)
        db = lancedb.connect(str(self.lancedb_dir))  # type: ignore[attr-defined]

        if self.table_name in db.list_tables().tables:
            if wipe:
                db.drop_table(self.table_name)
            else:
                return db.open_table(self.table_name)

        import numpy as np  # pylint: disable=import-outside-toplevel

        dummy = {
            "id": "__dummy__",
            "kind": "dummy",
            "name": "__dummy__",
            "title": "",
            "file_path": "",
            "text": "__dummy__",
            "vector": np.zeros((self.embedder.dim,), dtype="float32").tolist(),
        }
        tbl = db.create_table(self.table_name, data=[dummy])
        tbl.delete("id = '__dummy__'")
        return tbl

    def _get_table(self):
        """Return the cached LanceDB table handle, opening it on first access."""
        if self._tbl is None:
            import lancedb  # pylint: disable=import-outside-toplevel

            db = lancedb.connect(str(self.lancedb_dir))  # type: ignore[attr-defined]
            self._tbl = db.open_table(self.table_name)
        return self._tbl

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"SemanticIndex(lancedb_dir={self.lancedb_dir!r}, "
            f"table={self.table_name!r}, embedder={self.embedder!r})"
        )


# ---------------------------------------------------------------------------
# Internal utilities
# ---------------------------------------------------------------------------


def _build_index_text(n: dict) -> str:
    """Build the canonical text document used for embedding a node.

    :param n: Node dict with keys ``kind``, ``name``, ``title``, ``file_path``,
              ``char_start``, and optionally ``text``.
    :return: Newline-joined string suitable for embedding.
    """
    parts = [f"KIND: {n['kind']}"]
    if n.get("title"):
        parts.append(f"TITLE: {n['title']}")
    elif n.get("name"):
        parts.append(f"NAME: {n['name']}")
    if n.get("file_path"):
        parts.append(f"FILE: {n['file_path']}")
    if n.get("text"):
        parts.append("TEXT:\n" + n["text"].strip()[:1024])
    return "\n".join(parts)


def _extract_distance(row: dict, fallback_rank: int) -> float:
    """Extract a distance value from a LanceDB result row."""
    for key in ("_distance", "distance"):
        if key in row and row[key] is not None:
            return float(row[key])
    if "score" in row and row["score"] is not None:
        return 1.0 / (1.0 + float(row["score"]))
    return float(fallback_rank)


def _escape(s: str) -> str:
    """Escape single quotes for use in LanceDB delete predicates."""
    return s.replace("'", "''")
