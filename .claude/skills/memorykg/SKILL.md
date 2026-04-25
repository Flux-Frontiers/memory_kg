---
name: memorykg
description: Expert knowledge for installing, configuring, and using MemoryKG — a hybrid semantic + structural knowledge graph for document corpora (.md and .txt files). Use this skill when the user asks about: setting up MemoryKG in a project, adding memory-kg as a Poetry dependency, building the SQLite or LanceDB knowledge graph from documents, running the multipass analysis pipeline (memorykg pipeline run/embed/manifold), configuring .mcp.json for Claude Code or Kilo Code, configuring .vscode/mcp.json for GitHub Copilot, configuring claude_desktop_config.json for Claude Desktop, using the memorykg CLI (memorykg build, memorykg build-graph, memorykg build-index, memorykg query, memorykg pack, memorykg analyze, memorykg semantic-analyze, memorykg pipeline, memorykg viz, memorykg mcp, memorykg snapshot), using the graph_stats / query_docs / pack_docs / get_node MCP tools, or troubleshooting MemoryKG errors.
---

# MemoryKG Skill

> **Use MemoryKG first — before grep, file reads, or text search.**
>
> Text search finds strings. MemoryKG understands documents. It knows which sections contain which chunks, how topics and entities cross-reference across files, and surfaces the most semantically relevant excerpts in a single query. One `pack_docs` call replaces five rounds of search-and-read and gives the agent real structural insight into the corpus — not just keyword matches.

MemoryKG indexes `.md` and `.txt` document corpora into a hybrid knowledge graph (SQLite + LanceDB) and exposes it as MCP tools for AI agents. It also provides a **multipass analysis pipeline** (diary_kg-style) for deep NLP transformation with diversity sampling, hybrid topic classification, corpus embedding, and manifold analysis.

## Installation (Poetry)

```bash
# MCP server support is included in the core install — no extra needed
poetry add "memory-kg @ git+https://github.com/Flux-Frontiers/memory_kg.git"
```

Adds to `pyproject.toml`:
```toml
memory-kg = { git = "https://github.com/Flux-Frontiers/memory_kg.git" }
```

## Build the Knowledge Graph

MemoryKG uses a **single build command** that runs corpus parsing, SQLite persistence, and LanceDB vector indexing in one step. **Wipe is the default** — use `--update` to keep existing data instead.

```bash
# Build from a corpus directory (wipes and rebuilds by default)
memorykg build --repo docs/

# Build from an absolute path
memorykg build --repo /absolute/path/to/corpus

# Incremental update — keep existing data instead of wiping
memorykg build --repo docs/ --update
```

### Granular build steps (advanced)

For large corpora you can run steps independently:

```bash
# Step 1 — parse corpus and write SQLite graph
memorykg build-graph --repo docs/

# Step 2 — build LanceDB vector index from existing SQLite
memorykg build-index

# Incremental variants
memorykg build-graph --repo docs/ --update
memorykg build-index --update
```

### Excluding directories

**Via `pyproject.toml` (persistent — recommended):**
```toml
[tool.memorykg]
exclude = ["archive", "vendor", "generated"]
```

**Via CLI flags (per-command override):**
```bash
memorykg build --repo docs/ --exclude-dir archive --exclude-dir vendor
```

Both are additive — CLI flags extend `pyproject.toml` excludes. Excluded names are matched at every depth.

> **Why exclude matters:** Test directories, vendored docs, and archive folders pollute the graph with irrelevant nodes and degrade semantic retrieval accuracy. Always exclude non-canonical content.

## Rebuilding After Content Changes

The knowledge graph is a snapshot of the corpus at build time. It does **not** update automatically.

| Change | Action |
|---|---|
| Added / deleted documents | Full rebuild (default, no `--update`) |
| Large content updates across many files | Full rebuild (default, no `--update`) |
| Minor edits within existing documents | `--update` is usually sufficient |
| New file added | `--update` is sufficient |

> **Why full rebuild matters:** Deleted or renamed documents remain as phantom entries with `--update`. The default wipe clears orphan nodes from both SQLite and LanceDB.

