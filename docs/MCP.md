# MemoryKG MCP Setup Guide

Integrating MemoryKG with MCP-compatible agents (Claude Code, GitHub Copilot, Claude Desktop, Cursor, Continue).

## Overview

MemoryKG includes an MCP server exposed by:

- `memorykg mcp`
- `memorykg-mcp`

Once configured, agents get these tools:

- `graph_stats()`
- `query_docs(q, k, hop, rels, max_nodes)`
- `pack_docs(q, k, hop, rels, max_chars, max_nodes)`
- `get_node(node_id)`

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
- `--model all-mpnet-base-v2`
- `--transport stdio|sse`

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

- `graph_stats()`
Returns node and edge totals and breakdowns by kind and relation.

- `query_docs(...)`
Hybrid semantic and graph expansion query. Returns JSON.

- `pack_docs(...)`
Same hybrid retrieval, returns a Markdown context pack.

- `get_node(node_id)`
Returns one node record as JSON.

## Troubleshooting

- `mcp package not found`
Install dependencies in the active environment (`poetry install`) and retry.

- `SQLite database not found`
Run `memorykg build <corpus_root>` first.

- No tools visible in client
Verify absolute paths in MCP config and restart the client.

- Wrong corpus queried
Ensure `--repo`, `--db`, and `--vectors` all point to the same repository.
