[![CI](https://github.com/Flux-Frontiers/memory_kg/actions/workflows/ci.yml/badge.svg)](https://github.com/Flux-Frontiers/memory_kg/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![License: Elastic-2.0](https://img.shields.io/badge/License-Elastic%202.0-blue.svg)](https://www.elastic.co/licensing/elastic-license)
[![Version](https://img.shields.io/badge/version-0.9.0-blue.svg)](https://github.com/Flux-Frontiers/memory_kg/releases)
[![Poetry](https://img.shields.io/endpoint?url=https://python-poetry.org/badge/v0.json)](https://python-poetry.org/)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21282909.svg)](https://doi.org/10.5281/zenodo.21282909)

**MemoryKG** — A Hybrid Knowledge Graph for Conversational Memory and Document Corpora

*Author: Eric G. Suchanek, PhD — Flux-Frontiers, Liberty TWP, OH*

---

## TL;DR

MemoryKG achieves **96.3% tier-1 retrieval recall on the ConvoMem benchmark at k=20** (500 tier-1 items; 88.7% averaged across all 1,897 items spanning tiers 1–4), exceeding MemPal's published 92.9% tier-1 baseline by +3.4 pp. No LLM, no API key, no cloud inference at any stage. Full write-up: [`benchmarks/convomem/convomem_article.pdf`](benchmarks/convomem/convomem_article.pdf).

Recall is measured by substring containment in the top-10 retrieved nodes: an evidence message counts as found if its text appears verbatim in (or contains) any retrieved node — lenient toward retrieval, but it cannot be fooled by paraphrase.

On the LongMemEval-S benchmark, MemoryKG scores **98.2% Recall@5, 99.2% Recall@10, 0.954 NDCG@10** with zero inference (re-verified 2026-08-26). Against MemoryPalace hybrid v2 — the best LLM-free configuration either system has — it wins at depth (NDCG@10 0.954 vs 0.934, R@10 99.2% vs 99.0%) and trails by 0.2 pp at R@5 (98.2% vs 98.4%). LLM-augmented systems still rank higher at R@5 (MemoryPalace v4 + Haiku at 100%, v3 + Haiku rerank at 99.4%, Supermemory ASMR at ~99%); MemoryKG closes most of that gap without paying the inference cost. Full write-up: [`benchmarks/longmemeval/longmemeval_article.pdf`](benchmarks/longmemeval/longmemeval_article.pdf).

| System | LongMemEval R@5 | LLM at query time | Cost / query |
|---|--:|---|--:|
| MemoryPalace hybrid v4 + Haiku (500q) | 100% | Yes (Claude Haiku) | $$ |
| MemoryPalace hybrid v4 held-out (450q) | 98.4% | None | $0 |
| **MemoryKG (this work)** | **98.2%** | **None** | **$0** |
| MemoryPalace hybrid v3 + Haiku rerank | 99.4% | Yes (Claude Haiku) | $$ |
| Supermemory ASMR | ~99% | Yes (undisclosed) | $$ |
| MemoryPalace hybrid v2 | 98.4% | None | $0 |
| Mastra | 94.9% | Yes (GPT-5-mini) | $$ |
| MemoryPalace raw ChromaDB | 96.6% | None | $0 |
| Hindsight | 91.4% | Yes (Gemini-3) | $$ |
| Supermemory (production) | ~85% | Yes (undisclosed) | $$ |
| Stella (dense retriever) | ~85% | None | $0 |
| BM25 (sparse baseline) | ~70% | None | $0 |

With the sibling boost enabled on LongMemEval, **recall_all@10 reaches 98.6%** — meaning MemoryKG retrieves *every* required session for 493 of 500 questions without any LLM. No published system reports this metric; we track it because multi-session coverage is the real test of memory completeness.

The field has been over-engineering retrieval. A graph-augmented index with correct search-space scoping matches the best LLM-free result in the field at a fraction of the complexity.

---

## Why It Works

Most "memory" systems flatten a session into a single embedding and lean on an LLM at query time to rerank what they retrieve. MemoryKG does the opposite: it preserves session structure as a typed graph, then uses that structure as the ranking signal.

1. **Finer granularity.** Sessions are chunked by heading, not embedded as 2,000-word blobs. A 150-word chunk about "Dr. Chen's appointment" is dramatically more discriminative than the session it lives in.
2. **Structural expansion.** A `HAS_TOPIC` or `MENTIONS_ENTITY` edge from a weakly-matching chunk surfaces strongly-linked neighbors that pure cosine similarity never finds.
3. **Score-first ranking.** Graph proximity breaks ties *within* a vector-quality band — never across one. Good seeds get amplified; bad seeds don't get rescued.
4. **Kind-aware ranking.** Chunk matches outrank entity stubs outrank synthetic topic summaries. Flat vector stores treat every document equally.
5. **Search-space scoping.** When the benchmark defines a per-question candidate pool, MemoryKG honours it (`haystack_files=...`). This was the +11 pp fix that narrowed the gap to the inference-based leaderboard.

**No LLM. No API key. No cloud round-trip. Runs on Apple Silicon (MPS), CUDA, or CPU.**

---

## What MemoryKG Is

A **deterministic, explainable knowledge graph** built from conversational logs and document corpora (Markdown, plain text). MemoryKG semantically chunks text, extracts topics/entities/keywords, links them through typed edges, stores everything in SQLite, and adds a sqlite-vec vector index as an *acceleration layer* — not the source of truth.

Structure is treated as ground truth. Semantic search is a tool, not the system. The result is a searchable, auditable representation that supports precise navigation, source-grounded passage extraction, and downstream LLM reasoning — a practical foundation for **Knowledge-Graph RAG (KGRAG)**.

MemoryKG shares its architecture with [PyCodeKG](https://github.com/Flux-Frontiers/pycode_kg) (Python codebases) and [DocKG](https://github.com/Flux-Frontiers/doc_kg) (general document corpora).

---

## Features

- **Semantic chunking** — Multiple strategies: `heading` (one chunk per `## Section`), `fixed`, `sentence_group`, `semantic` (embedding-boundary detection)
- **Deterministic knowledge graph** — SQLite-backed canonical store with typed nodes and provenance-tracked edges
- **Relation extraction** — Topics, named entities, keywords; co-occurrence and similarity edges built automatically
- **Hybrid query model** — Semantic seeding (sqlite-vec) + structural expansion (graph traversal) + score-first ranking
- **Haystack-scoped search** — Restrict vector seeding to a per-question candidate pool for benchmark-grade precision
- **Passage packing** — Source-grounded text passages with headings, ready to paste into an LLM prompt
- **Coverage analysis & temporal snapshots** — Per-document metrics, hot chunks, orphan detection, version-over-version diffs
- **Parallel ingestion** — `--workers N` parallel Phase 1 parsing for large corpora
- **MCP server** — Four tools for AI agent integration (`graph_stats`, `query_docs`, `pack_docs`, `get_node`)
- **Streamlit web app** — Interactive graph browser, hybrid query UI, and passage pack explorer

---

## Quick Start

```bash
# Index a corpus (SQLite + sqlite-vec in one step; wipe is the default)
memorykg build --repo docs/

# Natural-language query — returns ranked chunks
memorykg query "authentication flow"

# Source-grounded passage pack — paste straight into an LLM prompt
memorykg pack "configuration reference" --fmt md --out context.md
```

---

## Installation

```bash
pip install 'memory-kg @ git+https://github.com/Flux-Frontiers/memory_kg.git'
```

See [docs/installation.md](docs/installation.md) for editable installs, dev setup, and offline model caching.

---

## Usage

### Build the knowledge graph

```bash
# Full pipeline: parse → SQLite graph → sqlite-vec index (wipe is default)
memorykg build --repo docs/

# Granular steps for large corpora
memorykg build-graph --repo docs/   # SQLite only
memorykg build-index                 # vector index from existing SQLite

# Incremental update — keep existing data
memorykg build --repo docs/ --update

# Parallelise Phase 1 parsing
memorykg build --repo docs/ --workers 8

# Exclude directories
memorykg build --repo docs/ --exclude-dir archive --exclude-dir vendor
```

### Query and pack passages

```bash
# Hybrid query — semantic seed + graph expansion
memorykg query "deployment configuration"

# Tune top-K and expansion hops
memorykg query "API authentication" --k 12 --hop 2

# Pack as Markdown for LLM context injection
memorykg pack "error handling strategies" --fmt md --out context.md
```

### Analyze, snapshot, visualize

```bash
memorykg analyze --repo docs/                      # corpus health report
memorykg snapshot save 0.4.1 && memorykg snapshot diff 0.4.0 0.4.1
memorykg viz                                       # Streamlit graph browser
memorykg mcp --repo docs/                          # MCP server for AI agents
```

See [docs/cli-reference.md](docs/cli-reference.md) for every flag.

---

## Reproducing the Benchmarks

### LongMemEval-S — 98.2% R@5, 99.2% R@10

Full write-up: [`benchmarks/longmemeval/longmemeval_article.pdf`](benchmarks/longmemeval/longmemeval_article.pdf)

```bash
# 1. Install
poetry install

# 2. Download LongMemEval-S
mkdir -p /tmp/longmemeval-data
curl -fsSL -o /tmp/longmemeval-data/longmemeval_s_cleaned.json \
  https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/main/longmemeval_s_cleaned.json

# 3. Build the corpus + KG (BGE-small-en-v1.5, heading chunks).
#    Parse -> SQLite, embed -> JSONL cache, index from cache; --keep-cache
#    resumes an interrupted build without re-embedding.
poetry run python3 benchmarks/longmemeval/longmemeval_memkg.py prepare \
  /tmp/longmemeval-data/longmemeval_s_cleaned.json \
  --wipe --chunk-strategy heading

# 4. Run evaluation (haystack filter and k=50 are now defaults)
poetry run python3 benchmarks/longmemeval/longmemeval_memkg.py run \
  /tmp/longmemeval-data/longmemeval_s_cleaned.json \
  --out benchmarks/longmemeval/results_20260826_bge_haystack.jsonl

# Expected: R@1=90.4%  R@5=98.2%  R@10=99.2%
#           recall_all@10=98.8%  NDCG@10=0.954  misses@10=4/500
```

### ConvoMem — 96.3% Tier-1 Recall Across 1,897 Items

Full write-up: [`benchmarks/convomem/convomem_article.pdf`](benchmarks/convomem/convomem_article.pdf)

```bash
# Run all four evidence tiers (top-10, hop=1, BGE-small-en-v1.5)
poetry run python3 benchmarks/convomem/convomem_bench.py --limit 1000 --tier 1
poetry run python3 benchmarks/convomem/convomem_bench.py --limit 1000 --tier 2
poetry run python3 benchmarks/convomem/convomem_bench.py --limit 1000 --tier 3
poetry run python3 benchmarks/convomem/convomem_bench.py --limit 1000 --tier 4

# Expected: 96.3% tier-1 recall@20 (500 items); 88.7% averaged across all 1,897 items in tiers 1-4 (~20 min)
```

**Hardware tested:** Apple M5 Max MacBook Pro, 64 GB RAM. Also runs on CUDA and pure CPU (`MEMORYKG_DEVICE=cpu`).

---

## Documentation

| Doc | Contents |
|---|---|
| [docs/installation.md](docs/installation.md) | Detailed install, dev setup, entry points, config |
| [docs/cli-reference.md](docs/cli-reference.md) | Full CLI reference with all options |
| [docs/ingestion.md](docs/ingestion.md) | Build pipeline architecture, **node kinds & edge types** |
| [docs/python-api.md](docs/python-api.md) | `MemoryKG` class — build, query, haystack-scoping, passage packing |
| [docs/MCP.md](docs/MCP.md) | MCP server setup (Claude Code, Copilot, Claude Desktop, Cline) |
| [docs/CHEATSHEET.md](docs/CHEATSHEET.md) | MCP tool query patterns and examples |
| [docs/SNAPSHOTS.md](docs/SNAPSHOTS.md) | Snapshot workflow and diff guide |
| [benchmarks/RESULTS_SUMMARY.md](benchmarks/RESULTS_SUMMARY.md) | **Canonical LongMemEval-S numbers** (2026-08-26 re-run), MemPalace head-to-head, progression |
| [benchmarks/README.md](benchmarks/README.md) | All four benchmarks at a glance, task descriptions, reproduce commands |
| [benchmarks/longmemeval/longmemeval_article.pdf](benchmarks/longmemeval/longmemeval_article.pdf) | LongMemEval-S report (PDF): 99.2% R@10, 100% R@30, 0.954 NDCG@10 (2026-08-26 re-run) |
| [benchmarks/convomem/convomem_article.pdf](benchmarks/convomem/convomem_article.pdf) | ConvoMem report (PDF): 96.3% tier-1 retrieval recall across 1,897 items |

---

## Citation

If you use MemoryKG in your research or project, please cite it:

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21282909.svg)](https://doi.org/10.5281/zenodo.21282909)

**APA**

> Suchanek, E. G. (2026). *MemoryKG: Hybrid Semantic-Graph Knowledge Base for Conversational Memory* (Version 0.9.0) [Software]. Flux-Frontiers. https://github.com/Flux-Frontiers/memory_kg

**BibTeX**

```bibtex
@software{suchanek_memory_kg,
  author    = {Suchanek, Eric G.},
  title     = {{MemoryKG}: Hybrid Semantic-Graph Knowledge Base for Conversational Memory},
  version   = {0.9.0},
  year      = {2026},
  publisher = {Flux-Frontiers},
  url       = {https://github.com/Flux-Frontiers/memory_kg},
  doi       = {10.5281/zenodo.21282909},
}
```
---

## License

[Elastic License 2.0](LICENSE) — free for non-commercial and internal use; commercial hosting or redistribution requires a license from Flux-Frontiers.
