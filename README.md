[![CI](https://github.com/Flux-Frontiers/memory_kg/actions/workflows/publish.yml/badge.svg)](https://github.com/Flux-Frontiers/memory_kg/actions/workflows/publish.yml)
[![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![License: Elastic-2.0](https://img.shields.io/badge/License-Elastic%202.0-blue.svg)](https://www.elastic.co/licensing/elastic-license)
[![Version](https://img.shields.io/badge/version-0.4.0-blue.svg)](https://github.com/Flux-Frontiers/memory_kg/releases)
[![Poetry](https://img.shields.io/endpoint?url=https://python-poetry.org/badge/v0.json)](https://python-poetry.org/)
[![DOI](https://zenodo.org/badge/1205364687.svg)](https://zenodo.org/badge/latestdoi/1205364687)

**MemoryKG** — A Hybrid Knowledge Graph for Conversational Memory and Document Corpora

*Author: Eric G. Suchanek, PhD — Flux-Frontiers, Liberty TWP, OH*

---

## TL;DR

MemoryKG is the **highest-scoring memory system on LongMemEval-S that uses no LLM, no API key, and no cloud inference at any stage** — 98.4% Recall@5, 99.4% Recall@10, 0.943 NDCG@10. It matches MemoryPalace's best clean LLM-free score and outperforms every system that requires an LLM at query time except MemoryPalace's (partially test-tuned) perfect run.

| System | LongMemEval R@5 | LLM at query time | Cost / query |
|---|--:|---|--:|
| MemoryPalace hybrid v4 + Haiku (500q) | 100% | Yes (Claude Haiku) | $$ |
| MemoryPalace hybrid v4 held-out (450q) | 98.4% | None | $0 |
| **MemoryKG (this work)** | **98.4%** | **None** | **$0** |
| MemoryPalace hybrid v3 + Haiku rerank | 99.4% | Yes (Claude Haiku) | $$ |
| Supermemory ASMR | ~99% | Yes (undisclosed) | $$ |
| MemoryPalace hybrid v2 | 98.4% | None | $0 |
| Mastra | 94.9% | Yes (GPT-5-mini) | $$ |
| MemoryPalace raw ChromaDB | 96.6% | None | $0 |
| Hindsight | 91.4% | Yes (Gemini-3) | $$ |
| Supermemory (production) | ~85% | Yes (undisclosed) | $$ |
| Stella (dense retriever) | ~85% | None | $0 |
| BM25 (sparse baseline) | ~70% | None | $0 |

With the sibling boost enabled, **recall_all@10 reaches 98.6%** — meaning MemoryKG retrieves *every* required session for 493 of 500 questions without any LLM. No published system reports this metric; we track it because multi-session coverage is the real test of memory completeness.

The field has been over-engineering retrieval. A graph-augmented index with correct search-space scoping matches the best LLM-free result in the field at a fraction of the complexity.

---

## Why It Wins

Most "memory" systems flatten a session into a single embedding and lean on an LLM at query time to rerank what they retrieve. MemoryKG does the opposite: it preserves session structure as a typed graph, then uses that structure as the ranking signal.

1. **Finer granularity.** Sessions are chunked by heading, not embedded as 2,000-word blobs. A 150-word chunk about "Dr. Chen's appointment" is dramatically more discriminative than the session it lives in.
2. **Structural expansion.** A `HAS_TOPIC` or `MENTIONS_ENTITY` edge from a weakly-matching chunk surfaces strongly-linked neighbors that pure cosine similarity never finds.
3. **Score-first ranking.** Graph proximity breaks ties *within* a vector-quality band — never across one. Good seeds get amplified; bad seeds don't get rescued.
4. **Kind-aware ranking.** Chunk matches outrank entity stubs outrank synthetic topic summaries. Flat vector stores treat every document equally.
5. **Search-space scoping.** When the benchmark defines a per-question candidate pool, MemoryKG honours it (`haystack_files=...`). This was the +11 pp fix that closed the gap to the inference-based leaderboard.

**No LLM. No API key. No cloud round-trip. Runs on Apple Silicon (MPS), CUDA, or CPU.**

---

## What MemoryKG Is

A **deterministic, explainable knowledge graph** built from conversational logs and document corpora (Markdown, plain text). MemoryKG semantically chunks text, extracts topics/entities/keywords, links them through typed edges, stores everything in SQLite, and adds a LanceDB vector index as an *acceleration layer* — not the source of truth.

Structure is treated as ground truth. Semantic search is a tool, not the system. The result is a searchable, auditable representation that supports precise navigation, source-grounded passage extraction, and downstream LLM reasoning — a practical foundation for **Knowledge-Graph RAG (KGRAG)**.

MemoryKG shares its architecture with [PyCodeKG](https://github.com/Flux-Frontiers/code_kg) (Python codebases) and [DocKG](https://github.com/Flux-Frontiers/doc_kg) (general document corpora).

---

## Features

- **Semantic chunking** — Multiple strategies: `heading` (one chunk per `## Section`), `fixed`, `sentence_group`, `semantic` (embedding-boundary detection)
- **Deterministic knowledge graph** — SQLite-backed canonical store with typed nodes and provenance-tracked edges
- **Relation extraction** — Topics, named entities, keywords; co-occurrence and similarity edges built automatically
- **Hybrid query model** — Semantic seeding (LanceDB) + structural expansion (graph traversal) + score-first ranking
- **Haystack-scoped search** — Restrict vector seeding to a per-question candidate pool for benchmark-grade precision
- **Passage packing** — Source-grounded text passages with headings, ready to paste into an LLM prompt
- **Coverage analysis & temporal snapshots** — Per-document metrics, hot chunks, orphan detection, version-over-version diffs
- **Parallel ingestion** — `--workers N` parallel Phase 1 parsing for large corpora
- **MCP server** — Four tools for AI agent integration (`graph_stats`, `query_docs`, `pack_docs`, `get_node`)
- **Streamlit web app** — Interactive graph browser, hybrid query UI, and passage pack explorer

---

## Quick Start

```bash
# Index a corpus (SQLite + LanceDB in one step; wipe is the default)
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
# Full pipeline: parse → SQLite graph → LanceDB index (wipe is default)
memorykg build --repo docs/

# Granular steps for large corpora
memorykg build-graph --repo docs/   # SQLite only
memorykg build-index                 # LanceDB from existing SQLite

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
memorykg snapshot save 0.4.0 && memorykg snapshot diff 0.3.1 0.4.0
memorykg viz                                       # Streamlit graph browser
memorykg mcp --repo docs/                          # MCP server for AI agents
```

See [docs/cli-reference.md](docs/cli-reference.md) for every flag.

---

## Reproducing the Benchmark Result

```bash
# 1. Install
poetry install

# 2. Download LongMemEval-S
mkdir -p /tmp/longmemeval-data
curl -fsSL -o /tmp/longmemeval-data/longmemeval_s_cleaned.json \
  https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/main/longmemeval_s_cleaned.json

# 3. Build the corpus + KG (BGE-small-en-v1.5, heading chunks)
poetry run python3 benchmarks/longmemeval/longmemeval_memkg.py prepare \
  /tmp/longmemeval-data/longmemeval_s_cleaned.json \
  --wipe --chunk-strategy heading

# 4. Run evaluation (haystack filter and k=50 are now defaults)
poetry run python3 benchmarks/longmemeval/longmemeval_memkg.py run \
  /tmp/longmemeval-data/longmemeval_s_cleaned.json \
  --out benchmarks/longmemeval/results_bge_haystack.jsonl

# Expected: R@5=98.4%  R@10=99.4%  NDCG@10=0.943  Misses@10=3
```

**Hardware tested:** Apple M5 Max MacBook Pro, 64 GB RAM. Also runs on CUDA and pure CPU (`MEMORYKG_DEVICE=cpu`).

---

## Knowledge Graph Schema

### Node kinds

| Kind | Description |
|---|---|
| `document` | A source `.md` or `.txt` file (or a session log) |
| `section` | A heading-delimited section within a document |
| `chunk` | A semantically coherent text passage within a section |
| `topic` | A topic extracted from chunk text |
| `entity` | A named entity (person, place, organization, concept) |
| `keyword` | A keyword or key phrase from a chunk |

### Edge types

| Type | Description |
|---|---|
| `CONTAINS` | Parent → child (document→section, section→chunk) |
| `NEXT` | Sequential ordering between same-level nodes |
| `REFERENCES` | A chunk references another document or section |
| `SIMILAR_TO` | Semantic similarity between chunks (LanceDB-derived) |
| `HAS_TOPIC` | Chunk → topic association |
| `MENTIONS_ENTITY` | Chunk → named entity association |
| `HAS_KEYWORD` | Chunk → keyword association |
| `CO_OCCURS_WITH` | Co-occurrence between topics/entities within a chunk |

---

## MCP Integration

Once the MCP server is running, your AI agent has four tools:

```
graph_stats()                        # node/edge counts by kind
query_docs("authentication flow")    # hybrid semantic + structural search
pack_docs("configuration reference") # source-grounded passages as Markdown
get_node("chunk:intro:overview")     # fetch a single node by ID
```

**Claude Code / Kilo Code** — `.mcp.json` in repo root:

```json
{
  "mcpServers": {
    "memorykg": {
      "command": "memorykg-mcp",
      "args": ["--repo", "."]
    }
  }
}
```

**GitHub Copilot** — `.vscode/mcp.json`:

```json
{
  "servers": {
    "memorykg": {
      "type": "stdio",
      "command": "memorykg-mcp",
      "args": ["--repo", "."]
    }
  }
}
```

See [docs/MCP.md](docs/MCP.md) for Claude Desktop, Cline, SSE transport, and troubleshooting.

---

## Python API

```python
from memory_kg import MemoryKG

kg = MemoryKG(corpus_root="docs/", chunk_strategy="heading")
kg.build(wipe=True)

# Hybrid query
result = kg.query("deployment configuration", k=8, hop=1)
for node in result.nodes:
    print(node["id"], node["name"])

# Haystack-scoped query (per-question candidate pool — benchmark mode)
result = kg.query("Dr. Chen's recommendation",
                  k=50, hop=1,
                  haystack_files=["session_2024_01_12.md", "session_2024_01_19.md"])

# Passage pack for LLM context
pack = kg.pack("authentication flow")
pack.save("context.md")
```

---

## Storage Layout

```
.memorykg/
  graph.sqlite      # SQLite knowledge graph (nodes + edges)
  lancedb/          # LanceDB vector index
  snapshots/        # Temporal snapshots (JSON)
```

Add `.memorykg/` to `.gitignore`.

---

## Documentation

| Doc | Contents |
|---|---|
| [docs/installation.md](docs/installation.md) | Detailed install, dev setup, entry points, config |
| [docs/cli-reference.md](docs/cli-reference.md) | Full CLI reference with all options |
| [docs/ingestion.md](docs/ingestion.md) | Build pipeline architecture |
| [docs/MCP.md](docs/MCP.md) | MCP server setup for all clients |
| [docs/CHEATSHEET.md](docs/CHEATSHEET.md) | MCP tool query patterns and examples |
| [docs/SNAPSHOTS.md](docs/SNAPSHOTS.md) | Snapshot workflow and diff guide |
| [benchmarks/BENCHMARKS.md](benchmarks/BENCHMARKS.md) | Full LongMemEval progression (75.8% → 98.4%), recall_all analysis, integrity notes |

---

## Citation

If you use MemoryKG in your research or project, please cite it:

[![DOI](https://zenodo.org/badge/1205364687.svg)](https://zenodo.org/badge/latestdoi/1205364687)

**APA**

> Suchanek, E. G. (2026). *MemoryKG: Hybrid Semantic-Graph Knowledge Base for Conversational Memory* (Version 0.4.0) [Software]. Flux-Frontiers. https://github.com/Flux-Frontiers/memory_kg

**BibTeX**

```bibtex
@software{suchanek_memory_kg,
  author    = {Suchanek, Eric G.},
  title     = {{MemoryKG}: Hybrid Semantic-Graph Knowledge Base for Conversational Memory},
  version   = {0.4.0},
  year      = {2026},
  publisher = {Flux-Frontiers},
  url       = {https://github.com/Flux-Frontiers/memory_kg},
  doi       = {10.5281/zenodo.TBD},
}
```
---

## License

[Elastic License 2.0](LICENSE) — free for non-commercial and internal use; commercial hosting or redistribution requires a license from Flux-Frontiers.
