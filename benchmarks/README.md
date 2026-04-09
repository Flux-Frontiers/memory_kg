# MemoryKG Benchmarks — Reproduction Guide

The `longmemeval_memkg.py` harness evaluates MemoryKG against the LongMemEval-S benchmark (500 questions). It ingests all haystack sessions into a persistent SQLite + LanceDB knowledge graph once, then runs all 500 queries against it.

Retrieval is **pure MemoryKG — no inference, no LLM, no API key required**.

---

## Best Result (as of April 2026)

| Metric | Score |
|---|---|
| R@5 | **97.6%** |
| R@10 | **99.2%** |
| NDCG@10 | **0.936** |
| Misses @10 | 4 |
| LLM required | None |

See [BENCHMARKS.md](BENCHMARKS.md) for the full progression and comparison against published systems.

---

## Setup

```bash
# Install dependencies
poetry install

# Download LongMemEval-S data
mkdir -p /tmp/longmemeval-data
curl -fsSL -o /tmp/longmemeval-data/longmemeval_s_cleaned.json \
  https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/main/longmemeval_s_cleaned.json
```

---

## Quick Start (Best Configuration)

```bash
# Step 1: Build the corpus and KG (one-time, ~5–10 min on Apple Silicon)
poetry run python3 benchmarks/longmemeval/longmemeval_memkg.py prepare \
  /tmp/longmemeval-data/longmemeval_s_cleaned.json \
  --wipe --chunk-strategy heading

# Step 2: Run evaluation (repeatable, reuses built KG, ~15 min)
poetry run python3 benchmarks/longmemeval/longmemeval_memkg.py run \
  /tmp/longmemeval-data/longmemeval_s_cleaned.json \
  --out benchmarks/longmemeval/results.jsonl
```

**Expected output:**
```
Recall@5:  0.976
Recall@10: 0.992
NDCG@10:   0.936
Misses@10: 4
```

The default `run` configuration is the best-validated setup:
- `--k 50` — 50 LanceDB seeds per query (sufficient within the 50-session haystack)
- `--hop 1` — one graph expansion hop
- `--haystack-filter` — restrict seeding to per-question haystack sessions (on by default)

---

## CLI Reference

### `prepare` — Build the corpus and knowledge graph

```bash
poetry run python3 benchmarks/longmemeval/longmemeval_memkg.py prepare \
  /tmp/longmemeval-data/longmemeval_s_cleaned.json \
  [--wipe] \
  [--chunk-strategy heading|paragraph|fixed] \
  [--model MODEL] \
  [--batch N] \
  [--similar]
```

| Flag | Default | Description |
|---|---|---|
| `--wipe` | off | Drop and rebuild the KG from scratch |
| `--chunk-strategy` | `heading` | How to split sessions into chunks |
| `--model` | env `DOCKG_MODEL` | Override the sentence-transformer model |
| `--batch` | 1024 | Embedding batch size |
| `--similar` | off | Discover SIMILAR_TO edges (slow — ~1 hr for full corpus) |

### `run` — Evaluate retrieval

```bash
poetry run python3 benchmarks/longmemeval/longmemeval_memkg.py run \
  /tmp/longmemeval-data/longmemeval_s_cleaned.json \
  [--k N] \
  [--hop N] \
  [--haystack-filter | --no-haystack-filter] \
  [--seed-kinds KINDS] \
  [--rels RELS] \
  [--max-nodes N] \
  [--limit N] \
  [--skip N] \
  [--out FILE] \
  [--ollama [--ollama-model MODEL] [--ollama-url URL] [--ollama-top-n N]]
```

| Flag | Default | Description |
|---|---|---|
| `--k` | `50` | LanceDB seed count before graph expansion |
| `--hop` | `1` | Graph expansion hops from each seed |
| `--haystack-filter` | **on** | Restrict seeding to per-question haystack sessions |
| `--no-haystack-filter` | — | Search the full corpus instead |
| `--seed-kinds` | all kinds | Comma-separated node kinds to seed from (e.g. `chunk`) |
| `--rels` | `CONTAINS,NEXT,REFERENCES,SIMILAR_TO,HAS_TOPIC,MENTIONS_ENTITY,HAS_KEYWORD` | Edge types to traverse |
| `--max-nodes` | `1000` | Cap on ranked nodes returned per query |
| `--limit` | `0` (all) | Stop after N questions |
| `--skip` | `0` | Skip first N questions |
| `--out` | auto | Output JSONL path |
| `--ollama` | off | Enable local LLM reranker via Ollama |
| `--ollama-model` | `qwen3:4b-instruct` | Ollama model name |
| `--ollama-url` | `http://localhost:11434` | Ollama server URL |
| `--ollama-top-n` | `20` | Candidates sent to reranker |

### `all` — Prepare + run in one step

```bash
poetry run python3 benchmarks/longmemeval/longmemeval_memkg.py all \
  /tmp/longmemeval-data/longmemeval_s_cleaned.json \
  --wipe --chunk-strategy heading \
  --out benchmarks/longmemeval/results.jsonl
```

---

## Common Recipes

```bash
# Full-corpus search (no haystack filter) — comparable to naive vector-only baselines
poetry run python3 benchmarks/longmemeval/longmemeval_memkg.py run \
  /tmp/longmemeval-data/longmemeval_s_cleaned.json \
  --no-haystack-filter --k 150 \
  --out benchmarks/longmemeval/results_full_corpus.jsonl

# Pure semantic (no graph) — hop=0 ablation
poetry run python3 benchmarks/longmemeval/longmemeval_memkg.py run \
  /tmp/longmemeval-data/longmemeval_s_cleaned.json \
  --hop 0 \
  --out benchmarks/longmemeval/results_hop0.jsonl

# Quick sanity check on 20 questions
poetry run python3 benchmarks/longmemeval/longmemeval_memkg.py run \
  /tmp/longmemeval-data/longmemeval_s_cleaned.json \
  --limit 20 --out benchmarks/longmemeval/results_smoke.jsonl

# With local LLM reranker (Ollama must be running)
poetry run python3 benchmarks/longmemeval/longmemeval_memkg.py run \
  /tmp/longmemeval-data/longmemeval_s_cleaned.json \
  --ollama --ollama-model qwen3:4b-instruct \
  --out benchmarks/longmemeval/results_ollama.jsonl
```

---

## Rendering Results

The `render_results.py` script compares multiple JSONL runs side-by-side and generates `BENCHMARKS_COMPARISON.md`. It runs automatically at the end of each `run` or `all` invocation.

To run manually:

```bash
poetry run python3 benchmarks/render_results.py benchmarks/longmemeval/results*.jsonl
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DOCKG_MODEL` | `BAAI/bge-small-en-v1.5` | Sentence-transformer model for embeddings |
| `DOCKG_DEVICE` | `mps` | Embedding device (`mps`, `cuda`, `cpu`) |

---

## Requirements

- Python 3.10+
- `poetry install` (all dependencies managed)
- ~300 MB disk for LongMemEval data
- ~2–3 GB disk for the built KG (23,867 sessions)
- No API key. No cloud. No GPU required (CPU works; MPS recommended on Apple Silicon).
