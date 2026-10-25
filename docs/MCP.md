# MemoryKG MCP Setup Guide

Integrating MemoryKG with MCP-compatible agents (Claude Code, GitHub Copilot, Claude Desktop, Cursor, Continue).

## Overview

MemoryKG includes an MCP server exposed by:

- `memorykg mcp`
- `memorykg-mcp`

Once configured, agents get the fleet's five canonical tools, under the same
names as every other KG server built on `kg_utils.mcp`:

- `stats()`
- `query(q, k, hop, max_nodes, rels)`
- `pack(q, k, hop, max_nodes, rels, max_chars)`
- `get_node(node_id)`
- `neighbors(node_id, rels, direction, limit)`

The list is generated, not kept by hand: `memorykg mcp --manifest` prints it as
JSON without opening the graph.

## Quick Start

1. Build the MemoryKG graph artifacts.
2. Add MCP config for your client.
3. Restart the client.

```bash
# From repo root (wipe is the default)
memorykg build docs

# Or build any corpus directory
# memorykg build /absolute/path/to/corpus

# Exclude specific directories during build
# memorykg build docs --exclude-dir archive --exclude-dir vendor

# Incremental update — keep existing data
# memorykg build docs --update
```

## Start Server Manually

```bash
memorykg mcp --repo /absolute/path/to/repo
```

Equivalent:

```bash
memorykg-mcp --repo /absolute/path/to/repo
```

Optional flags:

- `--db .memorykg/graph.sqlite`
- `--vectors .memorykg/vectors.sqlite`
- `--model BAAI/bge-small-en-v1.5`
- `--transport stdio|streamable-http` (with `--host` / `--port` for HTTP)
- `--manifest` — print the tool list as JSON and exit

These are the standard flags every fleet server takes. A relative `--db` or
`--vectors` is taken from `--repo`. On startup each session prints the store it
is actually serving to stderr, and a corpus with no graph is refused rather
than served empty.

## Claude Code Or Kilo Code (.mcp.json)

Create `.mcp.json` in project root:

```json
{
  "mcpServers": {
    "memorykg": {
      "command": "/absolute/path/to/repo/.venv/bin/memorykg",
      "args": [
        "mcp",
        "--repo",
        "/absolute/path/to/repo",
        "--db",
        "/absolute/path/to/repo/.memorykg/graph.sqlite",
        "--vectors",
        "/absolute/path/to/repo/.memorykg/vectors.sqlite"
      ]
    }
  }
}
```

## GitHub Copilot (.vscode/mcp.json)

Create `.vscode/mcp.json`:

```json
{
  "servers": {
    "memorykg": {
      "type": "stdio",
      "command": "/absolute/path/to/repo/.venv/bin/memorykg",
      "args": [
        "mcp",
        "--repo",
        "/absolute/path/to/repo",
        "--db",
        "/absolute/path/to/repo/.memorykg/graph.sqlite",
        "--vectors",
        "/absolute/path/to/repo/.memorykg/vectors.sqlite"
      ]
    }
  }
}
```

## Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "memorykg": {
      "command": "/absolute/path/to/repo/.venv/bin/memorykg",
      "args": [
        "mcp",
        "--repo",
        "/absolute/path/to/repo",
        "--db",
        "/absolute/path/to/repo/.memorykg/graph.sqlite",
        "--vectors",
        "/absolute/path/to/repo/.memorykg/vectors.sqlite"
      ]
    }
  }
}
```

## Excluding Directories from Indexing

By default, MemoryKG skips common directories (`.git`, `.venv`, `__pycache__`, `.memorykg`, etc.). To exclude additional directories:

**Configuration (`pyproject.toml`, persistent — recommended):**

```toml
[tool.memorykg]
exclude = ["archive", "vendor", "generated"]
```

**CLI flags (per-command override):**

```bash
memorykg build docs --exclude-dir archive --exclude-dir vendor
memorykg build-graph docs --exclude-dir node_modules
```

Both options are additive — CLI flags extend `pyproject.toml` excludes. Excluded directory names are matched at every depth in the file walk.

## Tool Semantics

- `stats()`
Returns node and edge totals and breakdowns by kind and relation.

- `query(...)`
Hybrid search: dense and keyword (BM25) seeds, then graph expansion. Returns
JSON. `rels` is a list, e.g. `["HAS_TOPIC", "SIMILAR_TO"]`; omit it for the
corpus relations.

- `pack(...)`
Same hybrid retrieval, returns a Markdown context pack; `max_chars` caps each
excerpt.

- `get_node(node_id)`
Returns one node record as JSON.

- `neighbors(node_id, rels, direction, limit)`
The edges touching one node and the nodes at their other ends. Graph only; no
model is loaded.

## Troubleshooting

- `mcp package not found`
Install dependencies in the active environment (`poetry install`) and retry.

- `no graph at ...`
Run `memorykg build <corpus_root>` first.

- `Invalid value for '--transport': 'sse'`
SSE was dropped in 0.13.0; use `stdio` or `streamable-http`.

- No tools visible in client
Verify absolute paths in MCP config and restart the client.

- Wrong corpus queried
Ensure `--repo`, `--db`, and `--vectors` all point to the same repository.
