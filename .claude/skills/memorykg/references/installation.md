# MemoryKG Installation Reference

## Table of Contents
1. [CLI Flags Reference](#cli-flags-reference)
2. [Agent Config Matrix](#agent-config-matrix)
3. [MCP Config Templates](#mcp-config-templates)
4. [Query Strategy Guide](#query-strategy-guide)
5. [Gitignore Recommendations](#gitignore-recommendations)
6. [Smoke-Test Commands](#smoke-test-commands)
7. [Full Troubleshooting Table](#full-troubleshooting-table)

---

## CLI Flags Reference

### `memorykg build-graph`

| Flag | Required | Default | Description |
|---|---|---|---|
| `--repo` | | `.` | Corpus root directory (a flag, **not** positional) |
| `--sqlite` | | `.memorykg/graph.sqlite` | SQLite output path |
| `--update` | | false | Incremental update; the default is a full rebuild |
| `--exclude-dir` | | — | Directory name(s) to exclude (repeatable) |

### `memorykg build-index`

| Flag | Required | Default | Description |
|---|---|---|---|
| `--sqlite` | | `.memorykg/graph.sqlite` | Path to SQLite graph |
| `--vectors` | | `.memorykg/vectors.sqlite` | sqlite-vec vector store |
| `--model` | | `BAAI/bge-small-en-v1.5` | Sentence-transformer model |
| `--update` | | false | Incremental update; the default is a full rebuild |

### `memorykg mcp`

| Flag | Default | Description |
|---|---|---|
| `--repo` | `.` | Corpus root |
| `--db` | `.memorykg/graph.sqlite` | SQLite path |
| `--vectors` | `.memorykg/vectors.sqlite` | sqlite-vec vector store |
| `--transport` | `stdio` | `stdio` or `sse` |

### `memorykg query`

```bash
poetry run memorykg query "your query here" --k 10
```

| Flag | Default | Description |
|---|---|---|
| `--repo` | `.` | Corpus root directory |
| `--sqlite` | `.memorykg/graph.sqlite` | Path to the SQLite graph |
| `--vectors` | `.memorykg/vectors.sqlite` | Path to the sqlite-vec store |
| `--k` | `10` | Number of seed hits (there is no `--limit`) |
| `--hop` | `1` | Graph expansion hops from each seed |
| `--rels` | all | Restrict expansion to these relation types |
| `--max-nodes` | — | Cap on total nodes returned |
| `--model` | `BAAI/bge-small-en-v1.5` | Sentence-transformer model |

### `memorykg install-hooks`

Installs the pre-commit hook that rebuilds the local index and saves a snapshot
on each commit.

### `memorykg download-model`

Pre-fetches the sentence-transformer model so the first build does not pay the
download cost.

---

## Agent Config Matrix

| Agent | Config file | Key | Per-repo? |
|---|---|---|---|
| **Claude Code** | `.mcp.json` (project root) | `"mcpServers"` | ✅ Yes |
| **Kilo Code** | `.mcp.json` (project root) | `"mcpServers"` | ✅ Yes |
| **GitHub Copilot** | `.vscode/mcp.json` (workspace root) | `"servers"` | ✅ Yes |
| **Claude Desktop** | `~/Library/Application Support/Claude/claude_desktop_config.json` | `"mcpServers"` | ❌ Global |
| **Cline** | `~/...saoudrizwan.claude-dev/settings/cline_mcp_settings.json` | `"mcpServers"` | ❌ Global only |

> ⚠️ **Do NOT add `memorykg` to any global settings file** (Claude Code `~/.claude/settings.json`, Kilo Code `mcp_settings.json`, Cline `cline_mcp_settings.json`).
> Use per-repo config files instead. For Cline, use a uniquely-named entry per repo (e.g. `memorykg-myproject`).

---

## MCP Config Templates

### Claude Code `.mcp.json`

```json
{
  "mcpServers": {
    "memorykg": {
      "command": "memorykg",
      "args": [
        "mcp",
        "--repo",    "/absolute/path/to/corpus",
        "--db",      "/absolute/path/to/corpus/.memorykg/graph.sqlite",
        "--vectors", "/absolute/path/to/corpus/.memorykg/vectors.sqlite"
      ]
    }
  }
}
```

### GitHub Copilot (.vscode/mcp.json)

GitHub Copilot uses a different schema — `"servers"` key (not `"mcpServers"`) and requires `"type": "stdio"`:

```json
{
  "servers": {
    "memorykg": {
      "type": "stdio",
      "command": "/absolute/path/to/venv/bin/memorykg",
      "args": [
        "mcp",
        "--repo",    "/absolute/path/to/corpus",
        "--db",      "/absolute/path/to/corpus/.memorykg/graph.sqlite",
        "--vectors", "/absolute/path/to/corpus/.memorykg/vectors.sqlite"
      ]
    }
  }
}
```

Get venv path: `poetry env info --path`

VS Code will prompt you to **Trust** the server on first use.

### Claude Desktop (absolute venv path)

```json
{
  "mcpServers": {
    "memorykg": {
      "command": "/absolute/path/to/venv/bin/memorykg",
      "args": [
        "mcp",
        "--repo",    "/absolute/path/to/corpus",
        "--db",      "/absolute/path/to/corpus/.memorykg/graph.sqlite",
        "--vectors", "/absolute/path/to/corpus/.memorykg/vectors.sqlite"
      ]
    }
  }
}
```

Get venv path: `poetry env info --path`

---

## Query Strategy Guide

### Choosing `k` and `hop`

| Goal | Settings |
|---|---|
| Narrow, precise lookup | `k=4, hop=0` |
| Standard exploration | `k=8, hop=1` (default) |
| Broad topic sweep | `k=12, hop=2` |
| Follow document structure | `k=8, hop=1, rels="CONTAINS,NEXT"` |

### Choosing `rels`

| Relation | When to include |
|---|---|
| `CONTAINS` | Always — structural context (document → section → chunk) |
| `NEXT` | When you need adjacent context (reading order) |
| `REFERENCES` | When tracing cross-document links |
| `SIMILAR_TO` | When you want semantically related chunks across files |
| `HAS_TOPIC` | When exploring by topic category |
| `MENTIONS_ENTITY` | When tracing named entities across documents |

### Typical session workflow

```
1. graph_stats()                                               → orientation: corpus size and shape
2. query_docs("authentication flow", k=8, hop=1)              → find relevant nodes
3. pack_docs("JWT token validation", k=6, hop=1)              → read actual document text
4. pack_docs("error handling", k=4, hop=2, rels="SIMILAR_TO") → related chunks across files
5. get_node("document:docs/auth.md")                          → single node metadata
```

---

## Gitignore Recommendations

```gitignore
.memorykg/
```

---

## Smoke-Test Commands

```bash
# Sample query (CLI)
cd /path/to/corpus && poetry run memorykg query "document structure" --k 5

# Verify SQLite row counts
sqlite3 .memorykg/graph.sqlite "SELECT COUNT(*) FROM nodes; SELECT COUNT(*) FROM edges;"

# List all documents in the graph
sqlite3 .memorykg/graph.sqlite "SELECT id FROM nodes WHERE kind='document' LIMIT 10;"
```

---

## Full Troubleshooting Table

| Symptom | Cause | Fix |
|---|---|---|
| `WARNING: SQLite database not found` | Graph not built | Run `memorykg build-graph --repo <corpus>` first |
| `mcp package not found` | Install is incomplete | `mcp` is a core dependency — re-run `poetry install` (there is no `mcp` extra) |
| No tools visible in MCP client | Relative paths or wrong location | Use absolute paths in `.mcp.json`; restart client |
| Empty query results | Vector store stale or missing | Run `memorykg build-index` from corpus root |
| Wrong corpus queried | Wrong `--repo` path | Verify `--repo`, `--sqlite` and `--vectors` all point to same corpus |
| Stale nodes after deleting files | Orphan entries in graph | Rebuild without `--update` — a plain build always clears first |
| `Command not found: memorykg` in VS Code MCP log | VS Code doesn't inherit shell PATH | Use absolute path: `"command": "/path/to/venv/bin/memorykg"` |
| Cline shows all repos pointing to same path | Global config used | Use unique entry name per repo (e.g. `memorykg-myproject`) |
