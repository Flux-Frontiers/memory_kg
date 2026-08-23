# Benchmark re-test plan, August 2026

Re-run all four retrieval benchmarks against current `memory_kg` HEAD and
record one canonical set of numbers. The published claims are being cited in
"The Shape of the Thing" (kgrag_priv), and the recorded numbers no longer
agree with each other or provably with the current code.

## Why re-run

Three things have changed or gone wrong since the April 2026 runs:

1. **The recorded numbers disagree.** For LongMemEval-S:
   - `benchmarks/README.md` reports R@5 98.4%, R@10 99.4% (baseline).
   - `benchmarks/RESULTS_SUMMARY.md` reports 98.4%/99.4% in its head-to-head
     table but 97.6%/99.2% with "4 misses" in its prose, and NDCG@10 0.943 in
     the table but 0.936 in the prose.
   - The essay quotes 97.6% R@5, 99.2% R@10, and four misses at R@10.

   At least one of these is stale. The re-run decides which configuration is
   canonical; every document then quotes that one.

2. **The vector store changed under the results.** Version 0.7.0 (2026-08-02)
   migrated `SemanticIndex` from LanceDB (squared L2) to sqlite-vec (cosine).
   Distance scales halved and tie-breaking can differ. Parity runs exist for
   LongMemEval (`results_sqlitevec_parity.jsonl`) and ConvoMem
   (`results_*_sqlitevec.json`), but not for LoCoMo or MemBench.

3. **Dependencies were relocked on 2026-08-23** (`c46e458`): kgmodule-utils
   and doc-kg moved to current PyPI versions. No benchmark has run against
   the relocked environment.

## Scope

| Benchmark | Script | Claimed result | sqlite-vec parity run exists |
|---|---|---|---|
| LongMemEval-S | `longmemeval/longmemeval_memkg.py` | 97.6 or 98.4% R@5 (see above) | Yes |
| LoCoMo | `locomobench/locomo_bench_memkg.py` | 98.1% session recall | No |
| MemBench | `membench/membench_bench.py` | 87.7% recall@20 | No |
| ConvoMem | `convomem/convomem_bench.py` | 96.3% recall@20 tier 1, 88.7% overall | Yes |

All runs are zero-inference retrieval: no LLM, no reranker, no API key. The
MemPalace comparison rows are fixed published values and are not re-run;
verify only that the quoted rows match the MemPalace source.

## Prepare the environment

1. Sync the venv to the lock and confirm the suite passes before any
   benchmark run:

   ```bash
   cd /Users/egs/repos/memory_kg
   env -u VIRTUAL_ENV -u POETRY_ACTIVE poetry install --sync --with dev
   env -u VIRTUAL_ENV -u POETRY_ACTIVE poetry run pytest
   ```

2. Record in the results header: `memory_kg` commit SHA, package version,
   `kgmodule-utils` version from `poetry.lock`, embedding model and
   revision (BGE-small-en-v1.5), and the machine.

3. Verify the datasets are present before building corpora:
   - `longmemeval/data/longmemeval_s_cleaned.json` (present as of
     2026-08-23). During prepare, confirm the session count and correct the
     essay's "23,867 conversation sessions" figure if it differs.
   - `locomobench/data/` (locomo10.json; the script's `prepare --download`
     fetches it if missing)
   - `membench/data/` corpora (present)
   - ConvoMem input per `convomem/BENCHMARKS_CONVOMEM.md`

## Run the benchmarks

Rebuild every corpus from scratch (`prepare --wipe` where the script
supports it) so no pre-migration index survives into the measurement.

1. **LongMemEval-S.** Run both recorded configurations, since the canonical
   number is in dispute:
   - baseline: BGE-small, hop=1, k=50, haystack filter on
   - sibling boost variant

   ```bash
   env -u VIRTUAL_ENV -u POETRY_ACTIVE poetry run python \
     benchmarks/longmemeval/longmemeval_memkg.py prepare \
     benchmarks/longmemeval/data/longmemeval_s_cleaned.json --wipe
   env -u VIRTUAL_ENV -u POETRY_ACTIVE poetry run python \
     benchmarks/longmemeval/longmemeval_memkg.py run \
     benchmarks/longmemeval/data/longmemeval_s_cleaned.json
   ```

   Report R@1, R@5, R@10, Recall_all@10, NDCG@10, and the miss count, so
   every number quoted anywhere has a fresh counterpart.

2. **LoCoMo.** First sqlite-vec run; compare against 98.1% session recall.

3. **MemBench.** First sqlite-vec run; compare against 87.7% recall@20
   overall and the per-category table in `benchmarks/README.md`. Keep
   per-item haystack scoping enabled; it is the load-bearing mechanism
   (8.9% without it).

4. **ConvoMem.** All four tiers at top-20, hop=1; compare against the
   existing `results_*_sqlitevec.json` files and the tier-1 96.3% claim.

## Acceptance criteria

- A metric within 0.5 percentage points of its canonical recorded value
  passes. Retrieval is deterministic, so expect exact agreement; small
  deltas can come from cosine-vs-L2 tie-breaking.
- A drop larger than 0.5 points on any headline metric is a regression:
  stop, bisect between the April SHA and HEAD, and file the finding before
  updating any document.
- LongMemEval must resolve the 97.6-vs-98.4 dispute: identify which
  configuration produced each recorded number, name one of them canonical
  in `RESULTS_SUMMARY.md`, and remove the conflicting figures.

## Record the results

1. Write timestamped result files beside each script, following the
   existing convention (`results_*_YYYYMMDD*.json[l]`).
2. Add a "2026-08 re-run" section to `RESULTS_SUMMARY.md` with the
   environment header from step 2 above, and fix its internal
   table-vs-prose contradiction.
3. Update the results table in `benchmarks/README.md` if any number
   changes.
4. Propagate the canonical LongMemEval numbers to the essay in
   `kgrag_priv/articles/the_shape_of_the_thing/` (both `.md` and `.tex`),
   which currently quotes 97.6% R@5, 99.2% R@10, four misses at R@10, and
   0.936 NDCG@10.

## Out of scope

- Re-running MemPalace itself; its published numbers are quoted as-is.
- Tuning. This is a verification pass: same configurations, current code.
  Any improvement work happens after the canonical baseline is re-established.
