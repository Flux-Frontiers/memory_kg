"""Tests for embedder_worker.py — PIPELINE_MODEL, EmbeddingCache, save/load roundtrip."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

from memory_kg.embedder_worker import (
    PIPELINE_MODEL,
    CorpusEmbedder,
    EmbeddingCache,
    _embed_shard,
    _resolve_device,
)

# ---------------------------------------------------------------------------
# PIPELINE_MODEL constant
# ---------------------------------------------------------------------------


def test_pipeline_model_constant_value():
    # Default is BAAI/bge-small-en-v1.5; overrideable via DOCKG_MODEL env var.
    import os

    expected = os.environ.get("DOCKG_MODEL", "BAAI/bge-small-en-v1.5")
    assert PIPELINE_MODEL == expected


def test_pipeline_model_is_string():
    assert isinstance(PIPELINE_MODEL, str)


def test_pipeline_model_is_non_empty():
    assert len(PIPELINE_MODEL) > 0


# ---------------------------------------------------------------------------
# EmbeddingCache creation
# ---------------------------------------------------------------------------


def test_embedding_cache_basic_creation():
    cache = EmbeddingCache(
        model="test-model",
        dim=32,
        texts=["hello", "world"],
        vectors=[[0.1] * 32, [0.2] * 32],
    )
    assert cache.model == "test-model"
    assert cache.dim == 32
    assert cache.texts == ["hello", "world"]
    assert len(cache.vectors) == 2


def test_embedding_cache_n_vectors_property():
    vectors = [[float(i)] * 8 for i in range(5)]
    cache = EmbeddingCache(
        model="m",
        dim=8,
        texts=[f"text{i}" for i in range(5)],
        vectors=vectors,
    )
    assert cache.n_vectors == 5


def test_embedding_cache_n_vectors_empty():
    cache = EmbeddingCache(model="m", dim=0, texts=[], vectors=[])
    assert cache.n_vectors == 0


def test_embedding_cache_n_vectors_matches_vectors_list():
    n = 7
    cache = EmbeddingCache(
        model="m",
        dim=4,
        texts=[f"t{i}" for i in range(n)],
        vectors=[[0.0] * 4 for _ in range(n)],
    )
    assert cache.n_vectors == n


def test_embedding_cache_auto_generates_created_at():
    """created_at is auto-generated when left blank."""
    cache = EmbeddingCache(model="m", dim=4, texts=[], vectors=[])
    assert cache.created_at != ""
    assert len(cache.created_at) > 0


def test_embedding_cache_auto_created_at_is_iso_format():
    """created_at should be parseable as an ISO timestamp."""
    from datetime import datetime

    cache = EmbeddingCache(model="m", dim=4, texts=[], vectors=[])
    # Should not raise
    dt = datetime.fromisoformat(cache.created_at)
    assert dt is not None


def test_embedding_cache_explicit_created_at_preserved():
    ts = "2025-01-15T12:00:00+00:00"
    cache = EmbeddingCache(model="m", dim=4, texts=[], vectors=[], created_at=ts)
    assert cache.created_at == ts


def test_embedding_cache_default_metadata_is_empty_list():
    cache = EmbeddingCache(model="m", dim=4, texts=["t"], vectors=[[0.0] * 4])
    assert cache.metadata == []


def test_embedding_cache_with_metadata():
    meta = [{"file_path": "a.md"}, {"file_path": "b.md"}]
    cache = EmbeddingCache(
        model="m",
        dim=4,
        texts=["t1", "t2"],
        vectors=[[0.0] * 4, [1.0] * 4],
        metadata=meta,
    )
    assert cache.metadata == meta


# ---------------------------------------------------------------------------
# save_cache / load_cache roundtrip
# ---------------------------------------------------------------------------


def _make_cache(n: int = 5, dim: int = 8) -> EmbeddingCache:
    """Create a synthetic EmbeddingCache for testing."""
    texts = [f"text number {i}" for i in range(n)]
    vectors = [[float(i * 0.1 + j * 0.01) for j in range(dim)] for i in range(n)]
    metadata = [{"index": i, "source": f"doc{i}.md"} for i in range(n)]
    return EmbeddingCache(
        model="test-model-v1",
        dim=dim,
        texts=texts,
        vectors=vectors,
        metadata=metadata,
        created_at="2025-04-01T00:00:00+00:00",
    )


def test_save_cache_creates_file(tmp_path):
    cache = _make_cache()
    out = tmp_path / "embeddings.json"
    CorpusEmbedder.save_cache(cache, out)
    assert out.exists()


def test_save_cache_creates_parent_dirs(tmp_path):
    cache = _make_cache()
    out = tmp_path / "nested" / "dir" / "embeddings.json"
    CorpusEmbedder.save_cache(cache, out)
    assert out.exists()


def test_save_cache_writes_valid_json(tmp_path):
    cache = _make_cache()
    out = tmp_path / "embeddings.json"
    CorpusEmbedder.save_cache(cache, out)

    with open(out, encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, dict)


def test_load_cache_roundtrip_model(tmp_path):
    cache = _make_cache()
    out = tmp_path / "embeddings.json"
    CorpusEmbedder.save_cache(cache, out)
    loaded = CorpusEmbedder.load_cache(out)

    assert loaded.model == cache.model


def test_load_cache_roundtrip_dim(tmp_path):
    cache = _make_cache(dim=16)
    out = tmp_path / "embeddings.json"
    CorpusEmbedder.save_cache(cache, out)
    loaded = CorpusEmbedder.load_cache(out)

    assert loaded.dim == 16


def test_load_cache_roundtrip_texts(tmp_path):
    cache = _make_cache(n=3)
    out = tmp_path / "embeddings.json"
    CorpusEmbedder.save_cache(cache, out)
    loaded = CorpusEmbedder.load_cache(out)

    assert loaded.texts == cache.texts


def test_load_cache_roundtrip_vectors(tmp_path):
    cache = _make_cache(n=4, dim=8)
    out = tmp_path / "embeddings.json"
    CorpusEmbedder.save_cache(cache, out)
    loaded = CorpusEmbedder.load_cache(out)

    assert len(loaded.vectors) == 4
    for orig, loaded_v in zip(cache.vectors, loaded.vectors):
        assert len(loaded_v) == 8
        for a, b in zip(orig, loaded_v):
            assert abs(a - b) < 1e-6


def test_load_cache_roundtrip_metadata(tmp_path):
    cache = _make_cache(n=3)
    out = tmp_path / "embeddings.json"
    CorpusEmbedder.save_cache(cache, out)
    loaded = CorpusEmbedder.load_cache(out)

    assert loaded.metadata == cache.metadata


def test_load_cache_roundtrip_n_vectors(tmp_path):
    cache = _make_cache(n=6)
    out = tmp_path / "embeddings.json"
    CorpusEmbedder.save_cache(cache, out)
    loaded = CorpusEmbedder.load_cache(out)

    assert loaded.n_vectors == 6


def test_load_cache_roundtrip_created_at(tmp_path):
    cache = _make_cache()
    out = tmp_path / "embeddings.json"
    CorpusEmbedder.save_cache(cache, out)
    loaded = CorpusEmbedder.load_cache(out)

    assert loaded.created_at == cache.created_at


def test_save_load_empty_cache(tmp_path):
    cache = EmbeddingCache(
        model="empty-model",
        dim=0,
        texts=[],
        vectors=[],
        created_at="2025-01-01T00:00:00+00:00",
    )
    out = tmp_path / "empty.json"
    CorpusEmbedder.save_cache(cache, out)
    loaded = CorpusEmbedder.load_cache(out)

    assert loaded.n_vectors == 0
    assert loaded.texts == []
    assert loaded.model == "empty-model"


def test_save_cache_json_structure(tmp_path):
    """Verify the JSON file contains all expected top-level keys."""
    cache = _make_cache(n=2)
    out = tmp_path / "embeddings.json"
    CorpusEmbedder.save_cache(cache, out)

    with open(out, encoding="utf-8") as f:
        data = json.load(f)

    for key in ("model", "dim", "n_vectors", "created_at", "texts", "metadata", "embeddings"):
        assert key in data, f"Missing key in saved JSON: {key}"


def test_save_cache_n_vectors_matches(tmp_path):
    """Saved n_vectors field should match len(vectors)."""
    cache = _make_cache(n=3)
    out = tmp_path / "embeddings.json"
    CorpusEmbedder.save_cache(cache, out)

    with open(out, encoding="utf-8") as f:
        data = json.load(f)

    assert data["n_vectors"] == 3
    assert len(data["embeddings"]) == 3


def test_save_load_cache_gzip_roundtrip(tmp_path):
    """A .gz suffix writes and reads a gzip-compressed cache."""
    cache = _make_cache(n=4, dim=8)
    out = tmp_path / "embeddings.json.gz"
    CorpusEmbedder.save_cache(cache, out)
    assert out.exists()

    loaded = CorpusEmbedder.load_cache(out)
    assert loaded.model == cache.model
    assert loaded.texts == cache.texts
    assert loaded.n_vectors == cache.n_vectors


# ---------------------------------------------------------------------------
# _resolve_device
# ---------------------------------------------------------------------------


def test_resolve_device_explicit_arg_wins(monkeypatch):
    monkeypatch.setenv("KG_EMBED_DEVICE", "cuda")
    assert _resolve_device("cpu") == "cpu"


def test_resolve_device_env_var_used_when_no_explicit_arg(monkeypatch):
    monkeypatch.setenv("KG_EMBED_DEVICE", "mps")
    assert _resolve_device(None) == "mps"


def test_resolve_device_normalizes_case_and_whitespace(monkeypatch):
    monkeypatch.delenv("KG_EMBED_DEVICE", raising=False)
    assert _resolve_device("  CPU  ") == "cpu"


def test_resolve_device_falls_back_to_auto_detect(monkeypatch):
    monkeypatch.delenv("KG_EMBED_DEVICE", raising=False)
    resolved = _resolve_device(None)
    assert resolved in {"cpu", "mps", "cuda", None}


# ---------------------------------------------------------------------------
# GPU devices force single-process embedding (the OOM-prevention guard)
# ---------------------------------------------------------------------------


def test_embed_forces_sequential_on_mps_even_with_many_texts_and_workers():
    """A GPU device can't be shared across spawn workers; embed() must not
    fan out into _embed_parallel regardless of corpus size or n_workers."""
    embedder = CorpusEmbedder(n_workers=4, device="mps")
    texts = [f"text {i}" for i in range(200)]

    with (
        patch.object(embedder, "_embed_sequential", return_value=[[0.0]] * 200) as seq,
        patch.object(embedder, "_embed_parallel") as par,
    ):
        embedder.embed(texts)

    seq.assert_called_once()
    par.assert_not_called()


def test_embed_forces_sequential_on_cuda():
    embedder = CorpusEmbedder(n_workers=4, device="cuda")
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


def test_corpus_embedder_device_defaults_to_resolved_value(monkeypatch):
    monkeypatch.setenv("KG_EMBED_DEVICE", "cpu")
    embedder = CorpusEmbedder()
    assert embedder.device == "cpu"


# ---------------------------------------------------------------------------
# resolve_model_path (canonical location: kg_utils.embed)
# ---------------------------------------------------------------------------


def test_resolve_model_path_available_from_kg_utils():
    """The local-model-path resolver is centralized in kg_utils.embed."""
    from kg_utils.embed import resolve_model_path

    result = resolve_model_path("BAAI/bge-small-en-v1.5")
    assert isinstance(result, Path)
    assert "bge-small-en-v1.5" in str(result)


# ---------------------------------------------------------------------------
# _embed_shard model resolution and device pinning
# ---------------------------------------------------------------------------


def _make_fake_st(dim: int = 4):
    """Return a mock SentenceTransformer that produces deterministic vectors."""
    fake = MagicMock()
    fake.encode.return_value = np.zeros((1, dim), dtype="float32")
    # load_sentence_transformer() ends with `model = model.to(device)`; the
    # mock must return itself so the configured `.encode` survives the move.
    fake.to.return_value = fake
    return fake


def test_embed_shard_uses_local_path_when_exists(tmp_path):
    """When the resolved local path exists, ST is loaded with local_files_only=True."""
    model_name = "BAAI/bge-small-en-v1.5"
    fake_local = tmp_path / "BAAI" / "bge-small-en-v1.5"
    fake_local.mkdir(parents=True)

    fake_st = _make_fake_st()
    with (
        patch("kg_utils.embedder.resolve_model_path", return_value=fake_local),
        patch("sentence_transformers.SentenceTransformer", return_value=fake_st) as mock_cls,
    ):
        _embed_shard((["hello"], model_name, 8, 0, None, None))

    assert mock_cls.call_args.kwargs.get("local_files_only") is True


def test_embed_shard_falls_back_to_network_when_local_files_only_fails(tmp_path):
    """When local_files_only raises OSError, falls back to a plain network load."""
    model_name = "BAAI/bge-small-en-v1.5"
    fake_st = _make_fake_st()
    missing = tmp_path / "nonexistent"

    def side_effect(name, **kwargs):
        if kwargs.get("local_files_only"):
            raise OSError("not cached")
        return fake_st

    with (
        patch("kg_utils.embedder.resolve_model_path", return_value=missing),
        patch("sentence_transformers.SentenceTransformer", side_effect=side_effect) as mock_cls,
    ):
        _embed_shard((["hello"], model_name, 8, 0, None, None))

    assert mock_cls.call_count == 2


def test_embed_shard_returns_correct_shape(tmp_path):
    """_embed_shard returns (worker_id, list_of_vectors) of expected length."""
    texts = ["a", "b", "c"]
    model_name = "BAAI/bge-small-en-v1.5"
    fake_st = MagicMock()
    fake_st.encode.side_effect = lambda batch, **kw: np.zeros((len(batch), 4), dtype="float32")
    fake_st.to.return_value = fake_st  # survive load_sentence_transformer's model.to(device)
    missing = tmp_path / "nonexistent"

    with (
        patch("kg_utils.embedder.resolve_model_path", return_value=missing),
        patch("sentence_transformers.SentenceTransformer", return_value=fake_st),
    ):
        worker_id, vectors = _embed_shard((texts, model_name, 8, 7, None, None))

    assert worker_id == 7
    assert len(vectors) == 3
    assert len(vectors[0]) == 4


def test_embed_shard_pins_device_when_given(tmp_path):
    """A concrete device pins the loaded model via model.to(device) —
    what keeps N parallel CPU workers from each auto-selecting MPS."""
    texts = ["a"]
    model_name = "BAAI/bge-small-en-v1.5"
    fake_st = MagicMock()
    fake_st.encode.side_effect = lambda batch, **kw: np.zeros((len(batch), 4), dtype="float32")
    fake_st.to.return_value = fake_st
    missing = tmp_path / "nonexistent"

    with (
        patch("kg_utils.embedder.resolve_model_path", return_value=missing),
        patch("sentence_transformers.SentenceTransformer", return_value=fake_st),
    ):
        _embed_shard((texts, model_name, 8, 0, None, "cpu"))

    fake_st.to.assert_called_with("cpu")


def test_embed_shard_reports_progress(tmp_path):
    """A non-None progress_queue receives per-batch counts and a None sentinel."""
    texts = ["a", "b", "c", "d", "e"]
    model_name = "BAAI/bge-small-en-v1.5"
    fake_st = MagicMock()
    fake_st.encode.side_effect = lambda batch, **kw: np.zeros((len(batch), 4), dtype="float32")
    fake_st.to.return_value = fake_st
    missing = tmp_path / "nonexistent"
    queue = MagicMock()

    with (
        patch("kg_utils.embedder.resolve_model_path", return_value=missing),
        patch("sentence_transformers.SentenceTransformer", return_value=fake_st),
    ):
        _embed_shard((texts, model_name, 2, 0, queue, None))

    # 3 batches of size <= 2 (2, 2, 1) plus a trailing None sentinel.
    assert queue.put.call_count == 4
    assert queue.put.call_args_list[-1].args == (None,)
