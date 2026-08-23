# 2026-08 benchmark re-run

**Date:** 2026-08-23
**Repository:** memory_kg @ `4400f39` (v0.8.0, sqlite-vec, kgmodule-utils 0.18.0 relock)
**Trigger:** [`benchmarks/RETEST_PLAN.md`](../RETEST_PLAN.md) — internal number disagreements between
`README.md`, `RESULTS_SUMMARY.md`, and the external essay, plus no sqlite-vec parity runs for
LoCoMo or MemBench, plus the 2026-08-23 dependency relock (`c46e458`) never having been
benchmark-validated.

## Status

| Benchmark | Claimed | Reproduced | Delta | Verdict |
|---|--:|--:|--:|---|
| LoCoMo (session recall) | 98.1% | 98.09% | -0.01 pp | PASS |
| MemBench (recall@20) | 87.7% | 87.81% | +0.11 pp | PASS |
| ConvoMem (tier-1 recall@20) | 96.3% | 96.27% | -0.03 pp | PASS |
| LongMemEval-S (R@5 / R@10) | disputed: 98.4%/99.4% vs. 97.6%/99.2% | pending | — | not yet run |

Three of four benchmarks are re-verified clean against the current code and relocked
dependencies (all within the plan's 0.5 pp acceptance threshold). LongMemEval-S — the one
benchmark with an actual internal number dispute to resolve — has not been run yet.

## The confirmed README defect

[`README.md`](../../README.md) currently claims:

> MemoryKG achieves **100% retrieval recall on the ConvoMem benchmark — every evidence message
> found, on every question, across 17,463 items**

This is wrong, and was already known to be wrong: `benchmarks/convomem/BENCHMARKS_CONVOMEM.md`
documents that the 100%/17,463-item figure came from a scoring bug (an empty-node false match),
fixed 2026-04-26, with the corrected result being **96.3% tier-1 recall across 1,897 items**. This
re-run reproduces that corrected number exactly (96.27%) on the current v0.8.0 code, closing the
question of whether the fix still holds — it does. The README has not been updated to match. Four
places in `README.md` repeat the stale claim (lines 16, 183, 194, 214 as of this commit).

## Headline: claimed vs. reproduced

![Claimed vs. reproduced recall](headline_claimed_vs_reproduced.png)

## ConvoMem — recall by tier

![ConvoMem recall by tier](convomem_by_tier.png)

Tiers 1-2 reproduce the LanceDB-era per-item results exactly; tiers 3-4 differ by a handful of
items due to pre-existing cross-process nondeterminism in graph expansion (documented in
`BENCHMARKS_CONVOMEM.md`), not the sqlite-vec migration.

![ConvoMem tier-1 recall by category](convomem_tier1_by_category.png)

## LoCoMo — first sqlite-vec parity run

No LanceDB-era parity run existed for this benchmark before now.

![LoCoMo session recall by category](locomo_by_category.png)

## MemBench — first sqlite-vec parity run

No LanceDB-era parity run existed for this benchmark before now. `noisy` (42.0%) and
`post_processing` (72.0%) are the weakest categories, consistent with their intent (adversarial
distractors and multi-step synthesis) rather than a regression.

![MemBench recall@20 by category](membench_by_category.png)

## Reproduce

```bash
cd /Users/egs/repos/memory_kg
env -u VIRTUAL_ENV -u POETRY_ACTIVE poetry install --sync --with dev

# LoCoMo
poetry run python benchmarks/locomobench/locomo_bench_memkg.py prepare \
  benchmarks/locomobench/data/locomo10.json --wipe
poetry run python benchmarks/locomobench/locomo_bench_memkg.py run \
  benchmarks/locomobench/data/locomo10.json

# MemBench
poetry run python benchmarks/membench/membench_bench.py all \
  --topic all --limit 100 --k 20 --wipe

# ConvoMem
poetry run python benchmarks/convomem/convomem_bench.py --tier 1 --k 20
poetry run python benchmarks/convomem/convomem_bench.py --tier 2 --k 20
poetry run python benchmarks/convomem/convomem_bench.py --tier 3 --k 20
poetry run python benchmarks/convomem/convomem_bench.py --tier 4 --k 20
```

## Outstanding

- **LongMemEval-S** has not been re-run — its corpus build is heavy (528k+ nodes, full session
  haystacks) and ran hot enough on Apple Silicon MPS to require killing the first attempt.
  Pending a lighter-weight run (`--device cpu --workers 4`, or similar).
- **README.md** still needs the ConvoMem claim corrected (100%/17,463 items -> 96.3%/1,897 items,
  four locations) regardless of the LongMemEval-S outcome.
- Per `RETEST_PLAN.md`, once LongMemEval-S is re-run, `RESULTS_SUMMARY.md` needs a "2026-08
  re-run" section resolving the 97.6%-vs-98.4% dispute, and the corrected numbers propagate to
  the external essay in `kgrag_priv/articles/the_shape_of_the_thing/`.
