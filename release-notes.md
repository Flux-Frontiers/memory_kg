# Release Notes — v0.5.2

> Released: 2026-07-09

This is the first tagged release since v0.4.1 and folds in everything from the untagged 0.5.0/0.5.1 line. The headline is a stability fix: `memorykg build` no longer crashes intermittently with a native segfault during the parse phase. Alongside it, this release lands a large benchmark suite, a toolchain modernization, and centralized embedding-model configuration shared across the KG ecosystem.

## What changed

**Build no longer segfaults.** `parse_corpus` ran an 8-thread pool in which every worker shared a single `SentenceTransformer`/torch embedder. Under the default semantic chunking strategy those threads called `encode()` on that one model concurrently, corrupting the native heap (`malloc: pointer being freed was not allocated` → SIGSEGV) — nondeterministically, so some builds succeeded and others crashed. The parse now runs serially whenever a shared embedder is in use, matching the sister repo `doc_kg`. Threaded parsing is retained for the embedder-free strategies (`fixed`/`heading`/`sentence_group`), where the per-file work is pure Python and safe to parallelize.

**A full benchmark program.** New harnesses and academic writeups for **MemBench** (87.7% recall@k20), **ConvoMem** (corrected 96.3% tier-1 recall, +3.4 pp over MemPal), and a MemoryKG-native **LoCoMo** benchmark (98.1% session recall). A prior ConvoMem scoring bug that inflated recall to 100% — an empty `node_text` counted as a substring match — was fixed, and the results and articles were regenerated with honest numbers.

**Toolchain modernization.** The type checker migrated from `mypy` to Astral's `ty`, `pylint` was dropped in favour of `ruff` (which already enforces the equivalent `PLE`/`PLW` rules), and snapshotting moved off the deprecated `kg_snapshot` package onto `kg_utils.snapshots`. Embedding-model configuration (`DEFAULT_MODEL`, model-path resolution) is now centralized in `kg_utils.embed`, and the default model is `BAAI/bge-small-en-v1.5` (384-d) across both the core build and the pipeline.

**Packaging.** The cross-KG siblings (`pycode-kg`, `doc-kg`) are now optional manual installs rather than a resolved extra — pinning them forced Poetry to reconcile their newer `transformers` requirement against this project's cap and left the lock unbuildable. The `transformers` constraint was relaxed to `>=4.40.0,<4.57`, and `--version` now reports the correct `memory-kg` distribution name.

## Upgrading

No API changes and no migration required. Reinstall to pick up the fix and the relaxed dependency bounds:

```
pip install -e ".[dev]"     # or: poetry install --all-extras
```

The cross-KG sibling integrations are no longer installed automatically — add them explicitly if you use them (`pip install pycode-kg doc-kg`). Existing `.memorykg/` indices remain compatible; rebuild with `memorykg build --wipe` only if you want to regenerate from scratch.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
