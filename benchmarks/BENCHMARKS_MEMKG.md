# MemoryKG × LongMemEval — Benchmark Report

**Run label:** `results_bge_haystack`
**Results file:** `results_bge_haystack.jsonl`
**Questions evaluated:** 500
**Generated:** 2026-04-09
**Machine:** Apple M5 Max MacBook Pro, 64 GB RAM, 2 TB SSD
**Repository:** memory_kg @ `a990e7b` (develop)
**Commit:** 2026-04-09 — perf(benchmark): add haystack-filter and seed-kinds seeding strategies
**Python:** 3.12.13  |  **Host:** Turing

---

## Session-Level Retrieval Metrics

| k | Recall@k | NDCG@k |
|--:|--:|--:|
|  1 | 0.894 | 0.894 |
|  3 | 0.958 | 0.929 |
|  5 | 0.976 | 0.933 |
| 10 | 0.992 | 0.936 |
| 30 | 1.000 | 0.936 |
| 50 | 1.000 | 0.936 |

## Per-Type Breakdown (R@5)

| Question Type | n | Recall@5 | Recall@10 | NDCG@10 |
|---|--:|--:|--:|--:|
| knowledge-update | 78 | 1.000 | 1.000 | — |
| multi-session | 133 | 0.977 | 1.000 | — |
| single-session-assistant | 56 | 1.000 | 1.000 | — |
| single-session-preference | 30 | 1.000 | 1.000 | — |
| single-session-user | 70 | 0.971 | 1.000 | — |
| temporal-reasoning | 133 | 0.947 | 0.970 | — |

## Key Findings

- **Top-1 recall:** 89.4% — immediate precision of the semantic seed
- **Top-5 recall:** 97.6%
- **Top-10 recall:** 99.2%
- **Top-50 recall (coverage ceiling):** 100.0%

**Hardest question type (by Recall@10):**
- `temporal-reasoning`: 97.0% — 4 misses are all `gpt4_*` multi-hop temporal arithmetic

**Perfect recall at k=10:**
- `knowledge-update`, `multi-session`, `single-session-assistant`, `single-session-preference`, `single-session-user`

## Misses @ k=10

**4 / 500** questions had zero sessions retrieved in top-10.

All 4 are `gpt4_*` temporal-reasoning variants requiring multi-hop date arithmetic beyond pure vector + graph retrieval.

## Configuration

- **Embedding model:** `BAAI/bge-small-en-v1.5` (384d, retrieval-optimized)
- **Chunk strategy:** heading-based
- **Seeds:** k=50, hop=1
- **Haystack filter:** enabled (restricts LanceDB search to per-question 50-session candidate pool)
- **Question normalization:** bypassed for `single-session-preference` type
- **Inference:** none — no LLM, no API key required
