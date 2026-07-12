"""Tests for embedder_worker.py — PIPELINE_MODEL and the kg_utils re-export.

CorpusEmbedder / EmbeddingCache / _embed_shard / resolve_device now live in
kg_utils (kg_utils.corpus_embedder / kg_utils.embedder); their unit coverage
lives there. This module only tests memory_kg's own surface: PIPELINE_MODEL's
DOCKG_MODEL env-var override, the re-export identity, and the GPU fan-out
guard exercised through memory_kg's own CorpusEmbedder import path.
"""

import os
from pathlib import Path
from unittest.mock import patch

import kg_utils.corpus_embedder as _kg_corpus_embedder
from kg_utils.embedder import resolve_device

from memory_kg.embedder_worker import PIPELINE_MODEL, CorpusEmbedder, EmbeddingCache

# ---------------------------------------------------------------------------
# PIPELINE_MODEL constant
# ---------------------------------------------------------------------------


def test_pipeline_model_constant_value():
    # Default is BAAI/bge-small-en-v1.5; overrideable via DOCKG_MODEL env var.
    expected = os.environ.get("DOCKG_MODEL", "BAAI/bge-small-en-v1.5")
    assert PIPELINE_MODEL == expected


def test_pipeline_model_is_string():
    assert isinstance(PIPELINE_MODEL, str)


def test_pipeline_model_is_non_empty():
    assert len(PIPELINE_MODEL) > 0


# ---------------------------------------------------------------------------
# Re-export identity — CorpusEmbedder/EmbeddingCache must be the actual
# kg_utils classes, not a diverged local copy.
# ---------------------------------------------------------------------------


def test_corpus_embedder_is_kg_utils_class():
    assert CorpusEmbedder is _kg_corpus_embedder.CorpusEmbedder


def test_embedding_cache_is_kg_utils_class():
    assert EmbeddingCache is _kg_corpus_embedder.EmbeddingCache


def test_corpus_embedder_constructs_with_pipeline_model():
    embedder = CorpusEmbedder(PIPELINE_MODEL, n_workers=2, batch_size=32, device="cpu")
    assert embedder.model_name == PIPELINE_MODEL
    assert embedder.device == "cpu"


def test_save_load_cache_roundtrip_via_reexport(tmp_path):
    """Smoke test that the re-exported save_cache/load_cache still work end to end."""
    cache = EmbeddingCache(
        model="test-model",
        dim=4,
        texts=["a", "b"],
        vectors=[[0.1, 0.2, 0.3, 0.4], [0.5, 0.6, 0.7, 0.8]],
        metadata=[{"file_path": "a.md"}, {"file_path": "b.md"}],
    )
    out: Path = tmp_path / "embeddings.json"
    CorpusEmbedder.save_cache(cache, out)
    loaded = CorpusEmbedder.load_cache(out)

    assert loaded.model == cache.model
    assert loaded.texts == cache.texts
    assert loaded.n_vectors == 2


# ---------------------------------------------------------------------------
# resolve_device (re-exported from kg_utils.embedder; memory_kg imports it
# transitively through CorpusEmbedder — verify the wiring, not the logic)
# ---------------------------------------------------------------------------


def test_resolve_device_explicit_arg_wins(monkeypatch):
    monkeypatch.setenv("KG_EMBED_DEVICE", "cuda")
    assert resolve_device("cpu") == "cpu"


def test_corpus_embedder_device_defaults_to_resolved_value(monkeypatch):
    monkeypatch.setenv("KG_EMBED_DEVICE", "cpu")
    embedder = CorpusEmbedder()
    assert embedder.device == "cpu"


# ---------------------------------------------------------------------------
# GPU devices force single-process embedding (the OOM-prevention guard) —
# this is the property that made the memory_kg fork dangerous before the
# kg_utils migration, so it's worth re-verifying through memory_kg's import.
# ---------------------------------------------------------------------------


def test_embed_forces_sequential_on_mps_even_with_many_texts_and_workers():
    embedder = CorpusEmbedder(n_workers=4, device="mps")
    texts = [f"text {i}" for i in range(200)]

    with (
        patch.object(embedder, "_embed_sequential", return_value=[[0.0]] * 200) as seq,
        patch.object(embedder, "_embed_parallel") as par,
    ):
        embedder.embed(texts)

    seq.assert_called_once()
    par.assert_not_called()


def test_embed_uses_parallel_on_cpu_with_enough_texts_and_workers():
    embedder = CorpusEmbedder(n_workers=4, device="cpu")
    texts = [f"text {i}" for i in range(200)]

    with (
        patch.object(embedder, "_embed_sequential") as seq,
        patch.object(embedder, "_embed_parallel", return_value=[[0.0]] * 200) as par,
    ):
        embedder.embed(texts)

    par.assert_called_once()
    seq.assert_not_called()
