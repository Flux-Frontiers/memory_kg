# PyCodeKG × SWE-bench — File-Localization Retrieval

The benchmark that meets *"AI Agents Don't Need Vector Search Anymore"* (Grewal,
2026) on its **own ground: code retrieval**. The other benchmarks in this repo test
document/memory retrieval; this one tests the exact task the article is about —
*given a real GitHub issue, which file(s) must an agent edit to fix it?*

This harness drives **PyCodeKG** (the sibling package, `pip install pycode-kg`),
whose typed AST graph (`CALLS`/`IMPORTS`/`INHERITS`/`CONTAINS`/`RESOLVES_TO`) is the
direct answer to the article's #1 criticism — *"semantic similarity misses imports
and call graphs."* SWE-bench's gold patches give a ground-truth localization target,
so we can score that claim instead of arguing it.

> It lives in the `memory_kg` repo for now because that's where this analysis branch
> is; it imports `pycode_kg`, not `memory_kg`, and is meant to graduate into the
> `pycode_kg` repo. It is the retrieval benchmark PyCodeKG currently lacks.

## Task & metrics

For each SWE-bench instance: check out the repo at `base_commit`, build a PyCodeKG,
query with the issue's `problem_statement`, and rank the **source files** of the
retrieved nodes against the files the gold patch modifies (à la Agentless / Moatless
file localization). All scoring is LLM-free and deterministic:

| Metric | Meaning |
|---|---|
| `recall@k` | ≥1 gold file in the top-k retrieved files |
| `recall_all@k` | *every* gold file in the top-k (the honest multi-file metric) |
| `MRR` | 1 / rank of the first gold file |

The article's head-to-head is one flag (same as the HotpotQA harness):

| `--hop` | Behaviour | Maps to |
|--------:|-----------|---------|
| `0` | pure semantic top-k | the flat RAG baseline the article defends |
| `1` | semantic seed **+** AST graph expansion | PyCodeKG's structural recovery |

## Running it

```bash
pip install pycode-kg                       # sibling package, not a memory_kg dep
export PYCODEKG_DEVICE=cpu                   # or mps/cuda

# One small repo, end to end (flask clones fast; astropy/django are heavy):
python benchmarks/swebench/swebench_pycodekg.py --dataset lite --repo pallets/flask --hop 1

# The article's comparison on a 20-instance sample:
python benchmarks/swebench/swebench_pycodekg.py --dataset lite --limit 20 --hop 0
python benchmarks/swebench/swebench_pycodekg.py --dataset lite --limit 20 --hop 1

# SWE-bench Verified (500 human-validated instances):
python benchmarks/swebench/swebench_pycodekg.py --dataset verified --limit 50 --hop 1
```

`--repo` filters to one repo (or an instance-id substring) so you can pick light
repos for a quick run. Cloned repos are cached under `--repos-cache`; the per-repo
KG is built fresh per instance (the `base_commit` differs).

## Cost note (it's the article's point, made concrete)

Cloning real repos and building a full AST KG is heavy — minutes per large repo. That
cost is **paid once per repo/commit**, then every subsequent query is a millisecond
SQLite+LanceDB lookup with no LLM in the loop. That is exactly the precompute↔JIT
trade the article describes: agentic `grep` pays a smaller fixed cost but re-derives
structure on *every* query, non-deterministically. For a repo analysed repeatedly
(CI, review, onboarding) the precomputed graph wins on cost, latency, and
reproducibility.

## First results (SWE-bench Lite, n=13: requests/flask/seaborn, BGE-small, CPU)

Build-once / query-both-hops, identical graph per instance (~27 s/instance):

| metric | hop 0 (flat) | hop 1 (+AST graph) |
|---|--:|--:|
| recall@1 | 0.308 | 0.308 |
| recall@5 | **0.769** | **0.769** |
| recall@10 / @20 | 0.769 | 0.769 |
| MRR | 0.487 | 0.487 |

**Symbol-level scoring** (does retrieval surface the specific function/method/class the
patch edits — node span overlaps a gold base-commit line; the regime where `CALLS`
expansion *should* help):

| metric | hop 0 | hop 1 |
|---|--:|--:|
| sym_recall@5 | 0.538 | 0.538 |
| sym_recall@10 | 0.692 | 0.692 |
| sym_recall@20 | 0.692 | **0.769** |
| sym_mrr | 0.365 | 0.372 |

