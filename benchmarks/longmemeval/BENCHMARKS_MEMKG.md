# MemoryKG × LongMemEval — Benchmark Report

**Run label:** `results_no_normalize`
**Results file:** `results_no_normalize.jsonl`
**Questions evaluated:** 500
**Generated:** 2026-04-25 18:38:40
**Run time:** 181.6s (0.36s per question)
**Machine:** Apple M5 Max MacBook Pro, 64 GB RAM, 2 TB SSD
**Repository:** memory_kg @ `7fe37b3` (main)
**Commit:** 2026-04-25 16:49:32 -0400 — chore(public-prep): sanitize machine-specific MCP configs before public release
**Python:** 3.12.13  |  **Host:** Turing

---

## Session-Level Retrieval Metrics

| k | Recall@k | NDCG@k |
|--:|--:|--:|
|  1 | 0.904 | 0.904 |
|  3 | 0.974 | 0.942 |
|  5 | 0.984 | 0.942 |
| 10 | 0.994 | 0.943 |
| 30 | 1.000 | 0.942 |
| 50 | 1.000 | 0.942 |

## Per-Type Breakdown

| Question Type | n | Recall@5 | Recall@10 | NDCG@10 |
|---|--:|--:|--:|--:|
| knowledge-update | 78 | 1.000 | 1.000 | 0.984 |
| multi-session | 133 | 0.992 | 0.992 | 0.949 |
| single-session-assistant | 56 | 1.000 | 1.000 | 1.000 |
| single-session-preference | 30 | 1.000 | 1.000 | 0.913 |
| single-session-user | 70 | 0.986 | 1.000 | 0.932 |
| temporal-reasoning | 133 | 0.955 | 0.985 | 0.901 |

## Key Findings

- **Top-1 recall:** 90.4% — immediate precision of the semantic seed
- **Top-5 recall:** 98.4%
- **Top-10 recall:** 99.4%
- **Top-50 recall (coverage ceiling):** 100.0%

**Hardest question types (by Recall@10):**
- `temporal-reasoning`: 98.5%
- `multi-session`: 99.2%

**Easiest question types (by Recall@10):**
- `single-session-preference`: 100.0%
- `single-session-user`: 100.0%

## Misses @ k=10

**3 / 500** questions had zero sessions retrieved in top-10.

<details>
<summary>Show all 3 missed question IDs</summary>

```
10d9b85a
gpt4_468eb064
eac54add
```
</details>
