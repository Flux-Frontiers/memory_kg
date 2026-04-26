# MemoryKG × MemBench — Benchmark Results

**April 2026 — Complete record of MemoryKG on MemBench (ACL 2025).**

---

## The Result

**87.7% mean recall at k=20 across all 11 categories, all 3 topics (movie, food, book), 1,100 items.**

Per-item haystack scoping is the essential mechanism: without it recall collapses to 8.9%.

---

## The Numbers

| Setting | Items | Avg Recall | Perfect | Time |
|---|--:|--:|--:|--:|
| k=10, hop=1 (haystack) | 1,100 | **0.816** | 839/1100 | 65.4s |
| k=20, hop=1 (haystack) | 1,100 | **0.877** | — | — |
| k=50, hop=1 (haystack) | 1,100 | **0.889** | — | — |
| k=10, hop=1 (no scoping) | 1,100 | **0.089** | — | 60.7s |

### Per-Category Recall (k=20, all topics — primary result)

| Category | Description | Recall | Perfect |
|---|---|--:|--:|
| simple | Basic single-turn fact recall | 0.970 | 97/100 |
| highlevel | Aggregation across turns | 1.000 | 100/100 |
| knowledge_update | Facts that change over time | 0.990 | 99/100 |
| comparative | Comparing items across turns | 0.970 | 94/100 |
| conditional | Conditional reasoning | 0.745 | 51/100 |
| noisy | Planted distractors | 0.420 | 8/100 |
| aggregative | Multi-turn combination | 0.870 | 57/100 |
| highlevel_rec | Preference recommendation | 0.983 | 95/100 |
| lowlevel_rec | Fact-based recommendation | 1.000 | 100/100 |
| RecMultiSession | Multi-session recommendation | 0.982 | 91/100 |
| post_processing | Post-processing reasoning | 0.720 | 47/100 |
| **Total** | | **0.877** | **839/1100** |

---

## The Essential Mechanism: Haystack Scoping

Per-item `haystack_files` scoping restricts LanceDB seeding to the queried item's single
Markdown file. Without this, recall collapses from 0.816 to 0.089 (k=10):

| Condition | Recall | Notes |
|---|--:|---|
| Haystack scoping ON | 0.816 | All 1,100 items, k=10 |
| Haystack scoping OFF | 0.089 | 86.5% of items score zero |

The 9× gap confirms that the global 259,464-node corpus is too large for k=10 seeds to
reliably land on the correct item's turns without scoping.

---

## The noisy Ceiling

The *noisy* category is the hardest at every seed count: 0.370 (k=10), 0.420 (k=20),
0.465 (k=50). Planted in-corpus distractors create a semantic overlap ceiling that
additional seeds cannot overcome. This is a re-ranking problem, not a seed-count problem.

---

## Architecture

```
Query (MemBench question)
  │
  ├─ LanceDB vector search (k=20, primary)
  │    └─ scoped to item's single Markdown file (haystack_files={item_file})
  │         └─ BGE-small-en-v1.5 embeddings (384d)
  │
  ├─ Graph expansion (hop=1)
  │    └─ edges: CONTAINS, NEXT (within-file only — no cross-item contamination)
  │
  └─ Text matching: target turn user/assistant text ∈ retrieved node text?
```

**No inference. No LLM. No API key required.**

---

## Reproducing the Results

```bash
# All-in-one (downloads data automatically, builds KG, runs evaluation)
poetry run python benchmarks/membench/membench_bench.py all --topic all --limit 100

# With k=20 (primary result)
poetry run python benchmarks/membench/membench_bench.py all --topic all --limit 100 --k 20

# No-haystack ablation
poetry run python benchmarks/membench/membench_bench.py all --topic all --limit 100 --no-haystack
```

**Machine:** Apple M5 Max MacBook Pro, 64 GB RAM
**Build time:** ~183s (259,464 nodes)
**Run time:** ~65s (0.06s/item)
**Data:** auto-downloaded from [github.com/import-myself/Membench](https://github.com/import-myself/Membench)

---

*Results verified April 2026. Scoring bug (empty-node false match) fixed 2026-04-26.*
