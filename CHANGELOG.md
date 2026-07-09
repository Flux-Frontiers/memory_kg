# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

### Changed

### Removed

- `src/__init__.py`: removed a vestigial, misplaced package init. It re-exported a stale subset of the public API and carried a **second** `__version__` that shadowed the real one — the earlier 0.6.0 bump left it at `0.5.3` while `memory_kg.__version__` (from `src/memory_kg/__init__.py`) stayed correct. The canonical package init is `src/memory_kg/__init__.py`; nothing imported `src`, and only `memory_kg` is packaged. Removing it gives a single source of truth for the version.

### Fixed

## [0.6.0] - 2026-07-09

### Added
- `src/memory_kg/store.py`: streaming reads for memory-bounded index builds — `GraphStore.count_nodes()` (row counts without loading text) and `GraphStore.iter_nodes()` (paged cursor generator). The builder now streams nodes instead of materialising the whole corpus in RAM.
- `benchmarks/longmemeval/longmemeval_memkg.py`: `--device {cpu,mps,cuda,auto}` flag on `prepare`/`all` (sets `KG_EMBED_DEVICE` in-process; default `auto`).

### Changed
- **`src/memory_kg/index.py`: `SemanticIndex.build()` `encode_batch_size` default 1024 → 128.** Attention memory scales with `batch × seq²`; at 1024 a single encode of long (heading) chunks allocated ~7–9 GB, ballooning peak RSS to 25 GB on CPU / 32 GB on MPS (and stalling MPS around 230k rows). Throughput is flat above ~128 on both CPU and MPS, so 128 cuts peak RAM ~7× at no speed cost. A 528k-node MPS build now peaks **~4 GB, flat** (was 25–32 GB).
- `src/memory_kg/index.py`: embedder consolidated onto `kg_utils.embedder` — `Embedder` and `SentenceTransformerEmbedder` are now imported and re-exported from the shared module (single source of truth for model loading + device handling) rather than defined locally. Existing `from memory_kg.index import SentenceTransformerEmbedder` imports are unchanged.
- `src/memory_kg/index.py`: device resolution unified on `KG_EMBED_DEVICE` (precedence: explicit → env → auto-detect cuda→mps→cpu), matching every other KG module. `SemanticIndex.search()` remains an exact flat cosine scan — retrieval recall stays exact, which the benchmark suites depend on.
- `src/memory_kg/index.py`: LanceDB write batch floored at 4096 rows, decoupled from the (smaller) encode batch, to keep fragment count and per-commit cost bounded.
- `benchmarks/longmemeval/longmemeval_memkg.py`: banner now prints the actually-resolved embedding device.
- `pyproject.toml`: require `kgmodule-utils>=0.4.6` (was `>=0.4.4`). kg_utils 0.4.6 lowers the shared embedder's default per-call encode batch 512 → 128, aligning the shared embedder default with this module's own 128 cap and pinning the fix so the dependency can't regress it.

### Removed
- `src/memory_kg/index.py`: GPU-drift mitigation machinery in `build()` — adaptive + fixed embedder refresh, dynamic encode-batch shrink, per-window `torch.mps/cuda.empty_cache()` + `gc.collect()`, and the `is_gpu` gating. All of it was compensating for the oversized encode batch; once that is right-sized the machinery is unnecessary, and on MPS its `embed_ms ≥ 0.6` refresh trigger misfired in steady state (~1.9 ms/row), reloading the model every window and dragging throughput down. The embed loop is now a lean stream: page → encode → buffer → write. Also removed the now-orphaned local `make_embedder` helper.
- `DOCKG_DEVICE` environment variable — superseded by `KG_EMBED_DEVICE`.

### Fixed
- Out-of-memory / stall on large-corpus embedding (Phase 2). Combined fix: streaming node reads (`iter_nodes`) + a pre-allocated contiguous `(n_chunks × dim)` float32 matrix for SIMILAR_TO discovery (replacing a Python list-of-lists) + the right-sized encode batch. A 528,083-node MPS build now completes with **flat ~4 GB peak RSS** and no mid-run stalls.

## [0.5.3] - 2026-07-09

### Changed
- `.github/workflows/ci.yml`, `.github/workflows/release.yml`: bumped `actions/checkout@v4 → v5` and `actions/setup-python@v5 → v6` so CI runs on Node 24 (Node 20 is deprecated on GitHub-hosted runners)
- `.gitignore`: enabled the previously commented-out `dist/` ignore so built wheels/sdist (rebuilt by the release workflow and attached to each GitHub Release) are no longer tracked

### Fixed
- `README.md`: the CI status badge pointed at the renamed `publish.yml` workflow (404 on GitHub, so it never rendered); repointed to the actual `ci.yml` workflow

## [0.5.2] - 2026-07-09

### Added
- `benchmarks/membench/membench_bench.py`: Complete MemBench benchmark harness (ACL 2025) — 1,100 items across 11 memory categories (simple, highlevel, knowledge_update, comparative, conditional, noisy, aggregative, highlevel_rec, lowlevel_rec, RecMultiSession, post_processing) and 3 topics (movie, food, book); prepare/run/all subcommand architecture; per-item haystack scoping essential (without it recall collapses from 87.7% to 8.9%); results: **87.7% recall@k20** (k=10: 81.6%, k=50: 88.9%)
- `benchmarks/membench/BENCHMARKS_MEMBENCH.md`: Full MemBench results record — per-category recall table, k-ablation, scoping ablation, and architectural notes
- `benchmarks/membench/membench_article.md` + `.tex` + `.pdf`: Academic writeup for MemBench evaluation
- `benchmarks/membench/results/`: JSONL + Markdown result files for k=10/20/50/hop=2 runs
- `benchmarks/convomem/convomem_article.md`: New ConvoMem article (corrected numbers — 96.3% tier-1 recall, beating MemPal by +3.4 pp; replaces the prior inflated 100% result)
- New ConvoMem result files (`results_convomem_tier{1-4}_top{10,20}_hop{0,1}_20260426_*.json`) replacing the prior runs that contained the scoring bug
- `benchmarks/locomobench/locomo_bench_memkg.py`: New MemoryKG-native LoCoMo benchmark — replaces ChromaDB-based `locomo_bench.py`; prepare/run/all subcommand architecture; one persistent KG over all 10 conversations with per-conversation `haystack_files` filtering; session and dialog granularity; shared `SentenceTransformerEmbedder`; optional Ollama reranker; auto-generated JSONL + Markdown result files; `--download` flag for dataset fetch
- `benchmarks/locomobench/locomo_article.tex` + `.md` + `.pdf`: Academic writeup — "98.1% Session Recall on LoCoMo: MemoryKG's Hybrid Semantic-Graph Architecture Achieves Near-Perfect Retrieval Across 1,986 Questions with No LLM Required"; includes per-category table, session vs. dialog granularity comparison (24.2 pp gap), recall distribution, throughput analysis, and architectural explanation of why session granularity dominates
- `benchmarks/locomobench/results/`: Session-granularity result (98.1% avg recall, 96.5% perfect) and dialog-granularity result (73.9%) JSONL + Markdown files for k=50, hop=1
- `docs/ingestion_infographic.md`: New ingestion pipeline infographic
- `analysis/memory_kg_analysis_20260426.md`: Updated codebase analysis

