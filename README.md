[![CI](https://github.com/Flux-Frontiers/memory_kg/actions/workflows/publish.yml/badge.svg)](https://github.com/Flux-Frontiers/memory_kg/actions/workflows/publish.yml)
[![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![License: Elastic-2.0](https://img.shields.io/badge/License-Elastic%202.0-blue.svg)](https://www.elastic.co/licensing/elastic-license)
[![Version](https://img.shields.io/badge/version-0.1.0-blue.svg)](https://github.com/Flux-Frontiers/memory_kg/releases)
[![Poetry](https://img.shields.io/endpoint?url=https://python-poetry.org/badge/v0.json)](https://python-poetry.org/)

**MemoryKG** — A Hybrid Knowledge Graph for Document Corpora and Conversational Memory

*Author: Eric G. Suchanek, PhD*
*Flux-Frontiers, Liberty TWP, OH*

---

## Overview

MemoryKG constructs a **deterministic, explainable knowledge graph** from a corpus of Markdown and plain-text documents. It semantically chunks text, discovers structural and semantic relationships between sections and chunks, stores them in SQLite, and augments retrieval with vector embeddings via LanceDB.

Structure is treated as **ground truth**; semantic search is strictly an acceleration layer. The result is a searchable, auditable representation of a document corpus that supports precise navigation, contextual passage extraction, and downstream reasoning — making it an ideal retrieval engine for LLMs and a practical foundation for **Knowledge-Graph RAG (KGRAG)**, in contrast to embedding-only approaches.

MemoryKG uses the same architecture as [CodeKG](https://github.com/Flux-Frontiers/code_kg) and [DocKG](https://github.com/Flux-Frontiers/doc_kg) but adds a **conversational memory layer** — ingesting and indexing agent turns, consolidating them into summaries, and enabling semantic recall across sessions.

---

## Features

- **Semantic chunking** — Multiple strategies: `heading` (one chunk per `## Section`), `fixed` (size-bounded), `sentence_group`, and `semantic` (embedding-boundary detection)
- **Deterministic knowledge graph** — SQLite-backed canonical store with typed nodes and provenance-tracked edges
- **Relation extraction** — Topics, named entities, and keywords extracted from each chunk; co-occurrence and similarity edges built automatically
- **Hybrid query model** — Semantic seeding (LanceDB embeddings) + structural expansion (graph traversal)
- **Passage packing** — Extract context-rich text passages grounded to source documents with headings
- **Semantic coverage analysis** — Per-document metrics, hot chunks, orphan detection, and overall corpus health report
- **Temporal snapshots** — Save and diff graph metrics over time; compare coverage across corpus versions
- **Conversational memory** — Auto-ingest Claude Code session turns via hooks; periodic consolidation into summaries; semantic recall across sessions
- **MCP server** — Four tools for AI agent integration (`graph_stats`, `query_docs`, `pack_docs`, `get_node`)
- **Streamlit web app** — Interactive graph browser, hybrid query UI, and passage pack explorer

---

## Quick Start

```bash
# Index a document corpus (SQLite + LanceDB in one step)
memorykg build docs/

# Natural-language query — returns ranked document chunks
memorykg query "authentication flow"

# Source-grounded passage pack — paste straight into an LLM prompt
memorykg pack "configuration reference" --format md --out context.md
```

---

## Usage Examples

### Build the knowledge graph

```bash
# Full pipeline: parse documents → SQLite graph → LanceDB semantic index
memorykg build docs/

# Build only the SQLite graph (no embeddings)
memorykg build-graph docs/

# Build only the LanceDB index from an existing graph
memorykg build-index

# Rebuild from scratch (wipe is the default)
memorykg build docs/

# Incremental update — keep existing data
memorykg build docs/ --update

# Use heading-based chunking (one chunk per ## section — faster, better for conversations)
memorykg build docs/ --chunk-strategy heading

# Exclude specific directories
memorykg build docs/ --exclude-dir dir1 --exclude-dir dir2
```

### Query and pack passages

```bash
# Hybrid query — semantic seed + graph expansion
memorykg query "deployment configuration"

# Increase top-K and expansion hops
memorykg query "API authentication" --k 12 --hop 2

# Pack passages as Markdown for LLM context injection
memorykg pack "error handling strategies" --format md --out context.md

# Pack as JSON
memorykg pack "database schema" --format json
```

### Analyze corpus health

```bash
# Full analysis report (Markdown + JSON snapshot)
memorykg analyze docs/

# Output to a specific file
memorykg analyze docs/ --output analysis/report.md

# Quiet mode for CI — exits non-zero on issues
memorykg analyze docs/ --quiet
```

### Snapshot the knowledge graph over time

```bash
# Save a snapshot tagged with a version
memorykg snapshot save 0.1.0

# List all saved snapshots
memorykg snapshot list

# Show detail for a specific snapshot
memorykg snapshot show 0.1.0

# Diff two snapshots
memorykg snapshot diff 0.1.0 0.2.0
```

### Install hooks

```bash
# Install git pre-commit hook (rebuilds index and snapshots before each commit)
memorykg install-hooks --repo .

# Also install Claude Code auto-ingest hooks for this repo
memorykg install-hooks --repo . --claude

# Install Claude Code hooks globally (all repos)
memorykg install-hooks --global
```

Claude Code hooks auto-ingest every session turn into the AgentKG conversation graph,
consolidate old turns into summaries, and snapshot the graph — enabling semantic recall
across sessions.

### Launch the Streamlit visualizer

```bash
# Requires [viz] extra: pip install 'memory-kg[viz]'
memorykg viz

# Custom port, suppress browser launch
memorykg viz --port 8510 --no-browser
```

### Start the MCP server

```bash
# Serve via stdio (default — for Claude Code, Cline, Copilot)
memorykg mcp --repo docs/

# Serve via SSE (for web clients)
memorykg mcp --repo docs/ --transport sse
```

### Use via MCP in Claude Code / GitHub Copilot

Once the MCP server is running, your AI agent has four tools:

```
graph_stats()                        # node/edge counts by kind
query_docs("authentication flow")    # hybrid semantic + structural search
pack_docs("configuration reference") # source-grounded passages as Markdown
get_node("chunk:intro:overview")     # fetch a single node by ID
```

---

## Installation

**Requirements:** Python ≥ 3.12, < 3.14

### pip (from GitHub)

```bash
# Core install (SQLite + LanceDB + MCP server)
pip install 'memory-kg @ git+https://github.com/Flux-Frontiers/memory_kg.git'

# With Streamlit web visualizer (adds Streamlit, pyvis, plotly)
pip install 'memory-kg[viz] @ git+https://github.com/Flux-Frontiers/memory_kg.git'
```

### Existing Poetry project

```bash
# Core
poetry add 'memory-kg @ git+https://github.com/Flux-Frontiers/memory_kg.git'

# With Streamlit visualizer
poetry add 'memory-kg[viz] @ git+https://github.com/Flux-Frontiers/memory_kg.git'
```

Or declare in `pyproject.toml`:

```toml
[tool.poetry.dependencies]
memory-kg = {git = "https://github.com/Flux-Frontiers/memory_kg.git", extras = ["viz"]}
```

> **Note for MemoryKG developers:** Use `poetry install -E viz` to install the Streamlit visualizer locally.

All CLI entry points are available immediately after installation:

```bash
memorykg build docs/
memorykg query "search term"
memorykg mcp --repo docs/
```

---

## CLI Reference

All commands are available via the unified `memorykg` CLI:

```bash
memorykg --help
```

Every subcommand also ships as a dedicated `memorykg-<name>` script — useful for shell scripts, `Makefile` targets, and CI pipelines with no `poetry run` required.

| Script alias | Equivalent subcommand | Description |
|---|---|---|
| `memorykg-build` | `memorykg build` | Full pipeline: parse → SQLite → LanceDB |
| `memorykg-build-graph` | `memorykg build-graph` | SQLite graph only |
| `memorykg-build-index` | `memorykg build-index` | LanceDB index only |
| `memorykg-query` | `memorykg query` | Hybrid semantic + structural query |
| `memorykg-pack` | `memorykg pack` | Source-grounded passage extraction |
| `memorykg-analyze` | `memorykg analyze` | Corpus health analysis + report |
| `memorykg-snapshot` | `memorykg snapshot` | Save / list / show / diff snapshots |
| `memorykg-viz` | `memorykg viz` | Launch Streamlit visualizer |
| `memorykg-mcp` | `memorykg mcp` | Start MCP server |

### `memorykg build` — Full pipeline

```bash
memorykg build CORPUS_ROOT [--db PATH] [--lancedb PATH] [--model NAME]
            [--update] [--no-similar] [--chunk-strategy STRATEGY]
            [--exclude-dir DIR]...
```

| Option | Default | Description |
|---|---|---|
| `CORPUS_ROOT` | required | Root directory of documents to index |
| `--db` | `.memorykg/graph.sqlite` | SQLite database path |
| `--lancedb` | `.memorykg/lancedb` | LanceDB index directory |
| `--model` | `all-MiniLM-L6-v2` | Sentence-transformer embedding model |
| `--update` | off | Incremental update — keep existing data instead of wiping |
| `--no-similar` | off | Skip computing `SIMILAR_TO` edges |
| `--chunk-strategy` | `semantic` | Chunking strategy: `semantic`, `heading`, `fixed`, `sentence_group` |
| `--exclude-dir` | — | Exclude a directory at every depth (repeatable) |

**Chunking strategies:**

| Strategy | Description | Best for |
|---|---|---|
| `semantic` | Embedding-boundary detection | General document corpora |
| `heading` | One chunk per `## Section` heading | Conversation logs, structured Markdown |
| `fixed` | Fixed character size with overlap | Uniform text, fast builds |
| `sentence_group` | Groups of N sentences | Prose-heavy documents |

### `memorykg build-graph` — SQLite only

```bash
memorykg build-graph CORPUS_ROOT [--db PATH] [--update] [--exclude-dir DIR]...
```

Parses documents, extracts nodes (documents, sections, chunks, topics, entities, keywords), and writes the SQLite graph. No embedding model required.

### `memorykg build-index` — LanceDB only

```bash
memorykg build-index [--db PATH] [--lancedb PATH] [--model NAME] [--no-similar]
```

Reads an existing SQLite graph and builds (or rebuilds) the LanceDB vector index.

### `memorykg query` — Hybrid search

```bash
memorykg query QUERY [--db PATH] [--lancedb PATH] [--k N] [--hop N] [--rels TYPES]
```

| Option | Default | Description |
|---|---|---|
| `QUERY` | required | Natural-language search string |
| `--k` | `8` | Top-K semantic seed hits |
| `--hop` | `1` | Graph expansion hops |
| `--rels` | `CONTAINS,NEXT,REFERENCES,SIMILAR_TO` | Edge types to traverse |

### `memorykg pack` — Passage extraction

```bash
memorykg pack QUERY [--db PATH] [--lancedb PATH] [--k N] [--hop N]
           [--format md|json] [--out PATH] [--max-chars N] [--max-nodes N]
```

| Option | Default | Description |
|---|---|---|
| `--k` | `8` | Top-K semantic seed hits |
| `--hop` | `1` | Graph expansion hops |
| `--format` | `md` | Output format: `md` or `json` |
| `--out` | stdout | Output file path |
| `--max-chars` | `12000` | Max total characters in pack |
| `--max-nodes` | `50` | Max nodes included |

### `memorykg install-hooks` — Hook installation

```bash
memorykg install-hooks [--repo PATH] [--force] [--claude] [--global]
```

| Option | Description |
|---|---|
| `--repo PATH` | Repository root (default: `.`) |
| `--force` | Overwrite existing hooks |
| `--claude` | Install Claude Code hooks into `.claude/settings.json` (project scope) |
| `--global` | Install Claude Code hooks into `~/.claude/settings.json` (all repos) |

With `--claude` or `--global`, writes three shell scripts to `~/.agentkg/hooks/` and
registers them in the target `settings.json`:

| Event | Action |
|---|---|
| `UserPromptSubmit` | Ingest user turn with embeddings |
| `Stop` | Ingest assistant turn; periodic consolidation; async snapshot |
| `PreCompact` | Synchronous prune + snapshot before context compression |

### `memorykg analyze` — Corpus health report

```bash
memorykg analyze [CORPUS_ROOT] [--db PATH] [--lancedb PATH]
              [--output PATH] [--json] [--quiet]
```

Runs the full `MemoryKGAnalyzer` pipeline:

1. Baseline graph statistics (node/edge counts by kind)
2. Per-document structure metrics (sections, chunks, depth)
3. Semantic coverage (% of chunks with topic/entity/keyword annotations)
4. Orphan detection (isolated nodes with no edges)
5. Hot chunks (highest connectivity / most referenced)
6. Actionable insights and improvement suggestions

Writes a Markdown report and optionally a JSON snapshot.

### `memorykg snapshot` — Temporal snapshots

```bash
memorykg snapshot save VERSION   # capture current metrics
memorykg snapshot list           # list all saved snapshots
memorykg snapshot show COMMIT    # full detail + delta vs previous
memorykg snapshot diff A B       # side-by-side comparison
```

---

## Knowledge Graph Schema

### Node kinds

| Kind | Description |
|---|---|
| `document` | A source `.md` or `.txt` file |
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

See [docs/MCP.md](docs/MCP.md) for the full setup guide covering Claude Code, GitHub Copilot, Claude Desktop, and Cline.

### Quick MCP setup

**Claude Code / Kilo Code** — add to `.mcp.json` in your repo root:

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

**GitHub Copilot** — add to `.vscode/mcp.json`:

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

### MCP tools reference

| Tool | Description |
|---|---|
| `graph_stats()` | Node and edge counts by kind |
| `query_docs(q, k, hop, rels, max_nodes)` | Hybrid semantic + structural search |
| `pack_docs(q, k, hop, rels, max_chars, max_nodes)` | Source-grounded passages as Markdown |
| `get_node(node_id)` | Fetch a single node by ID |

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

# Passage pack for LLM context
pack = kg.pack("authentication flow")
pack.save("context.md")
```

---

## Configuration

Add to your project's `pyproject.toml` to persist common settings:

```toml
[tool.memorykg]
exclude = ["archive", "vendor", "generated"]
```

### Exclude priority order

Exclusions are **additive** across three levels:

1. **Built-in** — hardcoded defaults: `.git`, `.venv`, `__pycache__`, `.memorykg`, etc.
2. **Config** — `[tool.memorykg].exclude` from `pyproject.toml` (auto-loaded from corpus root)
3. **CLI** — `--exclude-dir` flags (merged at call time)

---

## Storage Layout

After running `memorykg build`, the following files are created:

```
.memorykg/
  graph.sqlite      # SQLite knowledge graph (nodes + edges)
  lancedb/          # LanceDB vector index
  snapshots/        # Temporal snapshots (JSON)
    manifest.json
    <version>.json

~/.agentkg/           # Conversational memory (created by install-hooks)
  hooks/              # Claude Code auto-ingest hook scripts
  graph.sqlite        # Agent turn graph
  lancedb/            # Agent turn embeddings
  snapshots/          # Session snapshots
  hook_state/         # Per-session consolidation state
```

---

## Contributing

1. Fork the repository and create a feature branch
2. Install dev dependencies: `poetry install`
3. Run the test suite: `pytest`
4. Submit a pull request

```bash
# Install with viz extras for full local development
poetry install -E viz

# Run all tests
pytest

# Lint and format
ruff check src/ tests/
ruff format src/ tests/
```

---

## License

[Elastic License 2.0](LICENSE) — free for non-commercial and internal use; commercial redistribution requires a license from Flux-Frontiers.
