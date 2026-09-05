#!/usr/bin/env python3
"""
index.py

SemanticIndex — sqlite-vec vector index for MemoryKG.

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
"""

# pylint: disable=C0415

from __future__ import annotations

import contextlib
import gzip
import json
import logging
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, TextIO, cast

from kg_utils.embed import DEFAULT_MODEL, resolve_model_path
from kg_utils.embedder import Embedder, SentenceTransformerEmbedder
from kg_utils.vector_backend import SqliteVecBackend
from rich.console import Console

# Metadata persisted alongside each vector. ``id`` is implicit.
# ``title`` and ``file_path`` are load-bearing: :meth:`SemanticIndex.search`
# reads both off every hit, and they are also the columns the ``seed_kinds`` /
# ``haystack_files`` prefilters run against. The backend's default column set
# does not include them, so a default-configured port would silently return
# blank titles and paths — and filter against columns that do not exist.
_META_COLUMNS = ("kind", "name", "title", "file_path", "text")

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
    for name in ("sentence_transformers", "transformers", "huggingface_hub"):
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

_DEFAULT_KINDS = ("document", "section", "chunk", "topic", "entity", "keyword")


def _is_jsonl_cache(path: Path) -> bool:
    """Return ``True`` when *path* names a streaming JSONL embedding cache."""
    return path.suffix == ".jsonl" or path.name.endswith(".jsonl.gz")


def _open_text_auto(path: Path, mode: str) -> TextIO:
    """Open *path* as text, transparently gzipping when it ends in ``.gz``."""
    if path.suffix == ".gz":
        return cast(TextIO, gzip.open(path, mode, encoding="utf-8"))
    return cast(TextIO, open(path, mode, encoding="utf-8"))


def _mps_cache_evictor() -> Callable[[], None] | None:
    """Return a callable that releases cached GPU blocks, or ``None`` when N/A.

    The MPS allocator caches freed blocks and never returns them to the system,
    so a long streaming embed grows unbounded ("other allocations") until the
    machine swaps or the run is killed.  Calling the returned evictor once per
    batch keeps GPU memory flat.  Returns ``None`` on CPU-only machines and when
    torch is unavailable, so callers can skip the per-batch call entirely.
    """
    try:
        import torch  # pylint: disable=import-outside-toplevel

        if torch.cuda.is_available():
            return torch.cuda.empty_cache
        if hasattr(torch, "mps") and torch.backends.mps.is_available():
            return torch.mps.empty_cache
    except Exception:
        return None
    return None


