#!/usr/bin/env python3
"""
index.py

SemanticIndex — LanceDB vector index for MemoryKG.

Mirrors CodeKG's index.py with the following additions:

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
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from kg_utils.embed import DEFAULT_MODEL, resolve_model_path

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

        _tqdm.tqdm.__init__ = _silent_init

        try:
            import tqdm.auto as _tqdm_auto  # pylint: disable=import-outside-toplevel

            if _tqdm_auto.tqdm is not _tqdm.tqdm:
                _tqdm_auto.tqdm.__init__ = _silent_init
        except ImportError:
            pass
    except (ImportError, AttributeError):
        pass


# ---------------------------------------------------------------------------
# Embedder interface (identical to CodeKG — pluggable)
# ---------------------------------------------------------------------------


class Embedder:
    """Abstract embedding backend.

    :param dim: Embedding dimension (must be set by subclass ``__init__``).
    """

    dim: int

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of strings.

        :param texts: Input strings.
        :return: List of float32 vectors, one per input.
        """
        raise NotImplementedError

    def embed_query(self, query: str) -> list[float]:
        """Embed a single query string.

        :param query: Query string.
        :return: Float32 vector.
        """
        return self.embed_texts([query])[0]


class SentenceTransformerEmbedder(Embedder):
    """Local embedding via ``sentence-transformers``.

    Default model is ``BAAI/bge-small-en-v1.5`` (384-dim).  Override by
    passing ``model_name`` directly or setting ``KGRAG_MODEL_DIR`` to redirect
    the model cache system-wide.

    :param model_name: HuggingFace model name or local path.
    """

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        """Load the SentenceTransformer model and determine its embedding dimension."""
        import os  # pylint: disable=import-outside-toplevel

        from sentence_transformers import (  # pylint: disable=import-outside-toplevel
            SentenceTransformer,
        )
        from transformers import (  # pylint: disable=import-outside-toplevel
            logging as hf_logging,
        )

        hf_logging.set_verbosity_error()

        trust_remote = "nomic-ai/" in model_name
        local_path = _local_model_path(model_name)
        _prev_tqdm = os.environ.get("TQDM_DISABLE")
        os.environ["TQDM_DISABLE"] = "1"
        device = os.environ.get("DOCKG_DEVICE", "mps")
        try:
            if local_path.exists():
                self.model = SentenceTransformer(
                    str(local_path), trust_remote_code=trust_remote, device=device
                )
            else:
                try:
                    self.model = SentenceTransformer(
                        model_name,
                        local_files_only=True,
                        trust_remote_code=trust_remote,
                        device=device,
                    )
                except OSError:
                    self.model = SentenceTransformer(
                        model_name, trust_remote_code=trust_remote, device=device
                    )
        finally:
            if _prev_tqdm is None:
                os.environ.pop("TQDM_DISABLE", None)
            else:
                os.environ["TQDM_DISABLE"] = _prev_tqdm
        self.model_name = model_name
        get_dim = getattr(self.model, "get_embedding_dimension", None) or getattr(
            self.model, "get_sentence_embedding_dimension", None
        )
        self.dim: int = (get_dim() if get_dim is not None else None) or 384

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of strings into float32 vectors."""
        import numpy as np  # pylint: disable=import-outside-toplevel

        vecs = self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return [np.asarray(v, dtype="float32").tolist() for v in vecs]

    def embed_query(self, query: str) -> list[float]:
        """Embed a single query string into a float32 vector."""
        import numpy as np  # pylint: disable=import-outside-toplevel

        vec = self.model.encode([query], normalize_embeddings=True)[0]
        return np.asarray(vec, dtype="float32").tolist()

    def __repr__(self) -> str:
        """Return string representation."""
        return f"SentenceTransformerEmbedder(model={self.model_name!r}, dim={self.dim})"


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
        batch_size: int = 1024,
        quiet: bool = True,
        discover_similar: bool = True,
        similar_k: int = 5,
        similarity_edge_threshold: float = 0.85,
        n_workers: int = 8,
    ) -> dict:
        """Build (or rebuild) the vector index from *store*.

        After indexing, optionally discovers SIMILAR_TO edges between
        semantically close chunk nodes and writes them back to *store*.

        :param store: Authoritative :class:`~memory_kg.store.GraphStore`.
        :param wipe: If ``True``, delete all existing vectors first.
        :param batch_size: Number of nodes to embed per batch.
        :param quiet: Suppress progress output.
        :param n_workers: Number of parallel embedding workers (>1 enables
                          multi-process embedding via :class:`~memory_kg.embedder_worker.CorpusEmbedder`).
        :param discover_similar: If ``True``, run SIMILAR_TO edge discovery.
        :param similar_k: k-nearest neighbors to examine per chunk.
        :param similarity_edge_threshold: Minimum cosine similarity to emit a
                                          SIMILAR_TO edge (0–1).
        :return: Stats dict.
        """
        if quiet:
            suppress_ingestion_logging()

        nodes = self._read_nodes(store)
        tbl = self._open_table(wipe=wipe)

        indexed = 0
        # Accumulators for SIMILAR_TO discovery; only populated when discover_similar.
        # Skipping the .extend() calls below saves ~800 MB RAM for a 528K-node
        # corpus at 384 dims.
        all_ids: list[str] = []
        all_vecs: list[list[float]] = []

        # NOTE: n_workers is accepted but Phase 2 embedding runs single-process.
        # Multi-process spawn (CorpusEmbedder) deadlocks on macOS with MPS; the
        # GPU batch loop below is already hardware-accelerated.

        if not quiet:
            from rich.progress import (  # pylint: disable=import-outside-toplevel
                BarColumn,
                MofNCompleteColumn,
                Progress,
                TimeElapsedColumn,
            )

            _progress_ctx: contextlib.AbstractContextManager = Progress(
                "[progress.description]{task.description}",
                BarColumn(),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                transient=True,
            )
        else:
            _progress_ctx = contextlib.nullcontext()

        # On wipe builds the table is empty — accumulate rows and write in large
        # batches to avoid LanceDB fragment churn. On incremental builds, delete
        # + add per embedding batch to handle updates correctly.
        lance_batch_size = 4096
        pending_rows: list[dict] = []

        def _flush(force: bool = False) -> None:
            """Write pending rows to LanceDB; flushes unconditionally when *force* is True."""
            nonlocal indexed
            if not pending_rows:
                return
            if force or len(pending_rows) >= lance_batch_size:
                tbl.add(pending_rows)
                indexed += len(pending_rows)
                pending_rows.clear()

        with _progress_ctx as prog:
            task_id = prog.add_task("  Embedding", total=len(nodes)) if prog is not None else None
            for i in range(0, len(nodes), batch_size):
                chunk = nodes[i : i + batch_size]
                texts = [_build_index_text(n) for n in chunk]
                vecs = self.embedder.embed_texts(texts)

                ids = [n["id"] for n in chunk]

                if not wipe and ids:
                    # Incremental: delete stale vectors before re-adding
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
                    for n, text, vec in zip(chunk, texts, vecs, strict=True)
                ]

                if wipe:
                    pending_rows.extend(rows)
                    _flush()
                else:
                    tbl.add(rows)
                    indexed += len(rows)

                if discover_similar:
                    all_ids.extend(ids)
                    all_vecs.extend(vecs)
                if task_id is not None and prog is not None:
                    prog.advance(task_id, len(rows))

            _flush(force=True)  # write any remaining rows

        self._tbl = tbl

        # SIMILAR_TO edge discovery
        similar_edges_added = 0
        if discover_similar and all_vecs:
            similar_edges_added = self._discover_similar_edges(
                store,
                all_ids,
                all_vecs,
                k=similar_k,
                threshold=similarity_edge_threshold,
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
        node_ids: list[str],
        vecs: list[list[float]],
        *,
        k: int,
        threshold: float,
        quiet: bool,  # pylint: disable=unused-argument
    ) -> int:
        """Find semantically similar chunk pairs and write SIMILAR_TO edges.

        Only chunk nodes participate in SIMILAR_TO (sections and documents
        are already structurally connected via CONTAINS).

        :param store: GraphStore to write edges into.
        :param node_ids: Node IDs in the same order as *vecs*.
        :param vecs: Embedding vectors for each node.
        :param k: k-nearest neighbors to examine.
        :param threshold: Minimum cosine similarity for an edge.
        :param quiet: Suppress progress output.
        :return: Number of edges added.
        """
        from memory_kg.memorykg import (  # pylint: disable=import-outside-toplevel
            DocEdge,
        )

        # Only chunk nodes get SIMILAR_TO edges
        chunk_indices = [i for i, nid in enumerate(node_ids) if nid.startswith("chunk:")]
        if not chunk_indices:
            return 0

        import numpy as np  # pylint: disable=import-outside-toplevel

        chunk_ids = [node_ids[i] for i in chunk_indices]
        chunk_id_to_idx: dict[str, int] = {nid: idx for idx, nid in enumerate(chunk_ids)}
        chunk_vecs = np.asarray([vecs[i] for i in chunk_indices], dtype="float32")

        edges: list[DocEdge] = []
        seen: set[frozenset] = set()

        tbl = self._tbl
        if tbl is None:
            return 0

        from rich.progress import (  # pylint: disable=import-outside-toplevel
            BarColumn,
            MofNCompleteColumn,
            Progress,
            TimeElapsedColumn,
        )

        with Progress(
            "[progress.description]{task.description}",
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            transient=True,
        ) as prog:
            task = prog.add_task("  SIMILAR_TO", total=len(chunk_ids))
            for ci, (nid, qvec) in enumerate(zip(chunk_ids, chunk_vecs, strict=True)):
                raw = tbl.search(qvec.tolist()).limit(k + 1).to_list()
                for row in raw:
                    candidate = row["id"]
                    if candidate == nid or not candidate.startswith("chunk:"):
                        continue
                    pair = frozenset([nid, candidate])
                    if pair in seen:
                        continue
                    seen.add(pair)

                    ci2 = chunk_id_to_idx.get(candidate, -1)
                    if ci2 == -1:
                        continue
                    a, b = chunk_vecs[ci], chunk_vecs[ci2]
                    na, nb = np.linalg.norm(a), np.linalg.norm(b)
                    sim = float(np.dot(a, b) / (na * nb)) if na > 0 and nb > 0 else 0.0

                    if sim >= threshold:
                        edges.append(
                            DocEdge(
                                src=nid,
                                rel="SIMILAR_TO",
                                dst=candidate,
                                evidence={"similarity": round(sim, 4)},
                            )
                        )
                prog.advance(task)

        if edges:
            store._upsert_edges(edges)

        return len(edges)

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

    def _read_nodes(self, store: GraphStore) -> list[dict]:
        """Return all nodes of the configured *index_kinds* from *store*."""
        return store.query_nodes(kinds=list(self.index_kinds))

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
