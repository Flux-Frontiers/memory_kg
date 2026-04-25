# MemoryKG — CLI Reference

All commands are available via the unified `memorykg` CLI:

```bash
memorykg --help
```

---

## `memorykg build` — Full pipeline

```bash
memorykg build [--repo PATH] [--db PATH] [--lancedb PATH] [--model NAME]
               [--update] [--no-similar] [--chunk-size N] [--chunk-overlap N]
               [--exclude-dir DIR]...
```

| Option | Default | Description |
|---|---|---|
| `--repo` | `.` | Root directory of documents to index |
| `--db` | `.memorykg/graph.sqlite` | SQLite database path |
| `--lancedb` | `.memorykg/lancedb` | LanceDB index directory |
| `--model` | `BAAI/bge-small-en-v1.5` | Sentence-transformer embedding model |
| `--update` | off | Incremental update — keep existing data (default is wipe) |
| `--no-similar` | off | Skip computing `SIMILAR_TO` edges |
| `--chunk-size` | `512` | Approximate max characters per chunk |
| `--chunk-overlap` | `64` | Character overlap between consecutive chunks |
| `--similarity-threshold` | `0.75` | Cosine similarity threshold for semantic split detection |
| `--enable-topics/--no-topics` | on | Extract chunk→topic edges (`HAS_TOPIC`) |
| `--enable-entities/--no-entities` | on | Extract chunk→entity edges (`MENTIONS_ENTITY`) |
| `--enable-keywords/--no-keywords` | on | Extract chunk→keyword edges (`HAS_KEYWORD`) |
| `--emit-cooccur/--no-cooccur` | on | Emit `CO_OCCURS_WITH` edges |
| `--topics-file` | — | Optional JSON/YAML topic catalog |
| `--batch` | `256` | Embedding batch size |
| `--workers` | `8` | Parallel embedding workers |
| `--ext` | `.md .txt` | File extensions to include (repeatable) |
| `--exclude-dir` | — | Directory to exclude at every depth (repeatable) |

---

## `memorykg build-graph` — SQLite only

```bash
memorykg build-graph [--repo PATH] [--db PATH] [--update] [--exclude-dir DIR]...
```

Parses documents, extracts nodes and edges, writes the SQLite graph. No embedding model required.
Options mirror `build` except LanceDB and embedding flags are absent.

---

## `memorykg build-index` — LanceDB only

```bash
memorykg build-index [--repo PATH] [--db PATH] [--lancedb PATH] [--model NAME]
                     [--update] [--no-similar] [--batch N] [--workers N]
```

Reads an existing SQLite graph and builds (or rebuilds) the LanceDB vector index.

---

## `memorykg query` — Hybrid search

```bash
memorykg query QUERY [--db PATH] [--lancedb PATH] [--k N] [--hop N] [--rels TYPES]
```

| Option | Default | Description |
|---|---|---|
| `QUERY` | required | Natural-language search string |
| `--k` | `8` | Top-K semantic seed hits |
| `--hop` | `1` | Graph expansion hops |
| `--rels` | `CONTAINS,NEXT,REFERENCES,SIMILAR_TO` | Edge types to traverse |

---

## `memorykg pack` — Passage extraction

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

---

## `memorykg analyze` — Corpus health report

```bash
memorykg analyze [--repo PATH] [--db PATH] [--lancedb PATH]
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

---

## `memorykg snapshot` — Temporal snapshots

```bash
memorykg snapshot save VERSION   # capture current metrics
memorykg snapshot list           # list all saved snapshots
memorykg snapshot show COMMIT    # full detail + delta vs previous
memorykg snapshot diff A B       # side-by-side comparison
```

See [SNAPSHOTS.md](SNAPSHOTS.md) for detailed snapshot workflow.

---

## `memorykg install-hooks` — Hook installation

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

---

## `memorykg viz` — Streamlit visualizer

```bash
memorykg viz [--port N] [--no-browser]
```

Requires `[viz]` extra: `pip install 'memory-kg[viz]'`.

---

## `memorykg mcp` — MCP server

```bash
memorykg mcp [--repo PATH] [--db PATH] [--lancedb PATH]
             [--model NAME] [--transport stdio|sse]
```

See [MCP.md](MCP.md) for full client setup guide (Claude Code, GitHub Copilot, Claude Desktop, Cline).

---

## `memorykg pipeline` — Multipass analysis pipeline

```bash
# Full 5-phase pipeline
memorykg pipeline run --repo docs --batch 20 --strategy sentence_group

# Corpus embedding
memorykg pipeline embed --repo docs --workers 4 --batch-size 64

# Manifold analysis
memorykg pipeline manifold [--cache PATH] [--max-pca N]
```

See [ingestion.md](ingestion.md) for the full multipass pipeline architecture.
