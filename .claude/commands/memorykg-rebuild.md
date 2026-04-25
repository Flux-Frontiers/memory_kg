# MemoryKG Rebuild

Wipe and rebuild the MemoryKG SQLite knowledge graph and LanceDB semantic index for a document corpus. Execute the following steps in sequence.

## Command Argument Handling

**Usage:**
- `/memorykg-rebuild` — Rebuild for the current working directory
- `/memorykg-rebuild /path/to/corpus` — Rebuild for the specified corpus root

---

## Step 0: Resolve Paths

1. If a path argument was provided, use it as `CORPUS_ROOT`. Otherwise use the current working directory.
2. Verify the path exists and contains at least one `.md` or `.txt` file:
   ```bash
   find "$CORPUS_ROOT" \( -name "*.md" -o -name "*.txt" \) \
     -not -path "*/.venv/*" \
     -not -path "*/.memorykg/*" | head -5
   ```
3. If no documents are found, stop and report the issue.

All artifact paths default to `$CORPUS_ROOT/.memorykg/` — do not pass `--db` or `--lancedb` flags.

Detect how to invoke MemoryKG — try in order:
1. `poetry run memorykg` (preferred if inside a Poetry project)
2. `memorykg` (fallback for pip/venv installs)

Use whichever works and apply it consistently for all commands below.

---

## Step 1: Rebuild the SQLite Knowledge Graph

Run the corpus parsing build to replace any existing graph:

```bash
# Poetry
poetry run memorykg build "$CORPUS_ROOT"

# pip / venv
memorykg build "$CORPUS_ROOT"
```

Verify the database was created and is non-empty:
```bash
sqlite3 "$CORPUS_ROOT/.memorykg/graph.sqlite" "SELECT COUNT(*) FROM nodes; SELECT COUNT(*) FROM edges;"
```

Capture and report node and edge counts broken down by kind. If both are zero, warn the user — the corpus may have no indexable documents.

---


## Step 2: Verify

Run a quick smoke-test query to confirm both layers are consistent:

```bash
# Poetry
poetry run memorykg query "document overview" --repo "$CORPUS_ROOT" --k 3

# pip / venv
memorykg query "document overview" --repo "$CORPUS_ROOT" --k 3
```

If this errors, diagnose and report before proceeding.

---

## Step 3: Report

Present a summary:

```
✓ Corpus root:   <CORPUS_ROOT>
✓ SQLite graph:  <CORPUS_ROOT>/.memorykg/graph.sqlite  (<N> nodes, <M> edges)
✓ LanceDB index: <CORPUS_ROOT>/.memorykg/lancedb  (<V> vectors)

Node breakdown:  document=X  section=X  chunk=X  topic=X  entity=X  keyword=X
Edge breakdown:  CONTAINS=X  NEXT=X  REFERENCES=X  SIMILAR_TO=X  HAS_TOPIC=X
```

Note: MCP client configs do not need to change — they reference the same paths.

---

## Important Rules

- Pass the corpus path to `build-graph`; run `build-index` from the corpus root (no path needed — it reads defaults from `.memorykg/`).
- Use an absolute path for the corpus root.
- Do NOT modify any source files in the target corpus.
- If the corpus is large (>500 documents), warn that the embedding step may take several minutes.
