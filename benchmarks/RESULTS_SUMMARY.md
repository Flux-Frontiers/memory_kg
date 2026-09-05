# MemoryKG × LongMemEval — Results Summary

**Canonical run:** 2026-08-26 (see below)
**Repository:** memory_kg @ `9754508` (v0.8.0, sqlite-vec, kgmodule-utils 0.18.0)
**Machine:** Apple M5 Max MacBook Pro, 64 GB RAM
**Benchmark:** LongMemEval-S, 500 questions, session-granularity retrieval
**Corpus:** 19,195 unique sessions → 528,083 nodes

---

## Canonical numbers (2026-08 re-run)

Re-run per [`RETEST_PLAN.md`](RETEST_PLAN.md) against current code and the
2026-08-23 dependency relock. Configuration is the documented baseline:
BGE-small-en-v1.5, k=50, hop=1, haystack-filtered seeding, max_nodes=1000.
Zero inference — no LLM, no reranker, no API key.

| @k | recall_any | recall_all | nDCG |
|---|--:|--:|--:|
| @1 | 0.904 | 0.306 | 0.904 |
| @3 | 0.972 | 0.898 | 0.945 |
| **@5** | **0.982** | **0.968** | **0.950** |
| **@10** | **0.992** | **0.988** | **0.954** |
| @30 | 1.000 | 0.994 | 0.955 |
| @50 | 1.000 | 1.000 | 0.956 |

**4 misses in 500 at @10** (`10d9b85a`, `gpt4_468eb064`, `eac54add`,
`gpt4_68e94288`). 339.7 s total, 0.68 s per question.
Raw results: `longmemeval/results_20260826_bge_haystack.jsonl`.

### How the 97.6-vs-98.4 dispute resolved

Three different figures were on record for R@5: 98.4% (this file's head-to-head
table and `README.md`), 97.6% (this file's prose and the external essay), and a
matching set of NDCG@10 values, 0.943 vs 0.936. None of them came from a
configuration you can select today.

The re-run reproduces **98.2% R@5 / 99.2% R@10 / 0.954 NDCG@10** — matching the
old "MemoryKG + sibling boost" row exactly on all three. That row is the
canonical one, because the sibling boost is **not optional**: it is applied
unconditionally to multi-session questions at `longmemeval_memkg.py:911`, with
no flag to disable it. There is only one configuration the current code can
produce.

So:

- **98.2% / 99.2% / 0.954 is canonical.** R@1 is 90.4%, which the old baseline
  row also reported.
- **98.4% / 99.4% / 0.943** was the pre-sibling-boost code state. Stale.
- **97.6%** was never a head-to-head result at all — it is the last row of the
  progression table below, an earlier code state that happened to also miss 4
  at @10. The prose conflated the two.
- **0.936 NDCG@10** matches no reproduced configuration and is withdrawn.

The conflicting figures have been removed from this file rather than
annotated, per the retest plan's acceptance criteria.

---

## Head-to-Head: MemoryKG vs MemPalace

| System | Model | Inference | R@1 | R@5 | R@10 | NDCG@10 |
|---|---|---|--:|--:|--:|--:|
| MemPalace raw | MiniLM | None | 96.6% | 96.6% | 98.2% | 0.889 |
| MemPalace hybrid v2 | MiniLM | None | — | **98.4%** | 99.0% | 0.934 |
| MemPalace hybrid v3 + Haiku | MiniLM | Haiku rerank | — | **99.4%** | **99.6%** | **0.975** |
| **MemoryKG (canonical)** | **BGE-small** | **None** | **90.4%** | **98.2%** | **99.2%** | **0.954** |

Read honestly, that is a split decision, not a sweep:

- **MemoryKG wins the zero-inference comparison at depth.** Against MemPalace
  hybrid v2 — the best no-inference configuration either system has — the graph
  takes NDCG@10 (0.954 vs 0.934) and R@10 (99.2% vs 99.0%).
- **MemPalace hybrid v2 leads at R@5 by 0.2 pp** (98.4% vs 98.2%), without
  inference. Earlier drafts claimed a tie here on the stale 98.4% figure; the
  reproduced number does not support that.
- **MemoryKG beats MemPalace's raw baseline** at R@5 by 1.6 pp (98.2% vs 96.6%)
  and at NDCG@10 by 0.065.
- **MemPalace's overall best still requires a Haiku reranking pass** (99.4% R@5,
  0.975 NDCG@10). MemoryKG closes most of that gap at zero marginal cost, but
  does not beat it.
- **R@1 is the weak spot**, 90.4% against MemPalace raw's 96.6%. The graph
  ranks the right session into the top 5 almost always and the top 10 nearly
  always, but is worse than MemPalace at putting it first.

MemPalace rows are published values quoted as-is; they were not re-run.

---

## Per-Type Breakdown (2026-08 re-run, @10)

| Question Type | n | recall_any@10 | recall_all@10 |
|---|--:|--:|--:|
| knowledge-update | 78 | 1.000 | 1.000 |
| multi-session | 133 | 0.992 | 0.985 |
| single-session-assistant | 56 | 1.000 | 1.000 |
| single-session-preference | 30 | 1.000 | 1.000 |
| single-session-user | 70 | 1.000 | 1.000 |
| temporal-reasoning | 133 | 0.977 | 0.970 |