## Additional CLI Commands

| Command | Purpose |
|---|---|
| `memorykg query <QUERY>` | Hybrid semantic + graph query, prints ranked result summary |
| `memorykg pack <QUERY>` | Hybrid query + text excerpt pack, outputs Markdown or JSON |
| `memorykg analyze` | Structural analysis — metrics, coverage, hotspots, orphaned nodes |
| `memorykg semantic-analyze` | Semantic analysis — themes, entities, language metrics, cohesion |
| `memorykg viz` | Launch Streamlit graph visualizer (PyVis network) |
| `memorykg snapshot save <version>` | Capture metrics snapshot (commit, branch, version) |
| `memorykg snapshot list` | List all snapshots in reverse chronological order |
| `memorykg snapshot show <commit>` | Full details for a single snapshot |
| `memorykg snapshot diff <a> <b>` | Compare two snapshots side-by-side |
| `memorykg mcp` | Start the MCP server (stdio transport) |

### pack output format

`memorykg pack` uses `--fmt` (not `--format`):

```bash
memorykg pack "configuration reference" --fmt md --out context.md
memorykg pack "configuration reference" --fmt json --out context.json
```

## Multipass Analysis Pipeline

MemoryKG includes a diary_kg-style multipass analysis pipeline for deep NLP transformation. This is complementary to the core build — use it for corpus-level analysis, embedding quality evaluation, and structured provenance tracking.

### Pipeline Commands

| Command | Purpose |
|---|---|
| `memorykg pipeline run` | 5-phase analysis: sampling → chunking → classification → memory → output |
| `memorykg pipeline embed` | Multi-process corpus embedding (nomic-embed-text-v1, 768-d) |
| `memorykg pipeline manifold` | Intrinsic dimensionality, PCA elbow, MRL truncation quality |

### The 5 Phases

1. **Diversity Sampling** — NLP feature extraction, K-means clustering, representative batch selection
2. **Sentence-Group Chunking** — N sentences per chunk (default: 4), natural boundaries, fast
3. **Hybrid Topic Classification** — supervised keyword matching (primary) + unsupervised K-means (fallback)
4. **Memory Creation** — `EntryChunk` objects with full source provenance, confidence scores, entities
5. **Structured Output** — pipe-delimited `.psv` with run parameters, source tracking, statistics

### Quick Start

```bash
# Run full pipeline on a corpus (samples 20 docs by default)
memorykg pipeline run --repo docs/ --batch 20 --strategy sentence_group

# Embed full corpus for manifold analysis
memorykg pipeline embed --repo docs/ --workers 4

# Analyze embedding geometry
memorykg pipeline manifold
```

### Key Options

| Option | Default | Purpose |
|---|---|---|
| `--strategy` | `sentence_group` | Chunking strategy (`sentence_group` or `semantic`) |
| `--sentences` | `4` | Sentences per chunk (sentence_group strategy) |
| `--batch` | `20` | Documents to sample per run |
| `--sampling` | `diversity` | Sampling strategy (`diversity`, `random`, `temporal`) |
| `--n-clusters` | `8` | K-means clusters for diversity sampling and topic fallback |
| `--supervised-threshold` | `0.3` | Min confidence to accept supervised classification |
| `--topics-file` | built-in | Custom topic catalog (YAML/JSON) |
| `--model` | `nomic-ai/nomic-embed-text-v1` | Embedding model for pipeline |

### Pipeline Output

Output files are written to `.memorykg/pipeline/`:
- `PipelineRun_<id>_<timestamp>.psv` — pipe-delimited analysis results
- `embeddings.json` — corpus embedding cache (from `pipeline embed`)

### Embedding Models

| Pipeline | Model | Dims | Notes |
|---|---|---|---|
| Core build (`memorykg build`) | `BAAI/bge-small-en-v1.5` | 384 | Fast, general-text, SIMILAR_TO discovery |
| Multipass (`memorykg pipeline`) | `nomic-ai/nomic-embed-text-v1` | 768 | Asymmetric retrieval with `search_document:` prefix |

## Configure Claude Code / Kilo Code (.mcp.json)