### Changed
- `benchmarks/README.md`: Major restructure — now covers all four benchmarks (LongMemEval-S, LoCoMo, MemBench, ConvoMem) with a unified results-at-a-glance table and per-benchmark sections; replaced the old LongMemEval-only guide and CLI reference with concise quick-start commands
- `benchmarks/RESULTS_SUMMARY.md`: Updated LongMemEval comparison table — split MemoryKG row into "baseline" (98.4% R@5, 0.943 NDCG@10) and "sibling boost" (98.6% recall_all@10, 0.954 NDCG@10) to accurately reflect the two configurations
- `benchmarks/convomem/BENCHMARKS_CONVOMEM.md`: Updated with corrected numbers (96.3% tier-1, 88.6% tier-2, 83.7% tier-3, 84.3% tier-4); revised item counts (500/597/500/300 sampled vs. full dataset); added k=10 vs. k=20 ablation and MemPal comparison table
- `benchmarks/convomem/convomem_article.tex` + `.pdf`: Revised to reflect corrected benchmark numbers and ablation findings
- `benchmarks/locomo_bench.py` → `benchmarks/locomobench/locomo_bench.py`: Moved original ChromaDB benchmark into `locomobench/` subdirectory for consistency with other benchmark layouts
- `.gitignore`: Added `benchmarks/locomobench/data/` to exclude large corpus files, KG indices, and raw data from version control
- `docs/ingestion.md`: Minor clarifications — added `DocGraph` row to component table, expanded `TextChunker` strategy list, noted `CO_OCCURS_WITH` is off by default; updated default pipeline embedding model table from `nomic-ai/nomic-embed-text-v1` (768d) to `BAAI/bge-small-en-v1.5` (384d) to match implementation
- `docs/ingestion_infographic.md`: Updated pipeline embedding model table to reflect `BAAI/bge-small-en-v1.5` default and `DOCKG_MODEL` env var
- `src/memory_kg/memorykg.py`: Removed local `DEFAULT_MODEL` definition; re-exported from `kg_utils.embed` to centralize model configuration across the KG ecosystem
- `src/memory_kg/index.py`: `DEFAULT_MODEL` and `resolve_model_path` now imported from `kg_utils.embed`; `_local_model_path()` delegates to `kg_utils.embed.resolve_model_path()`, respecting `KGRAG_MODEL_DIR` for system-wide cache redirection
- `src/memory_kg/embedder_worker.py`: `PIPELINE_MODEL` now reads `DOCKG_MODEL` env var (default `BAAI/bge-small-en-v1.5`) instead of being hardcoded to `nomic-ai/nomic-embed-text-v1`, aligning pipeline and core build model selection
- **Tooling: type-checker migrated from `mypy` to `ty`** (Astral), matching the sister repo `doc_kg`. `pyproject.toml`: `[tool.mypy]` replaced with `[tool.ty.environment]` + `[tool.ty.rules]` (`unresolved-import = "ignore"`, mirroring mypy's `ignore_missing_imports`); `mypy` dev/all dep replaced with `ty>=0.0.41`. `.github/workflows/ci.yml`: type-check job now runs `ty check src/`. `.pre-commit-config.yaml`: `mypy` local hook replaced with `ty`
- `src/memory_kg/graph.py`: `nodes`/`edges` properties use `assert ... is not None` instead of `# type: ignore[return-value]`; `__repr__` ignore comment updated to `# ty: ignore[invalid-argument-type]`
- `src/memory_kg/store.py`: hoisted `params: list[object]` annotation above the branch so both query-parameter branches share the declared element type (ty `invalid-argument-type` fix)
- `src/memory_kg/index.py`: progress-bar advance now guards `prog is not None` alongside `task_id` (ty `unresolved-attribute` fix; `prog` is `None` under `nullcontext`); the two `tqdm.__init__ = _silent_init` monkey-patches carry `# ty: ignore[invalid-assignment]` (matching doc_kg)
- `src/memory_kg/topics.py`: optional-`yaml` fallback ignore comment updated to `# ty: ignore[invalid-assignment]`
- **`src/memory_kg/snapshots.py`: migrated off the deprecated `kg_snapshot` package to `kg_utils.snapshots`** (provided by `kgmodule-utils`), matching the sister repo `doc_kg`. The `SnapshotManager.capture()` override was realigned to the base class's `(..., tree_hash, hotspots, issues, **extra_metrics)` signature — the per-field kwargs (`coverage_score`, `issues_count`, `complexity_median`) are now read from `**extra_metrics`, which both preserves the public call contract (all callers pass them by keyword) and restores Liskov substitutability (fixes the ty `invalid-method-override` error)
- `pyproject.toml`: `kgmodule-utils` bumped `>=0.2.0` → `>=0.4.4` (provides `kg_utils.snapshots`), matching doc_kg

- `pyproject.toml`: the cross-KG sibling integrations (`pycode-kg`, `doc-kg`) are now **optional manual installs** rather than a resolved `kgdeps` extra. They are never imported by memory_kg's core code, and pinning them forced poetry's universal lock resolution to reconcile their newer `transformers>=4.57.6` requirement against this project's `transformers<4.57` cap — which had left `poetry.lock` unbuildable. Removing them unblocks `poetry lock`
- `poetry.lock`: regenerated — now consistent with `pyproject.toml` (`poetry check --lock` passes); previously stale since the `transformers<4.57` cap was introduced
- `pyproject.toml`: relaxed the `transformers` constraint to `>=4.40.0,<4.57` (widened lower bound) for broader environment compatibility

### Removed
- **`pylint` dropped** in favour of `ruff` (which already enforces the pylint-derived `PLE`/`PLW` rules): removed `pylint>=4.0.5` from dev/all deps, the `[tool.pylint.messages_control]` config, and the `pylint` pre-commit hook
- `pyproject.toml`: the `kgdeps` extra (`pip install -e ".[kgdeps]"`) — superseded by manual installs for the optional cross-KG siblings; removed its references from the install-instructions header
- `pyproject.toml`: the `kg-snapshot>=0.3.0` runtime dependency — snapshot functionality now comes from `kg_utils.snapshots` (in `kgmodule-utils`); `kg_snapshot` is no longer imported anywhere
- `benchmarks/BENCHMARKS.md`, `benchmarks/BENCHMARKS_COMPARISON.md`: Superseded by per-benchmark articles and the unified `benchmarks/README.md`
- `benchmarks/membench_bench.py`: Top-level script moved to `benchmarks/membench/membench_bench.py`
- Old ConvoMem result files with inflated scores from the scoring bug

### Fixed
- `src/memory_kg/memorykg.py`: **Parse-phase segfault** (`malloc: pointer being freed was not allocated` → SIGSEGV). The 8-thread `ThreadPoolExecutor` in `parse_corpus` gave each worker its own chunker but all wrapped the *same* shared `SentenceTransformer`/torch embedder; semantic chunking's concurrent `encode()` calls corrupted the native heap. Now parses serially whenever a shared embedder is in use (mirroring `doc_kg`); threaded parsing stays for the embedder-free strategies (`fixed`/`heading`/`sentence_group`), where per-file work is pure Python
- `src/memory_kg/cli`: `--version` reported the wrong distribution name (`doc-kg` → `memory-kg`)
- `benchmarks/convomem/convomem_bench.py`: Scoring bug in `retrieve_for_item()` — empty `node_text` was always counted as a substring match (empty string is a substring of any string), artificially inflating recall to 100%; fixed with `node_text and (...)` guard; corrected tier-1 recall: 96.3% (vs. 92.9% MemPal, still +3.4 pp)
- `tests/test_embedder_worker.py`: Updated `test_pipeline_model_constant_value` to respect `DOCKG_MODEL` env var override rather than asserting the old hardcoded model name

## [0.4.1] - 2026-04-25

### Added
- `benchmarks/convomem/BENCHMARKS_CONVOMEM.md`: New benchmark report — MemoryKG achieves **100% retrieval recall** on 17,463 ConvoMem items across all six evidence categories (User Facts, Assistant Facts, Abstention, Implicit Connections, Preferences, Changing Facts) and tiers 1–4; outperforms MemoryPalace's best published recall (92.9%) by +7.1 pp overall, with the largest gains on Preferences (+14.0 pp) and Implicit Connections (+10.7 pp)
- `benchmarks/convomem/convomem_article.pdf` + `.tex`: Academic paper writeup — "Perfect Retrieval Recall on ConvoMem: MemoryKG's Hybrid Semantic-Graph Architecture Achieves 100% Across 17,463 Items"; includes tier tables (1–4), MemoryPalace comparison, paper-baseline context table, architectural analysis, and throughput analysis (0.07 s/item on Apple Silicon)
- `README.md`: Expanded Citation section with APA and BibTeX formats
- `docs/python-api.md`: New doc covering the `MemoryKG` Python class — `build`, hybrid `query`, haystack-scoped query, and `pack` — moved out of the README so the README can stay focused on what/why and benchmarks

### Changed
- `benchmarks/convomem/convomem_bench.py`: Complete rewrite — replaced ChromaDB/MemPal backend with MemoryKG (SQLite + LanceDB); added shared `SentenceTransformerEmbedder` reused across all items for ~0.07 s/item throughput; added `--tier` (evidence tier 1–6), `--hop` (graph expansion hops), `--k` (semantic seeds), `--model`, and `--rels` flags; proper Markdown corpus serialization (one `.md` per conversation, `##`-headed speaker turns); per-item KG built with topic/entity/keyword enrichment disabled for speed
- `.gitignore`: Added `benchmarks/convomem/results_*.json` and LaTeX auxiliary file patterns (`*.aux`, `*.log`, `*.out`) to prevent large result files and build artifacts from being tracked
- `README.md`: Restructured TL;DR — ConvoMem 100% retrieval recall now leads, LongMemEval-S follows with **"tied for the top LLM-free score"** framing; paragraph names the three LLM-augmented systems that rank higher at R@5 (MemoryPalace v4 + Haiku 100%, v3 + Haiku rerank 99.4%, Supermemory ASMR ~99%); section header "Why It Wins" → "Why It Works"; bullet 5 "closed the gap" → "narrowed the gap"; removed Knowledge Graph Schema, MCP Integration, Python API, and Storage Layout sections — already covered in `docs/ingestion.md`, `docs/MCP.md`, `docs/python-api.md`; Documentation table updated with new doc rows and PDF article links
- `benchmarks/BENCHMARKS.md`: Replaced "clean" benchmark terminology in five places with descriptive labels: "Clean score — never tuned on held-out" → "Held-out score — not tuned on these 450 questions" (MemoryPalace row); "MemoryPalace's clean held-out score" → "MemoryPalace's held-out LLM-free score"; "Clean baseline (raw questions)" → "Raw-question baseline (no normalization)" (×2, our own results table and file index); "This progression is clean" → "This progression is principled"
- `benchmarks/convomem/convomem_article.tex`: Updated item count to 17,463 (5,000 + 5,008 + 4,658 + 2,797) across title, abstract, and §6.3 (Throughput) to include tier 4; abstract updated from "1–3 messages" to "1–4 messages"; §6.2 Tier scaling now reads "through tier 4 (four evidence messages)"; reproducibility command list now includes `--tier 4`; removed the "Block extraction" row from Table 3 (paper baselines); added `\citep{}` citations for each system in Table 4 (`memorykg2026`, `mempal2026`, `pakhomov2025convomem` ×2 for Gemini Pro/Flash, `mem0`); marked Assistant Facts Δ as "tied" so it is distinguishable from "n/a" (Changing Facts, not reported); tightened §5.4 summary to "100% _overall_ retrieval recall on ConvoMem", noting MemPal also reaches 100% on Assistant Facts at tier 1; "outperform" → "match or outperform" for long-context Gemini comparison
- `docs/ingestion.md`: Storage Layout section expanded — added "Why ignore `.memorykg/` in version control" subsection (artifacts are derived from the source corpus, fully reproducible by re-running `memorykg build`, large binaries up to several GB, corpus is source of truth); replaced bare `.memorykg/` gitignore advice with the correct `**/.memorykg/` pattern that catches nested cases like `docs/.memorykg/`; added granular alternative for users who want to track `snapshots/` while ignoring the heavy artifacts

## [0.4.0] - 2026-04-25

### Added
- `benchmarks/BENCHMARKS.md`: New comprehensive benchmark narrative — full LongMemEval progression from 75.8% → 98.4% R@5, recall_all analysis, integrity section, comparison vs MemoryPalace / Mastra / Hindsight / academic baselines, and reproducibility block
- `benchmarks/longmemeval/longmemeval_memkg.py`: `_sibling_boost()` — post-retrieval reranker that clusters `<base>_1` / `_2` / `_N` family members together when the first family member is found; applied only when `len(answer_sids) > 1` to avoid displacing single-session results; improves recall_all@10 from 96.8% → 98.6% (+1.8 pp)
- `benchmarks/longmemeval/longmemeval_memkg.py`: `recall_all@k` now tracked per-question in JSONL output (`entry_metrics`), in the per-type terminal breakdown, and in the summary table alongside recall_any and nDCG
- `benchmarks/longmemeval/longmemeval_memkg.py`: `answer_session_ids` and `query_sent` fields added to each JSONL result row for offline analysis
- `benchmarks/longmemeval/results.jsonl`: Committed clean baseline run (raw questions, no normalization) — recall_any@10=99.4%, recall_all@10=96.8%, nDCG@10=0.943

### Changed
- `benchmarks/longmemeval/longmemeval_memkg.py`: Query normalization removed — empirical A/B comparison showed raw questions outperform wh-word-stripped queries at every k; `_normalize_question`, `_WH_PREFIX`, and `_PERSONAL_STUB` deleted entirely
- `benchmarks/longmemeval/longmemeval_memkg.py`: All lazy function-level imports promoted to top-level (`MemoryKG`, `DEFAULT_MODEL`, `DEFAULT_RELS`, `urllib.request`, `urllib.error`, `importlib.util`); `json as _json` alias replaced with top-level `json`
- `benchmarks/longmemeval/longmemeval_memkg.py`: Terminal output and CLI help strings updated from "DocKG" to "MemoryKG"
- `benchmarks/longmemeval/longmemeval_memkg.py`: Summary table now shows recall_any, recall_all, and nDCG side-by-side; per-type breakdown shows both `any=` and `all=` columns
- `benchmarks/BENCHMARKS.md`: Rewrote with current results (98.4% R@5 baseline, 98.6% recall_all@10 with sibling boost) and full progression story; "MemPalace" renamed "MemoryPalace" throughout
- `README.md`: Updated headline benchmark numbers (97.6% → 98.4% R@5, 0.936 → 0.943 NDCG@10); added recall_all@10 callout; comparison table expanded with MemoryPalace hybrid v4 held-out and Supermemory ASMR rows, "MemPalace" → "MemoryPalace"; version badge 0.3.1 → 0.4.0
- `pyproject.toml`, `src/memory_kg/__init__.py`: Version bumped 0.3.1 → 0.4.0

### Removed
- `benchmarks/longmemeval_bench.py`: Legacy top-level bench script superseded by `benchmarks/longmemeval/longmemeval_memkg.py`
- `benchmarks/convomem_bench.py`: Moved to `benchmarks/convomem/` in a prior session; stale top-level copy removed
- `benchmarks/BENCHMARKS_MEMKG.md`: Replaced by the new `benchmarks/BENCHMARKS.md`

### Fixed
- `benchmarks/longmemeval/longmemeval_memkg.py`: `broad-exception-caught` pylint warning suppressed with inline `# pylint: disable` on the intentionally best-effort auto-render block

### Added
- `.mcp.json.example`: Portable MCP config template using relative paths (`.venv/bin/memorykg`, `"."` for repo) — copy to `.mcp.json` and customize for your environment
- `.vscode/mcp.json.example`: Portable VS Code MCP config template with relative paths for `memorykg` and `pycodekg` servers

### Changed
- `.gitignore`: Permanently exclude `.mcp.json`, `.vscode/mcp.json`, and `.claude/claude_code_config.json` — all contain machine-specific absolute paths unsuitable for a public repo
- `.pre-commit-config.yaml`: Move `ruff` and `detect-secrets` before the local `pylint`/`mypy`/`pytest` hooks so fast linters run first and catch issues cheaply; add `pass_filenames: false` and `always_run: true` to ruff hooks to match the behavior of the local hooks
- `.github/workflows/ci.yml`: Re-enable CI on `push` and `pull_request` to `main`; expand from a no-op `workflow_dispatch`-only stub to a full 3-job pipeline — `lint` (ruff format + check, `--only dev` deps to avoid the kgrag git dep), `type-check` (mypy, full install), `test` (pytest, full install)
- `.claude/skills/memorykg/SKILL.md`: Fix package name `doc-kg` → `memory-kg`; remove nonexistent `[mcp]` extra from install command (`mcp` is a core dep, no extra needed); update build command syntax to `--repo` flag style; fix `--format` → `--fmt` for `pack`; correct embedding model reference to `BAAI/bge-small-en-v1.5 (384-d)`; remove stale offline-setup section

### Fixed
- `README.md`: Fix `--format` → `--fmt` in two `memorykg pack` examples

### Removed
- `.mcp.json`: Machine-specific config with hardcoded `/Users/egs/...` paths; replaced by `.mcp.json.example`
- `.vscode/mcp.json`: Machine-specific VS Code MCP config with hardcoded absolute paths; replaced by `.vscode/mcp.json.example`
- `.claude/claude_code_config.json`: Machine-specific copilot MCP config with hardcoded `~/.claude/copilot/` paths; no public value

### Added
- `analysis/MemoryKG_Agent_instructions.md`: New agent prompt for MemoryKG tool assessment — replaces the old DocKG-targeted version; correctly describes MemoryKG purpose (document corpora), GitHub URL, MCP tools (`query_docs`, `pack_docs`, `get_node`, `graph_stats`), lineage from DocKG, and differentiating features (semantic layer, manifold analysis, pipeline, Claude Code hooks)
- `analysis/memory_kg_analysis_20260425.md`: PyCodeKG thorough analysis report for the memory_kg codebase — baseline metrics, fan-in ranking, SIR, docstring coverage, orphan audit, CodeRank, concern-based hybrid ranking

### Changed
- **Docstring coverage: 71.3% → 98.9%** — added 76 docstrings across 17 modules; all functions and methods now documented; remaining 3 undocumented nodes are property setters whose getters already carry the docstring
  - `store.py`: `ProvMeta.__init__`/`__repr__`, `GraphStore.__init__`/`__enter__`/`__exit__`/`__repr__`/`_upsert_nodes`/`_upsert_edges`
  - `kg.py`: `BuildStats.__str__`, `MemoryKG.__init__`/`__enter__`/`__exit__`/`__repr__`
  - `snapshots.py`: `SnapshotManager.__init__`/`load_snapshot`/`get_previous`/`get_baseline`
  - `index.py`: `SentenceTransformerEmbedder.__init__`/`__repr__`, `SemanticIndex.__init__`/`_read_nodes`/`_open_table`/`_get_table`/`__repr__`, nested `_silent_init`/`_flush`
  - `chunker.py`: `TextChunker.__init__`, `SentenceGroupChunker.__init__`, `HeadingChunker.__init__`
  - `graph.py`: `DocGraph.__init__`/`__repr__`
  - `app.py`: `_parse_cli_db_arg`, `_init_state`, `_load_store`, `_load_kg`, `_get_store`, `_build_pyvis`, `_render_sidebar`, `_load_all_nodes_edges`
  - `memorykg_thorough_analysis.py`: all 9 `MemoryKGAnalyzer` methods + `_default_report_path`/`_default_json_path`/`_print_summary`
  - `memorykg_semantic_analysis.py`: `MemoryKGSemanticAnalyzer.__init__`/`_compile_results`/`_write_report` + module-level helpers
  - `topics.py`, `relations.py`, `sampler.py`, `pipeline.py`, `manifold.py`, `semantic_builder.py`, `semantic_extractor.py`, `embedder_worker.py`, `memorykg.py`, `cli/cmd_snapshot.py`: remaining undocumented items

### Removed
- `.dockg/snapshots/` (16 JSON snapshots + manifest): Legacy DocKG snapshot artifacts purged from tracking; superseded by the `.memorykg/` layout
- `analysis/DocKG_Agent_instructions.md`: Replaced by `MemoryKG_Agent_instructions.md`
- `analysis/doc_kg_analysis_2026{0308,0314,0320}.md`: Stale DocKG analysis reports removed

### Added
- `README.md`: Rewritten to lead with the competitive benchmark story — TL;DR table comparing MemoryKG (97.6% R@5, no LLM) against MemPalace, Mastra, Hindsight, Supermemory, and academic baselines; per-type breakdown vs MemPalace raw and MemPalace + Haiku rerank; "Why It Wins" section covering chunk granularity, structural expansion, score-first ranking, kind-aware ranking, and search-space scoping; reproducibility block with exact LongMemEval-S commands; version badge bumped 0.1.0 → 0.3.1
- `CITATION.cff`: Citation metadata for academic use; Zenodo DOI badge added to README
- `docs/installation.md`: Detailed install guide (pip, Poetry, dev setup, offline model caching, MCP integration)
- `docs/cli-reference.md`: Full CLI reference with every flag for `build`, `query`, `pack`, `analyze`, `snapshot`, `viz`, `mcp`
- `pyproject.toml`: Expanded ruff lint `select` from 5 → 14 rule families (`B`, `SIM`, `C4`, `RET`, `PIE`, `PERF`, `FURB`, `RUF`, `PLE`, `PLW` added on top of the existing `E`, `F`, `W`, `I`, `UP`); added `[tool.ruff.lint.per-file-ignores]` to keep `benchmarks/`, `scripts/`, `tests/`, and `generate_wiki.py` on a looser ruleset; ignored `RUF001`/`RUF002` (intentional en-dash typography), `SIM113` (manual counter is occasionally clearer), `PLW0603` (MCP server uses an intentional module singleton)
- `kg.py`: `MemoryKG.__init__` gains `embedder: Embedder | None = None` parameter — when provided, pre-seeds `_embedder` so the lazy `SentenceTransformerEmbedder` init never fires; useful for injecting a custom or pre-loaded embedding backend

### Fixed
- `src/memory_kg/index.py`, `src/memory_kg/pipeline.py`: Three `zip()` calls now use `strict=True` (chunk/texts/vecs and chunk_ids/chunk_vecs pairs) — silently truncating on length mismatch was a latent-bug risk caught by the new `B905` rule
- `src/memory_kg/cli/main.py`: Restored `# noqa: F401` on side-effect subcommand imports and added explicit `__all__ = ["cli"]` for the entry-point re-export (previous noqa was inadvertently stripped by an earlier ruff auto-fix)
- `src/memory_kg/index.py`: Collapsed nested `if not wipe: / if ids:` into a single condition (SIM102); removed two `[] if x else []` no-op conditional initializers (RUF034); kept the explanatory comment about the ~800 MB RAM saving when `discover_similar` is off
- `src/memory_kg/chunker.py`, `src/memory_kg/kg.py`, `src/memory_kg/manifold.py`, `src/memory_kg/memorykg_thorough_analysis.py`: Replaced eight manual `for ... append()` loops with comprehensions or `list.extend()` calls (PERF401)
- `src/memory_kg/cli/cmd_build.py`: Two `set(generator)` expressions rewritten as set comprehensions (C401)
- `src/memory_kg/cli/cmd_hooks.py`, `src/memory_kg/semantic_builder.py`: Replaced `.items()` iteration with `.values()` where the key was unused (PERF102, B007)
- `src/memory_kg/chunker.py`: List concatenation `overlap_sents + [sent]` rewritten as `[*overlap_sents, sent]` (RUF005)
- `src/memory_kg/store.py`: Combined identical `if`/`elif` branches in graph traversal using a single condition (SIM114)
- `src/memory_kg/memorykg_semantic_analysis.py`: `_STOP` frozenset's `"""...""".split()` rewritten as a list literal (SIM905)
- `src/memory_kg/__init__.py`, `src/__init__.py`, `src/memory_kg/snapshots.py`: `__all__` lists sorted in isort style (RUF022)
- `src/memory_kg/cli/cmd_hooks.py`, `src/memory_kg/cli/main.py`, `src/memory_kg/sampler.py`, `src/memory_kg/snapshots.py`: Removed six unused `# noqa` directives whose underlying rules are no longer enabled (RUF100)
- Formatting: `ruff format` applied to `benchmarks/build_dockg.py`, `src/memory_kg/semantic_extractor.py`, `src/memory_kg/semantic_primitives.py`, `src/memory_kg/store.py` (4 files reformatted, 62 already clean)

### Fixed
- `index.py`: `SentenceTransformerEmbedder` dimension probe now tries `get_embedding_dimension()` before falling back to `get_sentence_embedding_dimension()`, then defaults to 384 — ensures compatibility across SentenceTransformer API versions

### Added
- `--workers` / `n_workers` parameter throughout the build pipeline — `MemoryKG`, `DocGraph`, `SemanticIndex.build()`, `cmd_build.py` (`build` and `build-index` commands), and benchmark scripts now accept `--workers N` for parallel Phase 1 file parsing (default: 8)
- `memorykg.py`: `parse_corpus()` parallelized via `ThreadPoolExecutor` — each worker thread gets its own thread-local chunker and topic extractor; per-file local nodes/edges are merged after all futures complete, eliminating shared-state races
- `benchmarks/convomem/convomem_bench.py`: New ConvoMem benchmark harness — evaluates retrieval against the Salesforce ConvoMem dataset (75,336 QA pairs across 6 evidence categories: user facts, assistant facts, changing facts, abstention, preferences, implicit connections); downloads evidence files from HuggingFace on first run; supports `--limit`, `--top-k`, `--category`, `--mode` (raw/aaak), and `--out` options

### Changed
- `benchmarks/BENCHMARKS.md`: Expanded comparison table to include R@10 and NDCG@10 columns; updated narrative — MemoryKG (97.6% R@5, 99.2% R@10, 0.936 NDCG@10) is the only zero-inference system to exceed MemPalace hybrid v2 at both R@10 and NDCG@10
- `benchmarks/BENCHMARKS_MEMKG.md`: Updated to `results_bge_haystack` run (R@1 89.4%, R@5 97.6%, R@10 99.2%, NDCG@10 0.936, only 4 misses — all multi-hop temporal arithmetic); configuration section added (BGE-small, heading chunks, haystack filter enabled)
- `benchmarks/RESULTS_SUMMARY.md`: Refined narrative to explicitly highlight MemoryKG beating MemPalace hybrid v2 at NDCG@10 (0.936 vs 0.934) and R@10 (99.2% vs 99.0%)
- `benchmarks/longmemeval/longmemeval_memkg.py`: Added `--workers` flag; updated default data path to `~/Downloads`; added model caching documentation (offline use via `DOCKG_MODEL_DIR`); wired `n_workers` through `build_kg()` and `cmd_prepare()`
- `.vscode/mcp.json`: Updated CodeKG binary `codekg` → `pycodekg` and DB path `.codekg/` → `.pycodekg/`
- `pyproject.toml`: Version bumped `0.1.0` → `0.2.0`

### Added
- `benchmarks/longmemeval/`: New self-contained benchmark subdirectory — moved `longmemeval_memkg.py`, all result JSONL files, and the `data/` corpus+KG directory here; `.gitignore` updated to exclude `data/` and `results_*.jsonl` from the new location
- `benchmarks/BENCHMARKS.md`: Full MemoryKG benchmark report modeled on MemPalace's structure — field comparison table, per-type breakdown vs MemPalace (with and without Haiku rerank), complete score progression narrative from 75.8% → 97.6%, architecture diagram, and reproducer
- `benchmarks/RESULTS_SUMMARY.md`: Concise comparison of best MemoryKG result (97.6% R@5, no LLM) against MemPalace and other published systems
- `benchmarks/README.md`: Rewritten from scratch as MemoryKG benchmark guide — setup, quick start, full CLI reference table for all `run`/`prepare`/`all` flags, common recipes, environment variables
- `benchmarks/render_results.py`: Run time now recorded in JSONL `_meta` header row (`elapsed_s`, `s_per_question`, `k`, `hop`, `haystack_filter`) and surfaced in single-run and comparison markdown reports; added `_load_meta()` and `_result_rows()` helpers; `_md_header()` accepts optional `meta` dict

### Changed
- `benchmarks/longmemeval/longmemeval_memkg.py`: `--haystack-filter` now defaults to **on** (add `--no-haystack-filter` to disable); `--k` default lowered from 150 → 50 (correct for haystack-scoped search); JSONL output now prefixed with a `_meta` header row containing run configuration and elapsed time; `REPO_ROOT` and data paths updated for new subdir location
- `benchmarks/render_results.py`: `write_markdown()` and `write_comparison_markdown()` strip `_meta` rows before aggregation; comparison report run headings include elapsed time when available

### Fixed
- `src/memory_kg/cli/cmd_hooks.py`: Corrected type annotation `dict[str, tuple[str, dict]]` → `dict[str, tuple[str, str]]` (hook script content is `str`, not `dict`)
- `src/memory_kg/pipeline.py`: Added `HeadingChunker` to import and to the `chunker` variable type annotation (`TextChunker | SentenceGroupChunker | HeadingChunker`) to match `chunker_for()` return type
- `src/memory_kg/memorykg.py`: Added `cast(Literal[...], chunk_strategy)` when calling `chunker_for()` to satisfy mypy Literal argument requirement
- `benchmarks/render_results.py`: Removed unused `bars` variable assignment (ruff F841); renamed ambiguous `l` → `lbl` in list comprehension (ruff E741)

### Added
- `index.py`: `SemanticIndex.search()` gains `seed_kinds` and `haystack_files` parameters — `seed_kinds` restricts LanceDB seeding to specific node kinds (e.g. `("document",)` for session-root-only seeding); `haystack_files` restricts seeding to a per-question file set for apples-to-apples comparison with MemPalace
- `kg.py`: `MemoryKG.query()` gains matching `seed_kinds` and `haystack_files` pass-through parameters with usage example in docstring
- `benchmarks/longmemeval_memkg.py`: `--seed-kinds` CLI flag (comma-separated node kinds, e.g. `document`) and `--haystack-filter` flag (limits seeding to per-question haystack files); both wired through `query_sessions()`
- `benchmarks/BENCHMARKS_COMPARISON.md`: Added `results_bge_doc_seed` (Recall@10 81.2%) and `results_haystack_filter` (Recall@10 97.0%) runs to the multi-run comparison; updated summary tables to 8 columns
- `benchmarks/BENCHMARKS_COMPARISON.md`: Multi-run LongMemEval comparison across baseline, `k150+fixes`, and `k150+kw+temporal` runs — shows +10pp Recall@1 and +6pp Recall@10 improvement from the ranking fix

### Changed
- `index.py`: `SentenceTransformerEmbedder` now reads `DOCKG_DEVICE` env var (default `"mps"`) and passes it to every `SentenceTransformer(...)` constructor call — enables explicit CPU/GPU/MPS device selection without code changes
- `index.py`, `kg.py`: Default `batch_size` raised from 256 → 1024 in `SemanticIndex`, `MemoryKG.build()`, and `MemoryKG.build_index()` for faster embedding throughput on Apple Silicon
- `benchmarks/BENCHMARKS_MEMKG.md`: Updated to reflect `k150_fixes` run results (Recall@1 70.8% → 80.8%, Recall@10 81.8% → 87.8%, misses@10 91 → 61)

### Fixed
- `kg.py`: Ranking sort key corrected — `base_dist` (vector distance) is now the primary sort key ahead of `prov.best_hop`; previously `best_hop` dominated, causing higher-hop but semantically closer nodes to outrank better semantic matches

### Renamed
- **Package restructuring:** `src/doc_kg/` → `src/memory_kg/` — major branding update from "DocKG" to "MemoryKG" across all skills, documentation, CLI, and internal references. All 113 files updated for the new naming convention.

### Added
- `cmd_snapshot.py`: `memorykg snapshot prune` command — removes vestigial snapshots (metric-duplicates, broken manifest entries, orphaned JSON files) while always preserving the oldest and newest; supports `--dry-run`
- `snapshots.py`: Re-export `PruneResult` from `kg_snapshot.snapshots` in the public API
- `.mcp.json`: MCP server configuration (copilot-memory, skills-copilot, task-copilot, pycodekg, memorykg) now tracked in git; `.gitignore` un-ignored it and added `.agentkg/` to ignored paths
- `pyproject.toml`: `kgdeps` optional group with `pycode-kg`, `ftree-kg`, `agent-kg` (moved out of dev group); `detect-secrets` and `pdoc` added to dev deps; `testpypi` source added
- `pyproject.toml`: `[tool.poe.tasks.docs]` task for generating API docs with pdoc
- `.claude/settings.json`: Agent-kg `UserPromptSubmit` and `Stop` hooks for automatic conversation ingestion

### Changed
- `pyproject.toml`: `kg-snapshot` dependency switched from git source to TestPyPI published package (`>=0.3.0`); pylint config refactored to opt-in only (cyclic-import, broad-exception-caught, cell-var-from-loop, undefined-variable, import-outside-toplevel); mypy upgraded to Python 3.13 with `mypy_path` and `explicit_package_bases`; ruff `E501` (line-length) suppressed; `types-pyyaml` removed from dev deps
- `.memorykg/snapshots/`: Pruned vestigial metric-duplicate snapshots from the repository

### Fixed
- `cmd_pipeline.py`: Cast `strategy: str` to `Literal["sentence_group", "semantic"]` for `PipelineConfig.chunk_strategy` to resolve mypy `arg-type` error
- `topics.py`: Added `# type: ignore[import-untyped]` on `import yaml` to resolve mypy `import-untyped` error (stubs not installed)
- `snapshots.py`: Added Author/License/Last Revision docstring header

- `settings.json.template`: Claude Code hooks template for agent-kg conversation ingestion — captures `UserPromptSubmit` and `Stop` events to the local agent-kg store asynchronously
- `PipelineConfig.sampling_strategy`: configurable Phase 1 sampling strategy (default `"diversity"`); was previously hardcoded — now wired through from the `--sampling` CLI option in `pipeline_run`

### Changed
- `pyproject.toml`: dev group marked `optional = true`; `code-kg` dev dep replaced with `pycode-kg` (new repo `Flux-Frontiers/pycode_kg`); `agent-kg` dev dep added (`Flux-Frontiers/agent_kg`); pylint `invalid-name` and `no-member` globally suppressed (ML matrix naming conventions; `SnapshotMetrics` typed-accessor attrs are false positives against the base `dict` type)

### Fixed
- `pipeline.py`: added `TYPE_CHECKING` guard import for `SentenceTransformerEmbedder` and typed `self._embedder: SentenceTransformerEmbedder | None` to resolve mypy `attr-defined` error; moved `if TYPE_CHECKING:` block after regular imports to fix pylint `wrong-import-position` (C0413)
- `topics.py`: initialized `self._kmeans: Any` and `self._cluster_labels: list[str]` in `__init__` (fixes pylint `attribute-defined-outside-init`); typed `_kmeans` as `Any` to eliminate mypy `attr-defined` errors on `.fit()`, `.predict()`, and `.cluster_centers_`
- `sampler.py`: renamed ML matrix variables `X` / `X_scaled` → `features_arr` / `features_scaled` for pylint naming compliance
- `topics.py`: renamed `X` → `embeddings_arr` in `fit_clusters` for consistency
- `embedder_worker.py`: added missing docstring to `n_vectors` property (fixes pylint `missing-function-docstring`)
- `cmd_pipeline.py`: wired `sampling` CLI arg into `PipelineConfig` (was silently ignored, triggering pylint `unused-argument`)
- `tests/test_snapshots.py`: fixed three failing snapshot tests (`test_list_snapshots_limit_zero_returns_all`, `test_snapshot_manager_get_previous`, `test_snapshot_manager_get_baseline`) — all failed because `save_snapshot` deduplicates entries with identical `version` + `metrics`; fixed by passing distinct `nodes=` counts per snapshot

- `scripts/generate_wiki.py`: Script to generate and publish GitHub wiki pages from `docs/` markdown files
- `poetry.toml`: `in-project = true` Poetry virtualenv configuration
- `src/memory_kg/__init__.py`: Package-level `__init__` exporting `MemoryKG` for cleaner imports
- `cli/cmd_model.py`: `memorykg download-model` command to download and cache embedding models for offline use; supports `--force` re-download and `trust_remote_code` for `nomic-ai/*` models
- `pyproject.toml`: `einops` dependency added (required by `nomic-embed-text-v1`)
- `generate_wiki.py`: Wiki generation script added to project root
- `analysis/memory_kg_analysis_20260320.md`: MemoryKG architectural analysis report (2026-03-20)

### Changed
- `cli/options.py`, `cli/cmd_build.py`, `cli/cmd_query.py`, `cli/cmd_snapshot.py`: `--sqlite` and `--lancedb` options now default to `None`; each command resolves the paths relative to `<repo>/.memorykg/` when not supplied, so the CLI works correctly regardless of the caller's working directory
- `cli/cmd_build.py`: Build output redesigned with Rich — section `Rule` headers, per-kind node counts (no raw Python dict dumps), features listed inline; embedder model name and dimension shown in summary; all three build commands (`build`, `build-graph`, `build-index`) updated consistently
- `index.py`: `SemanticIndex.build()` now shows a Rich progress bar (transient, with count and elapsed time) during batch embedding when `quiet=False`; `build()` stats dict now includes `model_name`
- `cli/cmd_hooks.py`: Pre-commit hook reordered — snapshot capture now runs *before* quality checks so the tree hash reflects staged content; snapshot failure is now non-fatal (warning only, does not abort commit); skip env var renamed from `CODEKG_SKIP_SNAPSHOT` to `DOCKG_SKIP_SNAPSHOT`
- `cli/main.py`: Registered `cmd_model` subcommand; updated usage docstring with `download-model`
- `index.py`: `SentenceTransformerEmbedder.__init__` now suppresses HF logging via `hf_logging.set_verbosity_error()`, wraps model load with `TQDM_DISABLE=1`, and passes `trust_remote_code=True` for `nomic-ai/*` models
- `analysis/CodeKG_Agent_instructions.md` renamed to `analysis/MemoryKG_Agent_instructions.md`

### Changed
- `pyproject.toml`: `kg-snapshot` dependency switched from local path (`../kg_snapshot`) to published git source (`github.com/Flux-Frontiers/kg_snapshot`); `kg-rag` dev dependency removed
- `src/memory_kg/snapshots.py`: Updated docstring module references from `kg_rag.snapshots` to `kg_snapshot.snapshots`

### Fixed
- `memorykg.py`: Changed `DEFAULT_MODEL` from `all-mpnet-base-v2` to `nomic-ai/nomic-embed-text-v1`; fixed the HuggingFace 404 error caused by the nonexistent `sentence-transformers/nomic-embed-text` model ID

## [0.4.1] - 2026-03-18

### Added
- `snapshots.py`: `_package_version()` helper that auto-detects the installed `doc-kg` version via `importlib.metadata`

### Changed
- `snapshots.py`: `Snapshot.version` field is now optional (default `""`); auto-populated from the installed package when not explicitly supplied
- `snapshots.py`: `SnapshotManager.capture()` `version` parameter is now optional (`None` by default); falls back to `_package_version()` when omitted
- `snapshots.py`: `Snapshot.from_dict()` now calls `data.setdefault("version", "")` for backward-compatible loading of snapshots that predate the optional field
- `cli/cmd_snapshot.py`: `VERSION` CLI argument for `memorykg snapshot save` is now optional (default `""`)
- `cli/cmd_hooks.py`: pre-commit hook no longer reads version from `pyproject.toml`; calls `memorykg snapshot save` without a version argument, relying on auto-detection
- `cli/cmd_hooks.py`: skip env var renamed from `DOCKG_SKIP_SNAPSHOT` to `CODEKG_SKIP_SNAPSHOT` for consistency with CodeKG convention
- `pyproject.toml`: `code-kg` (git) dependency moved from `main` to `dev` group; `ftree-kg` (git) dev dependency added

## [0.4.0] - 2026-03-14

### Added
- VS Code workspace file (`src/memory_kg/memory_kg.code-workspace`) for IDE integration
- `analysis/memory_kg_analysis_20260314.md`: CodeKG architectural analysis report (2026-03-14)
- `Snapshot.issues` field: list of issue-description strings now stored per snapshot
- `Snapshot.key` property: stable alias for `tree_hash`, used as the file key throughout

### Changed
- `src/memory_kg/snapshots.py`: replaced `commit` field with `tree_hash` as the stable snapshot key
  - `Snapshot.commit` removed; `Snapshot.tree_hash` is the new primary identifier
  - `Snapshot.key` property returns `tree_hash` for use as file key and manifest lookup
  - `SnapshotManager._get_current_commit()` renamed to `_get_current_tree_hash()`
  - `capture()` accepts `tree_hash` kwarg (was `commit`); auto-detects via `git write-tree` if omitted
  - `from_dict()` silently drops legacy `commit` field for backward-compatible loading
  - `load_snapshot()` now backfills `vs_previous` from manifest ordering when absent in the JSON file
  - Updated module docstring with full usage example and field-level inline comments
- `src/memory_kg/cli/cmd_snapshot.py`: `--commit` CLI option renamed to `--tree-hash`; issues list forwarded to `capture()`
- `.github/workflows/snapshots.yml`: updated `memorykg snapshot save` invocation from `--commit` to `--tree-hash`
- `tests/test_snapshots.py`: full test suite rewrite — all tests ported to `tree_hash`-based API, helper `_make_snapshot` replaced by `_make_memorykg_snapshot`, added new tests for git helpers, `vs_previous` backfill, and `issues` field
- `src/memory_kg/cli/group.py`: new module that houses the root Click group, extracted from `main.py` to eliminate circular imports between the entry-point and `cmd_*` submodules
- `pylint ^4.0.5` dev dependency with full `[tool.pylint.*]` configuration in `pyproject.toml` (design/format/similarities/messages_control sections)
- `code-kg` (git) dependency added to `pyproject.toml` for CodeKG integration
- All `cmd_*` CLI modules (`cmd_analyze`, `cmd_build`, `cmd_hooks`, `cmd_mcp`, `cmd_query`, `cmd_snapshot`, `cmd_viz`) now import `cli` from `memory_kg.cli.group` instead of `memory_kg.cli.main`, resolving circular import issues
- `src/memory_kg/cli/main.py`: reduced to re-exporting `cli` from `group.py` and registering submodule imports
- `src/memory_kg/cli/cmd_hooks.py`: Enhanced pre-commit hook with quality checks integration
  - Hook now runs `.pre-commit-config.yaml` checks (ruff, mypy, detect-secrets, etc.) before snapshot capture
  - Hook rebuilds local MemoryKG index (`memorykg build --wipe`) to keep it in sync with commits
  - Changed success message from `✓` emoji to `OK` prefix
- `.github/workflows/snapshots.yml`: Refactored snapshot workflow for consistency
  - Simplified build phase to use unified `memorykg build --wipe` instead of separate `build-graph` and `build-index` commands
  - Changed snapshot keying from short commit hash (`SHORT_COMMIT`) to full tree hash (`TREE_HASH` via `git write-tree`)
  - Replaced ad-hoc `memorykg analyze` output with structured `memorykg snapshot save` command
  - Workflow now commits and pushes snapshots directly to repository instead of uploading as artifacts
- `.pre-commit-config.yaml`: Fixed pylint hook to run via `poetry run` for access to project dependencies (was failing with import errors)
- `pyproject.toml`: Updated `pre-commit` dependency to `^4.5.1`
- `src/memory_kg/relations.py`: split overlong regex literal across multiple lines; simplified `cooccur_pairs` to `list(itertools.combinations(...))` directly
- Code quality: added missing public-method docstrings in `kg.py`, `snapshots.py`, `app.py`; added targeted `pylint: disable` annotations in `memorykg.py`, `index.py`, `mcp_server.py`, `topics.py`; fixed bare `except ImportError` chain in `cmd_mcp.py`

## [0.3.0] - 2026-03-12

### Added
- `memorykg install-hooks` CLI command: installs a MemoryKG pre-commit hook that captures a metrics snapshot (keyed by tree hash) and stages it atomically — mirrors CodeKG hook pattern; skip with `DOCKG_SKIP_SNAPSHOT=1` env var
- `src/memory_kg/cli/cmd_hooks.py`: hook installation module with embedded pre-commit hook script
- Documentation updates:
  - `docs/CHEATSHEET.md`: rewritten for MemoryKG MCP tools (`graph_stats`, `query_docs`, `pack_docs`, `get_node`)
  - `docs/SNAPSHOTS.md`: updated from CodeKG to MemoryKG snapshots (metrics for document corpora, not code)
  - `docs/deployment.md`: rewritten for MemoryKG deployment options (PyPI, Streamlit Cloud, Fly.io, MCP server)
  - `docs/memorykg_workflow.md`: new practical workflow guide showing `memorykg build`, `query`, `pack`, `analyze`, `viz`, `snapshot` commands
- `scripts/install-hooks.sh`: installs a MemoryKG pre-commit hook that captures a metrics snapshot (keyed by tree hash) and stages it atomically — mirrors CodeKG hook pattern; skip with `DOCKG_SKIP_SNAPSHOT=1`
- `--exclude-dir` CLI option on `build` and `build-graph` commands: exclude directory names at every depth during file walk (repeatable, merged with config)
- `src/memory_kg/config.py`: new module with `load_exclude_dirs()` to read `[tool.memorykg].exclude` from pyproject.toml — mirrors CodeKG pattern
- `.memorykg/snapshots/`: initial 6-commit snapshot history (migrated from `.codekg/snapshots/` where bad hook was writing them)
- MCP server (`src/memory_kg/mcp_server.py`): `memorykg mcp` / `memorykg-mcp` entry point exposing `graph_stats`, `query_docs`, `pack_docs`, and `get_node` tools for MCP-compatible agents (Claude Code, Claude Desktop, GitHub Copilot, Cursor, Continue)
- Streamlit visualizer (`src/memory_kg/app.py`): interactive PyVis-based graph explorer with per-node-kind colour/shape coding and per-relation-kind edge colours
- CLI subcommands: `memorykg mcp`, `memorykg analyze`, `memorykg viz`, `memorykg build-graph`, `memorykg build-index`
- `MemoryKGAnalyzer` (`src/memory_kg/memorykg_thorough_analysis.py`): nine-phase corpus analysis engine (baseline metrics, semantic coverage, top documents, hot chunks, strengths/weaknesses)
- Snapshot management (`src/memory_kg/snapshots.py`, `src/memory_kg/cli/cmd_snapshot.py`): `memorykg snapshot save|list|show|diff` for temporal tracking of metrics across versions (commits, branches, coverage)
- GitHub workflows and actions: CI pipeline, publish workflow, snapshot CI, and MemoryKG reusable action for automated knowledge graph building
- `mcp>=1.0.0` dependency
- `types-pyyaml^6.0.12.20250915` for type hints
- CLI smoke tests (`tests/test_cli.py`): verify all subcommands are registered via Click `CliRunner`

### Changed
- All CLI commands now use `--repo` (named option) instead of a positional `corpus_root` argument, matching the CodeKG CLI pattern; `repo_option` shared decorator added to `src/memory_kg/cli/options.py`; affected commands: `build`, `build-graph`, `build-index`, `analyze`, `query`, `pack`, `mcp`
- `src/memory_kg/memorykg.py`: `SKIP_DIRS` documented with per-entry comments and a block comment explaining the additive exclusion contract
- `pyproject.toml`: removed redundant `[tool.memorykg].exclude` list (all entries duplicated `SKIP_DIRS`); replaced with template comment; removed contradictory `ignore = ["E501"]`; cleaned up stale blank lines
- `.gitignore`: generalized `.memorykg/*.sqlite*` glob to cover all SQLite files (was only excluding `graph.sqlite`, missing `docs.sqlite` and future DBs); removed stale `.memorykg/docs_lancedb/` entry; consolidated lancedb pattern to `lancedb*`
- `MemoryKG.__init__` now accepts `exclude: set[str] | None` parameter, forwarded to DocGraph for file walk filtering
- `src/memory_kg/cli/cmd_build.py`: `build` and `build-graph` commands now merge `--exclude-dir` flags with `[tool.memorykg].exclude` from pyproject.toml
- `docs/MCP.md` rewritten as a MemoryKG-specific MCP setup guide covering all supported clients; added example of excluding directories
- `README.md`: documented `--exclude-dir` option and exclude priority order (built-in SKIP_DIRS + pyproject.toml + CLI flags)
- `src/memory_kg/cli/main.py`: registers `cmd_analyze`, `cmd_mcp`, `cmd_viz` subcommands
- `src/memory_kg/cli/cmd_build.py`: extended with `build-graph` and `build-index` split commands
- `analysis/memory_kg_analysis_20260308.md`: replaced with fresh MemoryKG-native analysis (1 537 nodes, 8 358 edges; 97.4% topic coverage)

### Removed

### Fixed
- `Snapshot.from_dict()` crashes on legacy snapshot JSON files that use old field names (`docstring_coverage`, `critical_issues`); added migration shim that renames them to `coverage_score` / `issues_count` on load

## [0.2.0] - 2026-03-08

### Added
- `memorykg install-hooks` CLI command
- MCP server, Streamlit visualizer, `analyze`, `viz`, `build-graph`, `build-index` subcommands
- Snapshot management (`memorykg snapshot save|list|show|diff`)

## [0.1.0] - 2026-03-08

### Added
- Initial MemoryKG implementation — document knowledge graph from `.md` / `.txt` files
- `memorykg build`, `memorykg query`, `memorykg pack` CLI commands
- Hybrid semantic + structural graph (SQLite + LanceDB)
- Default embedding model: `all-mpnet-base-v2`

### Changed

### Removed

### Fixed
