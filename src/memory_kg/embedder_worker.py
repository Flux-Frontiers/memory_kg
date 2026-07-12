#!/usr/bin/env python3
"""
embedder_worker.py

CorpusEmbedder — Stage 3 of the multipass analysis pipeline.

Thin re-export of :mod:`kg_utils.corpus_embedder`, the canonical multi-process,
device-safe corpus embedding engine shared across the KGModule stack (doc_kg,
memory_kg, diary_kg). This file used to carry its own — stale, pre-0.15.9 —
copy of ``CorpusEmbedder`` with no device pinning and no GPU fan-out guard;
see CHANGELOG.md for the incident history. Import from here for backward
compatibility, or from ``kg_utils.corpus_embedder`` directly in new code.

Usage::

    from memory_kg.embedder_worker import CorpusEmbedder

    embedder = CorpusEmbedder(n_workers=4, device="cpu")
    cache = embedder.embed(texts, metadata)
    embedder.save_cache(cache, Path("embeddings.json"))

Author: Eric G. Suchanek, PhD
"""

from __future__ import annotations

import os

from kg_utils.corpus_embedder import CorpusEmbedder, EmbeddingCache

__all__ = ["PIPELINE_MODEL", "CorpusEmbedder", "EmbeddingCache"]

#: Default embedding model for the multipass pipeline.
#: Reads ``DOCKG_MODEL`` env var (same as ``DEFAULT_MODEL`` in memorykg.py)
#: so the global model setting applies to both the core build and pipeline stages.
PIPELINE_MODEL: str = os.environ.get("DOCKG_MODEL", "BAAI/bge-small-en-v1.5")