Four of six types are perfect at @10. Both remaining misses are concentrated in
`temporal-reasoning` (3) and `multi-session` (1) — the two types that need
reasoning across sessions rather than retrieval within one.

This table is **@10 and not directly comparable** to the earlier @5 per-type
table it replaces, or to the MemPalace per-type figures, which are @5.

---

## MemoryKG Progression (April 2026 tuning session)

Historical record of how the retrieval numbers were reached. These rows are
**earlier code states**, not selectable configurations — see the dispute note
above before quoting any of them.

| Run | Model | hop | k | Haystack filter | R@5 | R@10 | Misses @10 |
|---|---|--:|--:|--:|--:|--:|--:|
| baseline | MiniLM | 1 | 50 | No | 75.8% | 81.8% | 91 |
| k150 + score-first ranking | MiniLM | 1 | 150 | No | 84.6% | 87.8% | 61 |
| BGE-small + hop=1 | BGE-small | 1 | 150 | No | 86.6% | 89.4% | 53 |
| MiniLM + haystack filter | MiniLM | 1 | 50 | Yes | 94.0% | 97.0% | 15 |
| BGE-small + haystack filter | BGE-small | 1 | 50 | Yes | 97.6% | 99.2% | 4 |
| **current code (2026-08-26)** | **BGE-small** | **1** | **50** | **Yes** | **98.2%** | **99.2%** | **4** |

The 97.6% in the second-to-last row is the figure that leaked into the prose
and the external essay as though it were the headline result. It is not.

---

## Key Changes That Drove Improvements

1. **Score-first ranking** (`base_dist` first in `_rank_key`, not hop distance) — +8.8 pp R@5
   File: `src/memory_kg/kg.py:558,636`

2. **k 50 → 150** (more seeds, better haystack coverage) — part of +8.8 pp
   File: `benchmarks/longmemeval/longmemeval_memkg.py:601`

3. **BGE-small-en-v1.5** replacing MiniLM-L6-v2 — +2.0 pp R@5 (without filter)
   File: `src/memory_kg/memorykg.py:58`

4. **Haystack-filtered seeding** — restrict sqlite-vec seeds to the ~50 per-question haystack sessions rather than the full 19,195-session corpus. Eliminates cross-corpus noise.
   The decisive fix: +9.4 pp R@5 (MiniLM) / +11.0 pp R@5 (BGE-small)
   Files: `src/memory_kg/index.py`, `src/memory_kg/kg.py`, `benchmarks/longmemeval/longmemeval_memkg.py`

5. **Skip question normalization for preference questions** — targeted fix for `single-session-preference` type
   File: `benchmarks/longmemeval/longmemeval_memkg.py:462`

---

## Architecture

```
Query
  │
  ├─ sqlite-vec vector search (k=50)
  │    └─ filtered to haystack session files only (50 sessions per question)
  │         └─ BGE-small-en-v1.5 embeddings (384d)
  │
  ├─ Graph expansion (hop=1)
  │    └─ edges: CONTAINS, NEXT, REFERENCES, HAS_TOPIC, MENTIONS_ENTITY, HAS_KEYWORD
  │
  ├─ Score-first ranking (base_dist → hop → semantic_boost → kind_priority)
  │
  └─ Temporal re-rank for temporal-reasoning questions (date proximity boost)
```

**No inference. No LLM. No API key required.**

---

## Remaining 4 Misses @k=10

Four questions are missed at k=10, unchanged in count from April:

- `10d9b85a`, `eac54add` — `temporal-reasoning`
- `gpt4_468eb064`, `gpt4_68e94288` — multi-hop temporal arithmetic

All four sit in the two types that need reasoning *across* sessions rather than
retrieval *within* one, and all four are recovered by k=30 (recall_any@30 =
1.000). They are a ranking-depth limit, not a retrieval failure: the right
session is in the candidate set, just not in the top ten.

---

## Reproducibility

```bash
# 1. Build the corpus and KG (BGE-small-en-v1.5, heading chunks, no SIMILAR_TO).
#    Three phases: parse -> SQLite, embed -> JSONL cache, index from cache.
#    Add --keep-cache to resume from the cache without re-embedding.
poetry run python3 benchmarks/longmemeval/longmemeval_memkg.py prepare \
  benchmarks/longmemeval/data/longmemeval_s_cleaned.json \
  --wipe --chunk-strategy heading

# 2. Run evaluation (haystack-filter and k=50 are defaults)
poetry run python3 benchmarks/longmemeval/longmemeval_memkg.py run \
  benchmarks/longmemeval/data/longmemeval_s_cleaned.json \
  --out benchmarks/longmemeval/results_20260826_bge_haystack.jsonl

# Expected: R@1=90.4%  R@5=98.2%  R@10=99.2%
#           recall_all@10=98.8%  NDCG@10=0.954  misses@10=4/500
```

There is one configuration, not two. The sibling boost is applied
unconditionally to multi-session questions and cannot be switched off.
