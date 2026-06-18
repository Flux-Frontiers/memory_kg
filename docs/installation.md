# MemoryKG — Installation Guide

**Requirements:** Python ≥ 3.12, < 3.14

---

## pip (from GitHub)

```bash
# Core install (SQLite + LanceDB + MCP server)
pip install 'memory-kg @ git+https://github.com/Flux-Frontiers/memory_kg.git'

# With Streamlit web visualizer (adds Streamlit, pyvis, plotly)
pip install 'memory-kg[viz] @ git+https://github.com/Flux-Frontiers/memory_kg.git'
```

## Poetry

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

## Developer Install

Clone the repo and install with dev dependencies:

```bash
git clone https://github.com/Flux-Frontiers/memory_kg.git
cd memory_kg

# Core only
poetry install

# With Streamlit visualizer
poetry install -E viz

# Run tests
pytest

# Lint and format
ruff check src/ tests/
ruff format src/ tests/
```

## Entry Points

All CLI entry points are available immediately after installation:

```bash
memorykg build --repo docs/
memorykg query "search term"
memorykg mcp --repo docs/
```

Every subcommand also ships as a dedicated `memorykg-<name>` script — useful for shell scripts,
`Makefile` targets, and CI pipelines:

| Script alias | Equivalent subcommand |
|---|---|
| `memorykg-build` | `memorykg build` |
| `memorykg-build-graph` | `memorykg build-graph` |
| `memorykg-build-index` | `memorykg build-index` |
| `memorykg-query` | `memorykg query` |
| `memorykg-pack` | `memorykg pack` |
| `memorykg-analyze` | `memorykg analyze` |
| `memorykg-snapshot` | `memorykg snapshot` |
| `memorykg-viz` | `memorykg viz` |
| `memorykg-mcp` | `memorykg mcp` |

## Embedding Model

The default embedding model is `BAAI/bge-small-en-v1.5` (384-d). Override via `--model` or the
`MEMORYKG_MODEL` environment variable:

```bash
export MEMORYKG_MODEL=all-mpnet-base-v2
memorykg build --repo docs/
```

## Configuration

Add to your project's `pyproject.toml` to persist common settings:

```toml
[tool.memorykg]
exclude = ["archive", "vendor", "generated"]
```

Exclusions are additive across three levels:
1. **Built-in** — hardcoded defaults: `.git`, `.venv`, `__pycache__`, `.memorykg`, etc.
2. **Config** — `[tool.memorykg].exclude` from `pyproject.toml` (auto-loaded from corpus root)
3. **CLI** — `--exclude-dir` flags (merged at call time)