Both Claude Code and Kilo Code read per-repo config from `.mcp.json` in the project root.

```json
{
  "mcpServers": {
    "memorykg": {
      "command": "/absolute/path/to/repo/.venv/bin/memorykg",
      "args": [
        "mcp",
        "--repo",   "/absolute/path/to/repo",
        "--db",     "/absolute/path/to/repo/.memorykg/graph.sqlite",
        "--lancedb","/absolute/path/to/repo/.memorykg/lancedb"
      ]
    }
  }
}
```

Always use **absolute paths**. Merge into existing `mcpServers` — don't overwrite other entries.

> ⚠️ Do NOT add `memorykg` to any global settings file — use per-repo `.mcp.json` only.

## Configure GitHub Copilot (.vscode/mcp.json)

GitHub Copilot requires `"servers"` key and `"type": "stdio"`:

```json
{
  "servers": {
    "memorykg": {
      "type": "stdio",
      "command": "/absolute/path/to/repo/.venv/bin/memorykg",
      "args": [
        "mcp",
        "--repo",    "/absolute/path/to/repo",
        "--db",      "/absolute/path/to/repo/.memorykg/graph.sqlite",
        "--lancedb", "/absolute/path/to/repo/.memorykg/lancedb"
      ]
    }
  }
}
```

VS Code will prompt you to **Trust** the server on first use.

## Configure Claude Desktop (claude_desktop_config.json)

Claude Desktop has no Poetry on PATH — use the absolute venv binary:

```bash
poetry env info --path
# → /path/to/venv
# binary: /path/to/venv/bin/memorykg
```

