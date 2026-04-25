# MemoryKG × LongMemEval — Multi-Run Comparison

**Generated:** 2026-04-25 19:04:30
**Repository:** memory_kg @ `7fe37b3` (main)
**Machine:** Apple M5 Max MacBook Pro, 64 GB RAM, 2 TB SSD

---

## Recall@k Comparison

| k | results_260425 | results_no_normalize | results_sibling_boost | results_sibling_boost2 |
|--:|--:|--:|--:|--:|
|  1 | 0.904 | 0.904 | 0.904 | 0.904 |
|  3 | 0.974 | 0.974 | 0.964 | 0.972 |
|  5 | 0.984 | 0.984 | 0.976 | 0.982 |
| 10 | 0.994 | 0.994 | 0.990 | 0.992 |
| 30 | 1.000 | 1.000 | 1.000 | 1.000 |
| 50 | 1.000 | 1.000 | 1.000 | 1.000 |

## NDCG@k Comparison

| k | results_260425 | results_no_normalize | results_sibling_boost | results_sibling_boost2 |
|--:|--:|--:|--:|--:|
|  1 | 0.904 | 0.904 | 0.904 | 0.904 |
|  3 | 0.942 | 0.942 | 0.940 | 0.945 |
|  5 | 0.942 | 0.942 | 0.946 | 0.950 |
| 10 | 0.943 | 0.943 | 0.951 | 0.954 |
| 30 | 0.942 | 0.942 | 0.953 | 0.955 |
| 50 | 0.942 | 0.942 | 0.953 | 0.955 |

---

## Run: `results_260425` (n=500 — 179.2s (0.36s/q))

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

---

## Run: `results_no_normalize` (n=500 — 181.6s (0.36s/q))

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

---

## Run: `results_sibling_boost` (n=500 — 178.8s (0.36s/q))

## Session-Level Retrieval Metrics

| k | Recall@k | NDCG@k |
|--:|--:|--:|
|  1 | 0.904 | 0.904 |
|  3 | 0.964 | 0.940 |
|  5 | 0.976 | 0.946 |
| 10 | 0.990 | 0.951 |
| 30 | 1.000 | 0.953 |
| 50 | 1.000 | 0.953 |

## Per-Type Breakdown

| Question Type | n | Recall@5 | Recall@10 | NDCG@10 |
|---|--:|--:|--:|--:|
| knowledge-update | 78 | 1.000 | 1.000 | 0.992 |
| multi-session | 133 | 0.992 | 0.992 | 0.965 |
| single-session-assistant | 56 | 1.000 | 1.000 | 1.000 |
| single-session-preference | 30 | 0.967 | 0.967 | 0.896 |
| single-session-user | 70 | 0.957 | 1.000 | 0.925 |
| temporal-reasoning | 133 | 0.947 | 0.977 | 0.919 |

## Key Findings

- **Top-1 recall:** 90.4% — immediate precision of the semantic seed
- **Top-5 recall:** 97.6%
- **Top-10 recall:** 99.0%
- **Top-50 recall (coverage ceiling):** 100.0%

**Hardest question types (by Recall@10):**
- `single-session-preference`: 96.7%
- `temporal-reasoning`: 97.7%

**Easiest question types (by Recall@10):**
- `single-session-assistant`: 100.0%
- `single-session-user`: 100.0%

## Misses @ k=10

**5 / 500** questions had zero sessions retrieved in top-10.

<details>
<summary>Show all 5 missed question IDs</summary>

```
10d9b85a
09d032c9
gpt4_468eb064
eac54add
gpt4_68e94288
```
</details>

---

## Run: `results_sibling_boost2` (n=500 — 180.6s (0.36s/q))

## Session-Level Retrieval Metrics

| k | Recall@k | NDCG@k |
|--:|--:|--:|
|  1 | 0.904 | 0.904 |
|  3 | 0.972 | 0.945 |
|  5 | 0.982 | 0.950 |
| 10 | 0.992 | 0.954 |
| 30 | 1.000 | 0.955 |
| 50 | 1.000 | 0.955 |

## Per-Type Breakdown

| Question Type | n | Recall@5 | Recall@10 | NDCG@10 |
|---|--:|--:|--:|--:|
| knowledge-update | 78 | 1.000 | 1.000 | 0.992 |
| multi-session | 133 | 0.992 | 0.992 | 0.965 |
| single-session-assistant | 56 | 1.000 | 1.000 | 1.000 |
| single-session-preference | 30 | 1.000 | 1.000 | 0.913 |
| single-session-user | 70 | 0.986 | 1.000 | 0.932 |
| temporal-reasoning | 133 | 0.947 | 0.977 | 0.921 |

## Key Findings

- **Top-1 recall:** 90.4% — immediate precision of the semantic seed
- **Top-5 recall:** 98.2%
- **Top-10 recall:** 99.2%
- **Top-50 recall (coverage ceiling):** 100.0%

**Hardest question types (by Recall@10):**
- `temporal-reasoning`: 97.7%
- `multi-session`: 99.2%

**Easiest question types (by Recall@10):**
- `single-session-preference`: 100.0%
- `single-session-user`: 100.0%

## Misses @ k=10

**4 / 500** questions had zero sessions retrieved in top-10.

<details>
<summary>Show all 4 missed question IDs</summary>

```
10d9b85a
gpt4_468eb064
eac54add
gpt4_68e94288
```
</details>