class SemanticIndex:
    """sqlite-vec-backed semantic vector index for MemoryKG.

    Reads nodes from a :class:`~memory_kg.store.GraphStore`, embeds them, and
    stores the vectors in a single ``vectors.sqlite`` file.  The index is
    **derived and disposable** — it can be rebuilt from SQLite at any time
    without data loss.

    Changed in 0.7.0: the store was a LanceDB directory plus a named table.
    The embedding text built by :func:`_build_index_text` and the SIMILAR_TO
    discovery pass are unchanged — only where the vectors live changed.

    ``search`` uses an exact flat cosine scan (no ANN index): retrieval recall
    is exact, which the benchmark suites depend on.  Search cost grows linearly
    with corpus size but stays well within budget at the scales in use.

    After building the vector index, optionally runs a SIMILAR_TO edge
    discovery pass that writes semantic similarity edges back to the store.

    Example::

        embedder = SentenceTransformerEmbedder()
        idx = SemanticIndex(".memorykg/vectors.sqlite", embedder=embedder)
        idx.build(store, wipe=True)

        hits = idx.search("climate change policy", k=8)
        for h in hits:
            print(h.id, h.distance)

    :param vectors_path: Path to the ``vectors.sqlite`` store.
    :param embedder: Embedding backend.
    :param index_kinds: Node kinds to embed.
    """

    def __init__(
        self,
        vectors_path: str | Path,
        *,
        embedder: Embedder | None = None,
        index_kinds: Sequence[str] = _DEFAULT_KINDS,
    ) -> None:
        """Configure the sqlite-vec semantic index; the store is opened lazily."""
        self.vectors_path = Path(vectors_path)
        self.embedder: Embedder = embedder or SentenceTransformerEmbedder()
        self.index_kinds = tuple(index_kinds)
        self._backend: SqliteVecBackend | None = None

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
        embedded, and written to the store in large batches.  Chunk vectors are
        accumulated into a single pre-allocated ``(n_chunks × dim)`` float32
        matrix so the SIMILAR_TO pass sees a compact array rather than hundreds
        of thousands of loose Python lists.  After indexing, optionally discovers
        SIMILAR_TO edges between semantically close chunk nodes.

        :param store: Authoritative :class:`~memory_kg.store.GraphStore`.
        :param wipe: If ``True``, delete all existing vectors first.
        :param batch_size: Rows buffered per write transaction.
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
        backend = self._open_for_build(wipe=wipe)

        indexed = 0
        # Buffer writes into large batches regardless of the (smaller) encode
        # batch: each upsert runs its own transaction, so many small writes cost
        # one commit apiece.  Floor at 4096.
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

        # A long GPU embed otherwise grows unbounded: the allocator caches freed
        # blocks and never returns them.  Resolved once — the check itself imports
        # torch, so it must not run per batch.
        evict_gpu_cache = _mps_cache_evictor()

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

                # `upsert` deletes any prior rows for these ids and re-inserts.
                # The backend already skips that delete on a freshly wiped store,
                # so the explicit wipe-guard this used to carry is gone — along
                # with its OR-joined `id = '...'` predicate, one term per node.
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
                    indexed += backend.upsert(pending_rows, batch_size=write_batch_size)
                    pending_rows = []

                if evict_gpu_cache is not None:
                    evict_gpu_cache()
                if prog is not None and task_id is not None:
                    prog.advance(task_id, len(enc_nodes))

        if pending_rows:
            indexed += backend.upsert(pending_rows, batch_size=write_batch_size)

        # SIMILAR_TO edge discovery — blocked BLAS matmul over the compact matrix.
        similar_edges_added = 0
        if discover_similar and chunk_pair_ids and chunk_pair_vecs is not None:
            similar_edges_added = self._discover_similar_edges(
                store,
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
            "vectors_path": str(self.vectors_path),
            "kinds": list(self.index_kinds),
            "similar_edges_added": similar_edges_added,
        }

    # ------------------------------------------------------------------
    # Two-phase build: precompute embeddings → build index from cache
    # ------------------------------------------------------------------

    def precompute_embeddings(
        self,
        store: GraphStore,
        out: Path,
        *,
        n_workers: int | None = None,
        batch_size: int = 128,
        device: str | None = None,
        quiet: bool = False,
    ) -> Path:
        """Embed all index nodes into a JSONL cache, writing no vectors to the store.

        Pure embedding pass — the expensive half of :meth:`build`, separated so it
        can be paid once and reused.  Call :meth:`build_from_cache` afterwards to
        populate the vector index from the saved file without re-running the model.

        Routes by device.  A GPU cannot fan out across spawn workers, so MPS/CUDA
        takes the single-process stream, which also reuses the caller's already
        loaded embedder rather than loading a second copy (an MPS double-load is a
        SIGBUS).  CPU takes ``CorpusEmbedder.embed_to_cache``, which is both
        multi-process and bounded: peak memory scales with shard size, not corpus
        size.  Either way vectors are flushed to disk as they are produced, so a
        528k-node corpus never accumulates in RAM.

        :param store: Source :class:`~memory_kg.store.GraphStore`.
        :param out: Output path; must be ``.jsonl`` or ``.jsonl.gz``.
        :param n_workers: Worker processes for the CPU path (default: CPU count / 2).
        :param batch_size: Per-batch embedding size.
        :param device: Embedding device (``"cpu"``/``"mps"``/``"cuda"``); ``None``
            resolves via ``KG_EMBED_DEVICE`` then auto-detect.
        :param quiet: Suppress progress output.
        :raises ValueError: If *out* is not a JSONL path.
        :return: Path to the written cache (*out*).
        """
        if not _is_jsonl_cache(out):
            raise ValueError(
                f"embedding cache must be .jsonl or .jsonl.gz, got: {out.name}. "
                "MemoryKG streams the cache to disk rather than building it in RAM; "
                "a whole-file .json cache would defeat that at corpus scale."
            )

        from kg_utils.embedder import resolve_device  # pylint: disable=import-outside-toplevel

        if resolve_device(device) in {"mps", "cuda"}:
            return self._precompute_embeddings_jsonl_stream(
                store, out, batch_size=batch_size, quiet=quiet
            )
        return self._precompute_embeddings_parallel_stream(
            store,
            out,
            n_workers=n_workers,
            batch_size=batch_size,
            device=device,
            quiet=quiet,
        )

    def _precompute_embeddings_jsonl_stream(
        self,
        store: GraphStore,
        out: Path,
        *,
        batch_size: int,
        quiet: bool,
    ) -> Path:
        """Stream embeddings to JSONL in-process, one node page at a time (GPU path)."""
        if quiet:
            suppress_ingestion_logging()

        out.parent.mkdir(parents=True, exist_ok=True)
        total = store.count_nodes(kinds=list(self.index_kinds))
        model_name = getattr(self.embedder, "model_name", DEFAULT_MODEL)
        dim = int(getattr(self.embedder, "dim", 0) or 0)
        written = 0

        if not quiet:
            Console().print(f"  nodes    : {total:,} to embed  (streaming JSONL)")
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

        evict_gpu_cache = _mps_cache_evictor()

        with _open_text_auto(out, "wt") as f:
            header = {
                "__meta__": {
                    "version": 1,
                    "model": model_name,
                    "dim": dim,
                    "created_at": datetime.now(tz=UTC).isoformat(),
                }
            }
            f.write(json.dumps(header, ensure_ascii=False, separators=(",", ":")) + "\n")

            with _progress_ctx as prog:
                task_id = prog.add_task("  Embedding", total=total) if prog is not None else None
                for enc_nodes in store.iter_nodes(
                    kinds=list(self.index_kinds), batch_size=max(1, int(batch_size))
                ):
                    texts = [_build_index_text(n) for n in enc_nodes]
                    vecs = self.embedder.embed_texts(texts)

                    for n, text, vec in zip(enc_nodes, texts, vecs, strict=True):
                        row = {
                            "id": n["id"],
                            "kind": n["kind"],
                            "name": n["name"],
                            "title": n.get("title") or "",
                            "file_path": n.get("file_path") or "",
                            "text": text,
                            "vector": vec,
                        }
                        f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
                        written += 1

                    f.flush()
                    if evict_gpu_cache is not None:
                        evict_gpu_cache()
                    if prog is not None and task_id is not None:
                        prog.advance(task_id, len(enc_nodes))

        if not quiet:
            size_mb = out.stat().st_size / 1_048_576
            Console().print(
                f"  cache    : {out}  ({written:,} vectors, dim={dim}, {size_mb:,.0f} MB)"
            )
        return out

    def _precompute_embeddings_parallel_stream(
        self,
        store: GraphStore,
        out: Path,
        *,
        n_workers: int | None,
        batch_size: int,
        device: str | None,
        quiet: bool,
    ) -> Path:
        """Embed via the multi-process ``CorpusEmbedder``, streaming to JSONL (CPU path)."""
        from kg_utils.corpus_embedder import (  # pylint: disable=import-outside-toplevel
            CorpusEmbedder,
        )

        if quiet:
            suppress_ingestion_logging()

        texts, metadata = self._read_texts_metadata(store)
        model_name = getattr(self.embedder, "model_name", DEFAULT_MODEL)
        corp_embedder = CorpusEmbedder(
            model_name=model_name,
            n_workers=n_workers,
            batch_size=batch_size,
            device=device,
        )

        if not quiet:
            Console().print(
                f"  nodes    : {len(texts):,} to embed  "
                f"({corp_embedder.n_workers} workers, streaming JSONL)"
            )

        corp_embedder.embed_to_cache(texts, metadata, out_path=out)

        if not quiet:
            size_mb = out.stat().st_size / 1_048_576
            Console().print(f"  cache    : {out}  ({len(texts):,} vectors, {size_mb:,.0f} MB)")
        return out

    def _read_texts_metadata(self, store: GraphStore) -> tuple[list[str], list[dict]]:
        """Read index nodes as aligned ``(texts, metadata)`` ready for embedding.

        Used by the CPU path only, which needs the full work list up front to
        shard it across workers.  The GPU path streams pages instead and never
        calls this.
        """
        nodes = list(store.query_nodes(kinds=list(self.index_kinds)))
        texts = [_build_index_text(n) for n in nodes]
        metadata = [
            {
                "id": n["id"],
                "kind": n["kind"],
                "name": n["name"],
                "title": n.get("title") or "",
                "file_path": n.get("file_path") or "",
            }
            for n in nodes
        ]
        return texts, metadata

    def build_from_cache(
        self,
        store: GraphStore,
        cache_path: Path,
        *,
        wipe: bool = False,
        batch_size: int = 4096,
        quiet: bool = False,
        discover_similar: bool = True,
        similar_k: int = 5,
        similarity_edge_threshold: float = 0.85,
        similar_max_degree: int = 0,
    ) -> dict:
        """Build (or rebuild) the vector index from a pre-computed embedding cache.

        Skips model inference entirely — reads float32 vectors written by
        :meth:`precompute_embeddings` and upserts them straight into the backend,
        one batch at a time, so the cache is never held whole in RAM.

        :param store: :class:`~memory_kg.store.GraphStore` (needed for SIMILAR_TO writes).
        :param cache_path: Path to the JSONL cache.
        :param wipe: If ``True``, delete all existing vectors first.
        :param batch_size: Vector-store write batch size.
        :param quiet: Suppress progress output.
        :param discover_similar: Run SIMILAR_TO edge discovery after indexing.
        :param similar_k: k-nearest neighbours per chunk for SIMILAR_TO discovery.
        :param similarity_edge_threshold: Minimum cosine similarity for a SIMILAR_TO edge.
        :param similar_max_degree: Cap total SIMILAR_TO edges per node (0 = unlimited).
        :raises ValueError: If *cache_path* is not a JSONL cache.
        :return: Stats dict (same schema as :meth:`build`).
        """
        if not _is_jsonl_cache(cache_path):
            raise ValueError(f"embedding cache must be .jsonl or .jsonl.gz, got: {cache_path.name}")

        import numpy as np  # pylint: disable=import-outside-toplevel

        if quiet:
            suppress_ingestion_logging()

        if not quiet:
            size_mb = cache_path.stat().st_size / 1_048_576
            Console().print(f"  cache    : reading {cache_path.name} ({size_mb:,.0f} MB) …")

        backend = self._open_for_build(wipe=wipe)
        indexed = 0
        model_name = "unknown"
        dim = 0
        pending_rows: list[dict[str, Any]] = []
        chunk_pair_ids: list[str] = []
        chunk_vecs_list: list[Any] = []
        write_batch_size = max(1, int(batch_size))

        with _open_text_auto(cache_path, "rt") as f:
            first = f.readline()
            if first:
                first_obj = json.loads(first)
                meta = first_obj.get("__meta__", {}) if isinstance(first_obj, dict) else {}
                model_name = str(meta.get("model") or model_name)
                dim = int(meta.get("dim") or dim)

            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line)
                rid = row["id"]
                vec = row["vector"]
                if not dim:
                    dim = len(vec)

                pending_rows.append(
                    {
                        "id": rid,
                        "kind": row.get("kind", ""),
                        "name": row.get("name", ""),
                        "title": row.get("title") or "",
                        "file_path": row.get("file_path") or "",
                        "text": row.get("text") or "",
                        "vector": vec,
                    }
                )

                if discover_similar and rid.startswith("chunk:"):
                    chunk_pair_ids.append(rid)
                    chunk_vecs_list.append(vec)

                if len(pending_rows) >= write_batch_size:
                    indexed += backend.upsert(pending_rows, batch_size=len(pending_rows))
                    pending_rows = []

        if pending_rows:
            indexed += backend.upsert(pending_rows, batch_size=len(pending_rows))

        similar_edges_added = 0
        if discover_similar and chunk_pair_ids and chunk_vecs_list:
            similar_edges_added = self._discover_similar_edges(
                store,
                chunk_pair_ids,
                np.asarray(chunk_vecs_list, dtype=np.float32),
                k=similar_k,
                threshold=similarity_edge_threshold,
                max_degree=similar_max_degree,
                quiet=quiet,
            )

        return {
            "indexed_rows": indexed,
            "dim": dim,
            "model_name": model_name,
            "vectors_path": str(self.vectors_path),
            "kinds": list(self.index_kinds),
            "similar_edges_added": similar_edges_added,
        }

    # ------------------------------------------------------------------
    # SIMILAR_TO edge discovery
    # ------------------------------------------------------------------

    def _discover_similar_edges(
        self,
        store: GraphStore,
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

        Uses a blocked NumPy matmul rather than per-chunk vector-store queries.
        Since all chunk vectors are L2-normalised by the embedder
        (``normalize_embeddings=True``), cosine similarity equals the dot
        product, so one BLAS SGEMM call per block gives exact similarities with
        no per-query round-trip into the vector store.

        The ``(block_size × n_chunks)`` sims matrix is clamped adaptively to stay
        under ~256 MB regardless of corpus size.  Pairs above *threshold* are
        emitted as undirected SIMILAR_TO edges (canonicalized as ``(lo_id,
        hi_id)`` where ``lo_id < hi_id`` lexicographically); the SQLite PRIMARY
        KEY on ``(src, rel, dst)`` deduplicates the symmetric pairs.

        When *max_degree* > 0 the scan collects candidates first, then enforces a
        hard per-node cap with a greedy high-similarity selection pass.

        :param store: GraphStore to write edges into.
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
            is in this tuple. Compiled into the backend's SQL prefilter, so the
            k nearest are drawn from the matching subset. Example:
            ``seed_kinds=("document",)`` returns only document-level hits.
        :param haystack_files: If set, restrict seeding to nodes whose ``file_path``
            is in this set. Use to limit search to the per-question haystack (e.g.
            the 50 session files for a LongMemEval question) rather than the full
            corpus. This makes retrieval apples-to-apples with flat per-question
            search approaches like MemPalace.
        :return: List of :class:`SeedHit` ordered by ascending distance.
        """
        if self._backend is None and not self.vectors_path.exists():
            raise FileNotFoundError(
                f"vector index not found at '{self.vectors_path}'.\n"
                "Run 'memorykg build' to create it."
            )
        backend = self._get_backend()
        qvec = self.embedder.embed_query(query)
        filters: list[str] = []
        if seed_kinds:
            kind_list = ", ".join(f"'{_escape(kind)}'" for kind in seed_kinds)
            filters.append(f"kind IN ({kind_list})")
        if haystack_files:
            file_list = ", ".join(f"'{_escape(f)}'" for f in sorted(haystack_files))
            filters.append(f"file_path IN ({file_list})")
        raw = backend.search(qvec, k, where=" AND ".join(filters) if filters else None)

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

    def _new_backend(self) -> SqliteVecBackend:
        """Construct (but do not open) the sqlite-vec backend."""
        self.vectors_path.parent.mkdir(parents=True, exist_ok=True)
        return SqliteVecBackend(
            self.vectors_path,
            dim=self.embedder.dim,
            meta_columns=_META_COLUMNS,
        )

    def _get_backend(self) -> SqliteVecBackend:
        """Return the backend for reading, opening it on first use."""
        if self._backend is None:
            self._backend = self._new_backend()
            self._backend.open()
        return self._backend

    def _open_for_build(self, *, wipe: bool) -> SqliteVecBackend:
        """Open the backend for a write pass, re-opening a cached one.

        ``SqliteVecBackend`` decides at ``open()`` whether ``upsert`` needs its
        delete-before-insert dedup — a freshly created or wiped store has
        nothing to replace — and never revisits that verdict.  Re-opening is
        what makes a second build on the same instance correct: without it the
        first build's "fresh" verdict survives, the dedup stays off, and
        re-indexing the same nodes raises ``UNIQUE constraint failed``.

        :param wipe: Drop existing vectors before indexing.
        :return: The open backend.
        """
        if self._backend is None:
            self._backend = self._new_backend()
        else:
            # open() rebinds the connection without closing the old one.
            self._backend.close()
        self._backend.open(wipe=wipe)
        return self._backend

    def count(self) -> int:
        """Return the number of indexed vectors, or 0 when nothing is built."""
        if self._backend is None and not self.vectors_path.exists():
            return 0
        return self._get_backend().count()

    def __repr__(self) -> str:
        """Return string representation."""
        return f"SemanticIndex(vectors_path={self.vectors_path!r}, embedder={self.embedder!r})"


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
    """Extract a distance value from a vector-search result row.

    ``SqliteVecBackend`` returns ``_distance`` (cosine), which is tried first;
    the remaining fallbacks are tolerated so a row from any other backend still
    yields a usable ordering.
    """
    for key in ("_distance", "distance"):
        if key in row and row[key] is not None:
            return float(row[key])
    if "score" in row and row["score"] is not None:
        return 1.0 / (1.0 + float(row["score"]))
    return float(fallback_rank)


def _escape(s: str) -> str:
    """Escape single quotes for embedding in a SQL string literal.

    Still load-bearing after the sqlite-vec port: ``search`` builds its
    ``kind IN (...)`` / ``file_path IN (...)`` prefilter as a SQL predicate
    string, and a path containing an apostrophe would otherwise break it.
    """
    return s.replace("'", "''")