**Three honest takeaways:**

1. **Flat PyCodeKG retrieval is already competitive** — gold file in the top-5 on
   10/13 (0.77), MRR 0.49, fully deterministic, $0/query, no LLM. That is the number
   that matters against agentic `grep` (5–30× tokens, seconds of latency, non-reproducible).
2. **Hop expansion is null at file granularity (Δ = 0.000)** — each Lite instance edits
   one file; once seeding surfaces it, `CALLS`/`IMPORTS` neighbours map to files already
   ranked.
3. **Hop expansion is *essentially* null even at symbol granularity** — the regime built
   to favour it. Δ symbol-MRR = +0.006; hop-1 recovered exactly **one** gold symbol, and
   only at rank ≤20. Symbol localization is genuinely harder (sym_recall@10 = 0.69 vs
   file 0.77), but the call graph does not meaningfully rerank it here.

## Multi-file regime (SWE-bench Verified, n=14, gold patch edits ≥2 files)

Run with `--dataset verified --min-gold-files 2` on light-ish repos
(seaborn/xarray/pylint/pytest) — the regime where cross-file `CALLS`/`IMPORTS`
expansion *should* help, because the second file's edited symbol is reachable
structurally but not necessarily by similarity to the issue text.

| metric | hop 0 | hop 1 | Δ |
|---|--:|--:|--:|
| file recall@10 | 0.929 | 0.929 | 0.000 |
| file recall_all@10 (both files) | 0.214 | 0.214 | 0.000 |
| sym_recall@10 | 0.571 | 0.643 | **+0.071** |
| sym_recall@20 | 0.571 | **0.786** | **+0.214** |
| sym_mrr | 0.357 | 0.376 | +0.018 |

**This is the first place hop-expansion helps — and it does, cleanly.** 3 of 14
instances recovered a gold symbol that flat retrieval missed entirely (sym@20 0→1),
**zero regressed**, and all three wins are the **pylint multi-file fixes (2–4 gold
files)** — the gain grows with how many files the change spans. The recovered symbols
surface at deeper ranks (the lift is at @20, modest at @10), so expansion *finds* the
cross-file bridge symbol but ranks it only moderately. File-level and `recall_all` are
unchanged: getting *both* files is hard (0.21) and expansion doesn't help there.

## The full picture — structural expansion is regime-specific

| benchmark / regime | does hop>0 help? |
|---|---|
| HotpotQA (dense passage QA, co-occurrence edges) | **hurts** (−0.09 recall_all@5) |
| SWE-bench single-file, file-level | null (Δ 0.000) |
| SWE-bench single-file, symbol-level | ~null (Δ MRR +0.006) |
| SWE-bench **multi-file, file-level** | null (Δ 0.000) |
| SWE-bench **multi-file, symbol-level** | **helps** (+0.21 sym_recall@20, 3/14, no regressions) |

The honest conclusion is not "graphs win" or "graphs don't help" — it's that
**retrieval topology must match data topology.** Cross-file AST expansion helps exactly
where the answer is cross-file and structural (multi-file symbol localization) and
nowhere else. Alongside that, PyCodeKG's deterministic substrate and *structural query
capabilities* (callers, fan-in, dead code — see `benchmarks/capabilities/`) are value
flat embeddings can't provide at all. See `analysis/agentic_search_2026_analysis.md`.

## Verification status

- ✅ Dataset download (HF parquet), instance loading, gold-file parsing — verified on
  real SWE-bench Lite.
- ✅ **Full end-to-end verified** on `pallets__flask-4045` with PyCodeKG v0.19.3
  (clone → AST KG build → query → score): gold file `src/flask/blueprints.py`
  retrieved at **rank 2** (`tests/test_blueprints.py` ranked first), `recall@5=1.0`,
  MRR=0.5, ~147 s for the one instance (build-dominated). See
  `results_swebench_lite_hop1_flask4045.json`.
- Note the realistic localization nuance even in this single case: the *test* file
  out-ranked the *source* file by semantic similarity alone — exactly the kind of
  near-miss the AST graph (`CONTAINS`/`CALLS` from the failing test to the
  implementation) is meant to correct. That's the signal the full hop-0 vs hop-1
  sweep is designed to measure.