Config path: `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)

```json
{
  "mcpServers": {
    "memorykg": {
      "command": "/path/to/venv/bin/memorykg",
      "args": [
        "mcp",
        "--repo",    "/abs/path",
        "--db",      "/abs/path/.memorykg/graph.sqlite",
        "--lancedb", "/abs/path/.memorykg/lancedb"
      ]
    }
  }
}
```

## MCP Tools

| Tool | When to use |
|---|---|
| `graph_stats()` | First call — understand corpus size, node/edge breakdown |
| `query_docs(q)` | Structural exploration — find relevant nodes and relationships |
| `pack_docs(q)` | Read actual document text (prefer over `query_docs`) |
| `get_node(node_id)` | Fetch one node by its stable ID — metadata, title, file path |

## Node & Edge Reference

### Node kinds

| Kind | ID prefix | Description |
|---|---|---|
| `document` | `document:<file_path>` | Top-level document (one per file) |
| `section` | `section:<file_path>:<heading-slug>` | Markdown heading block |
| `chunk` | `chunk:<file_path>:<index:04d>` | Text fragment (≈512 chars, overlapping) |
| `topic` | `topic:<slug>` | Inferred topic category (e.g. `topic:architecture`) |
| `entity` | `entity:<slug>` | Named entity extracted from chunk text |
| `keyword` | `keyword:<slug>` | Significant keyword extracted from chunk text |

### Edge types

| Relation | Direction | Meaning |
|---|---|---|
| `CONTAINS` | document → section → chunk | Structural containment hierarchy |
| `NEXT` | chunk → chunk | Sequential adjacency (reading order) |
| `REFERENCES` | chunk → document/section | Cross-document citation or link |
| `SIMILAR_TO` | chunk → chunk | High cosine similarity (≥0.85 by default) |
| `HAS_TOPIC` | chunk → topic | Topic classification edge |
| `MENTIONS_ENTITY` | chunk → entity | Named entity mention |
| `HAS_KEYWORD` | chunk → keyword | Keyword occurrence |
| `CO_OCCURS_WITH` | topic/entity/keyword → topic/entity/keyword | Co-occurrence within a chunk window |

## Query Strategy Guide

### Choosing `k` and `hop`

| Goal | Settings |
|---|---|
| Narrow, precise lookup | `k=4, hop=0` |
| Standard exploration | `k=8, hop=1` (default) |
| Broad topic sweep | `k=12, hop=2` |
| Follow document structure | `k=8, hop=1, rels="CONTAINS,NEXT"` |
| Trace topics and entities | `k=8, hop=2, rels="HAS_TOPIC,MENTIONS_ENTITY"` |
| Find semantically similar chunks | `k=6, hop=1, rels="SIMILAR_TO"` |

### Choosing `rels`

| Relation | When to include |
|---|---|
| `CONTAINS` | Always — keeps structural context (document → section → chunk) |
| `NEXT` | When you need adjacent context (reading order) |
| `REFERENCES` | When tracing cross-document links |
| `SIMILAR_TO` | When you want semantically related chunks across files |
| `HAS_TOPIC` | When exploring by topic category |
| `MENTIONS_ENTITY` | When tracing named entities across documents |
| `HAS_KEYWORD` | When doing keyword-centric searches |
| `CO_OCCURS_WITH` | When finding concept clusters |

### Typical session workflow

```
1. graph_stats()                                              → orientation: corpus size and shape
2. query_docs("authentication flow", k=8, hop=1)             → find relevant nodes
3. pack_docs("JWT token validation", k=6, hop=1)             → read actual document text
4. pack_docs("error handling", k=4, hop=2, rels="SIMILAR_TO")→ related chunks across files
5. get_node("document:docs/auth.md")                         → single node metadata
6. query_docs("topic overview", rels="HAS_TOPIC", hop=2)     → topic-centric traversal
```

### Common query patterns

| Goal | Query |
|---|---|
| "What does this corpus say about X?" | `pack_docs("X concept")` |
| "Find all documents about topic T" | `query_docs("T", rels="HAS_TOPIC")` |
| "What chunks mention entity E?" | `query_docs("E", rels="MENTIONS_ENTITY")` |
| "Find chunks similar to this one" | `query_docs("concept", rels="SIMILAR_TO")` |
| "Show the structure of a document" | `query_docs("doc name", rels="CONTAINS", hop=2)` |
| "Find cross-references between docs" | `query_docs("topic", rels="REFERENCES")` |
| "Get adjacent context around a chunk" | `query_docs("chunk text", rels="CONTAINS,NEXT")` |

## Key Defaults

- `k=8, hop=1, rels="CONTAINS,NEXT,REFERENCES,SIMILAR_TO,HAS_TOPIC,MENTIONS_ENTITY,HAS_KEYWORD,CO_OCCURS_WITH"`
- `max_chars=2000` (pack_docs), `max_nodes=15` (pack_docs), `max_nodes=25` (query_docs)
- Core build embedding model: `BAAI/bge-small-en-v1.5` (384-d)
- Pipeline embedding model: `nomic-ai/nomic-embed-text-v1` (768-d)
- Storage: `.memorykg/graph.sqlite` (SQLite) + `.memorykg/lancedb/` (LanceDB)
- Pipeline output: `.memorykg/pipeline/` (`.psv` runs, `embeddings.json` cache)
- Feature cache: `.memorykg/cache/` (pickle, per-file with SHA-256 invalidation)
- Transport: `stdio` (Claude Code/Desktop), `sse` (HTTP clients)

## .gitignore Setup

```gitignore
.memorykg/
```

The `.memorykg/` directory holds the SQLite graph, LanceDB vector index, snapshots, pipeline outputs, feature caches, and embedding caches. All are local reproducible artifacts. Add this to `.gitignore` when installing MemoryKG in a new repo.

## Troubleshooting

| Error | Fix |
|---|---|
| `WARNING: SQLite database not found` | Run `memorykg build --repo <corpus_root>` first |
| `mcp package not found` | `poetry install` (ensure `[mcp]` extra is included) |
| No tools visible in MCP client | Use absolute paths in config; restart the client |
| Empty query results | Run `memorykg build --repo <corpus_root>` |
| Wrong corpus queried | Verify `--repo`, `--db`, and `--lancedb` all point to the same repo |
| Stale nodes after deleting files | Run full rebuild (no `--update`) after deletions or renames |

## Full Reference

See `docs/MCP.md` for complete MCP config templates and tool semantics.
See `docs/ingestion.md` for the complete ingestion architecture (core build + multipass pipeline).
