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

## Verification status

- ✅ Dataset download (HF parquet), instance loading, gold-file parsing — verified on
  real SWE-bench Lite.
- ✅ PyCodeKG integration (`PyCodeKG(...).build()/.query()`, `module_path` → file
  localization) — wired to the confirmed v0.19.3 API.
- See `results_*.json` for committed sample runs.
