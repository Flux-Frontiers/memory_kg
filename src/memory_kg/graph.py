#!/usr/bin/env python3
"""
graph.py

DocGraph — pure corpus extraction class.

Mirrors the role of CodeGraph in CodeKG: wraps parse_corpus() with a
cached, object-oriented interface.  No I/O, no persistence, no embeddings.

Author: Eric G. Suchanek, PhD
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from pathlib import Path

from memory_kg.memorykg import DocEdge, DocNode, parse_corpus


class DocGraph:
    """
    Pure, deterministic text extraction from a document corpus.

    Wraps the low-level ``parse_corpus`` function with a cached,
    object-oriented interface.  No side effects; calling :meth:`extract`
    twice on the same root returns the same result.

    Example::

        graph = DocGraph("/path/to/corpus")
        graph.extract()
        print(f"{len(graph.nodes)} nodes, {len(graph.edges)} edges")

    :param corpus_root: Path to the corpus root directory.
    :param extensions: File extensions to include (default: .md, .txt, .rst).
    :param exclude: Directory names to exclude from extraction.
    :param chunk_size: Approximate maximum characters per chunk.
    :param chunk_overlap: Character overlap between consecutive chunks.
    :param similarity_threshold: Cosine similarity threshold for semantic split detection.
    :param embedder: Optional embedder for semantic boundary detection.
    :param enable_topics: Emit topic nodes and HAS_TOPIC edges.
    :param enable_entities: Emit entity nodes and MENTIONS_ENTITY edges.
    :param enable_keywords: Emit keyword nodes and HAS_KEYWORD edges.
    :param emit_cooccur: Emit CO_OCCURS_WITH edges among semantic nodes.
    :param cooccur_window: Co-occurrence window metadata.
    :param topic_threshold: Topic confidence threshold.
    :param topics_file: Optional topics file path (JSON/YAML).
    :param n_workers: Number of parallel threads for file parsing (default: 8).
    """

    def __init__(
        self,
        corpus_root: str | Path,
        *,
        extensions: set[str] | None = None,
        exclude: set[str] | None = None,
        chunk_strategy: str = "semantic",
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        similarity_threshold: float = 0.75,
        embedder=None,
        enable_topics: bool = True,
        enable_entities: bool = True,
        enable_keywords: bool = True,
        emit_cooccur: bool = False,
        cooccur_window: int = 1,
        topic_threshold: float = 0.2,
        topics_file: str | None = None,
        n_workers: int = 8,
    ) -> None:
        """Configure the corpus extraction pipeline; extraction is deferred until :meth:`extract`."""
        self.corpus_root: Path = Path(corpus_root).resolve()
        self.extensions = extensions
        self.exclude: set[str] = exclude or set()
        self.chunk_strategy = chunk_strategy
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.similarity_threshold = similarity_threshold
        self.embedder = embedder
        self.enable_topics = enable_topics
        self.enable_entities = enable_entities
        self.enable_keywords = enable_keywords
        self.emit_cooccur = emit_cooccur
        self.cooccur_window = cooccur_window
        self.topic_threshold = topic_threshold
        self.topics_file = topics_file
        self.n_workers = n_workers

        self._nodes: list[DocNode] | None = None
        self._edges: list[DocEdge] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, *, force: bool = False) -> DocGraph:
        """Run corpus extraction (cached after first call).

        :param force: Re-extract even if already cached.
        :return: self (for chaining)
        """
        if self._nodes is None or force:
            self._nodes, self._edges = parse_corpus(
                self.corpus_root,
                extensions=self.extensions,
                exclude=self.exclude,
                chunk_strategy=self.chunk_strategy,
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
                similarity_threshold=self.similarity_threshold,
                embedder=self.embedder,
                enable_topics=self.enable_topics,
                enable_entities=self.enable_entities,
                enable_keywords=self.enable_keywords,
                emit_cooccur=self.emit_cooccur,
                cooccur_window=self.cooccur_window,
                topic_threshold=self.topic_threshold,
                topics_file=self.topics_file,
                n_workers=self.n_workers,
            )
        return self

    def extract_streaming(
        self,
        on_batch: Callable[[list[DocNode], list[DocEdge]], None],
        *,
        batch_size: int = 5000,
    ) -> None:
        """Run extraction, flushing nodes/edges to *on_batch* instead of caching them.

        Use this in place of :meth:`extract` for corpora large enough that holding
        every node in memory before writing is undesirable (LongMemEval-scale, hundreds
        of thousands of nodes). Nothing is cached on this instance afterward — the
        :attr:`nodes`/:attr:`edges` properties and :meth:`stats` are unavailable for a
        streaming extraction; read counts back from wherever *on_batch* persisted them.

        :param on_batch: Called with each batch of newly parsed nodes/edges, in
            parsing-completion order. Typically a callback that upserts into storage.
        :param batch_size: Approximate number of pending nodes buffered before flushing.
        """
        parse_corpus(
            self.corpus_root,
            extensions=self.extensions,
            exclude=self.exclude,
            chunk_strategy=self.chunk_strategy,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            similarity_threshold=self.similarity_threshold,
            embedder=self.embedder,
            enable_topics=self.enable_topics,
            enable_entities=self.enable_entities,
            enable_keywords=self.enable_keywords,
            emit_cooccur=self.emit_cooccur,
            cooccur_window=self.cooccur_window,
            topic_threshold=self.topic_threshold,
            topics_file=self.topics_file,
            n_workers=self.n_workers,
            on_batch=on_batch,
            stream_batch_size=batch_size,
        )

    @property
    def nodes(self) -> list[DocNode]:
        """Extracted nodes (calls :meth:`extract` if needed)."""
        if self._nodes is None:
            self.extract()
        assert self._nodes is not None
        return self._nodes

    @property
    def edges(self) -> list[DocEdge]:
        """Extracted edges (calls :meth:`extract` if needed)."""
        if self._edges is None:
            self.extract()
        assert self._edges is not None
        return self._edges

    def result(self) -> tuple[list[DocNode], list[DocEdge]]:
        """Return the extracted nodes and edges as a tuple.

        :return: ``(nodes, edges)`` tuple, triggering extraction if not yet done.
        """
        return self.nodes, self.edges

    def stats(self) -> dict:
        """Return a summary of extracted nodes and edges by kind/relation.

        :return: dict with ``node_counts``, ``edge_counts``, ``total_nodes``,
                 ``total_edges``.
        """
        node_counts: Counter = Counter(n.kind for n in self.nodes)
        edge_counts: Counter = Counter(e.rel for e in self.edges)
        return {
            "corpus_root": str(self.corpus_root),
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "node_counts": dict(node_counts),
            "edge_counts": dict(edge_counts),
        }

    def __repr__(self) -> str:
        """Return string representation showing extraction state."""
        extracted = self._nodes is not None
        if extracted:
            return (
                f"DocGraph(corpus_root={self.corpus_root!r}, "
                f"nodes={len(self._nodes)}, edges={len(self._edges)})"  # ty: ignore[invalid-argument-type]
            )
        return f"DocGraph(corpus_root={self.corpus_root!r}, not yet extracted)"
