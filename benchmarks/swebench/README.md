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

**Two honest takeaways:**

1. **Flat PyCodeKG retrieval is already competitive** — gold file in the top-5 on
   10/13 instances (0.77), MRR 0.49, fully deterministic, $0/query, no LLM. That is
   the number that matters against agentic `grep` (which pays 5–30× tokens and seconds
   of latency for a non-reproducible answer).
2. **Graph hop expansion changed *nothing* at file granularity (Δ = 0.000).** Every
   Lite instance here edits a single file; once semantic seeding surfaces that file,
   adding `CALLS`/`IMPORTS` neighbours maps to files already in the ranking. Hop
   expansion is the wrong lever for *file*-level localization — it would matter for
   *symbol*-level localization or multi-file fixes, and that's the next thing to
   measure (`--rels`, symbol-granularity scoring, SWE-bench Verified at larger n).

This mirrors the HotpotQA finding: **structural expansion is not a free ranking win.**
PyCodeKG's edge over flat embeddings is its deterministic substrate and its
*structural query capabilities* (callers, fan-in, centrality), not hop-expanded
ranking. See `analysis/agentic_search_2026_analysis.md`.

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
