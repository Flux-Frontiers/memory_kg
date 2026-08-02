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

## sqlite-vec Parity (August 2026)

The 0.7.0 port from LanceDB to sqlite-vec reproduces this benchmark. The KG was rebuilt
from scratch on the new backend and matched the LanceDB-era build exactly — 259,464 nodes,
258,364 edges, 259,464 indexed rows (327s).

| Setting | LanceDB baseline | sqlite-vec | Per-item rows differing |
|---|--:|--:|--:|
| k=10, hop=1 (haystack) | 0.8161 | 0.8161 | **0 of 1,100** |
| k=20, hop=1 (haystack) | 0.8772 | 0.8768 | 4 of 1,100 |

All 11 per-category figures reproduce; the headline 87.7% at k=20 stands.

The four differing items at k=20 are **not attributable to the backend**: the runner does
not reproduce itself. Two consecutive k=20 runs against the *same* index and the *same*
code also differ on 4 of 1,100 items — a different four. See "Retrieval is not reproducible
across processes" below.

Results: `results/membench_memkg_all_all_k{10,20}_hop1_sqlitevec.{jsonl,md}`.
Elapsed times in those reports are not comparable to the baseline's — several runs
overlapped on one machine.

---

## Retrieval Is Not Reproducible Across Processes

Discovered while diffing the parity runs, and **pre-existing** — it predates the sqlite-vec
port and is unrelated to it.

Two runs of the same benchmark, same index, same code, differ on a handful of items:

| Comparison | Rows differing |
|---|--:|
| MemBench k=20, sqlite-vec run 1 vs run 2 | 4 of 1,100 |
| MemBench k=20, LanceDB baseline vs sqlite-vec | 4 of 1,100 |
| MemBench k=20 with `PYTHONHASHSEED=0`, run A vs run B | **0 of 1,100** |

The query vector and the seed distances are bit-identical across processes — only the
expanded and ranked node set moves. `GraphStore.expand()` iterates `frontier`, a `set[str]`,
and the first seed to reach a node claims it as `via_seed`. Python randomizes string hashing
per process, so when two seeds reach the same node, which one wins varies between runs.
`via_seed` supplies `base_dist`, the first element of `_rank_key` in `kg.py`, so the tail
order changes and a different node falls off the `max_nodes` cut.

That predicts exactly what the data shows: every differing item sits *at* the cap
(`retrieved_nodes == 50`) and has more than one evidence turn. Items returning fewer than
`max_nodes` never differ. At k=20, 325 of 1,100 items hit the cap (252 of them with multiple
evidence turns) and 4 flipped; at k=10 only 97 items hit the cap and none flipped.

Pinning `PYTHONHASHSEED` makes whole runs bit-reproducible. Until the traversal itself is
made order-independent, treat differences of this magnitude between any two runs as noise,
not signal.

---

## The Essential Mechanism: Haystack Scoping

Per-item `haystack_files` scoping restricts vector seeding to the queried item's single
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
  ├─ sqlite-vec vector search (k=20, primary)
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
*Reproduced on sqlite-vec 2026-08-02 (memory_kg @ `2c8cc56`, Apple Silicon, MPS).*
