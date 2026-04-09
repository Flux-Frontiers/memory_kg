# MemoryKG × LongMemEval — Benchmark Report

**Run label:** `k150_fixes`
**Results file:** `results_k150_fixes.jsonl`
**Questions evaluated:** 500
**Generated:** 2026-04-09 09:42:25
**Machine:** Apple M5 Max MacBook Pro, 64 GB RAM, 2 TB SSD
**Repository:** memory_kg @ `2142eaf` (develop)
**Commit:** 2026-04-08 23:54:16 -0400 — add: new chunking, analysis report
**Python:** 3.12.13  |  **Host:** Turing

---

## Session-Level Retrieval Metrics

| k | Recall@k | NDCG@k |
|--:|--:|--:|
|  1 | 0.808 | 0.808 |
|  3 | 0.834 | 0.823 |
|  5 | 0.846 | 0.825 |
| 10 | 0.878 | 0.830 |
| 30 | 0.954 | 0.824 |
| 50 | 0.998 | 0.818 |

## Per-Type Breakdown

| Question Type | n | Recall@5 | Recall@10 | NDCG@10 |
|---|--:|--:|--:|--:|
| knowledge-update | 78 | 0.949 | 0.974 | 0.938 |
| multi-session | 133 | 0.880 | 0.910 | 0.849 |
| single-session-assistant | 56 | 1.000 | 1.000 | 1.000 |
| single-session-preference | 30 | 0.500 | 0.567 | 0.520 |
| single-session-user | 70 | 0.757 | 0.814 | 0.760 |
| temporal-reasoning | 133 | 0.812 | 0.842 | 0.782 |

## Key Findings

- **Top-1 recall:** 80.8% — immediate precision of the semantic seed
- **Top-5 recall:** 84.6%
- **Top-10 recall:** 87.8%
- **Top-50 recall (coverage ceiling):** 99.8%

**Hardest question types (by Recall@10):**
- `single-session-preference`: 56.7%
- `single-session-user`: 81.4%

**Easiest question types (by Recall@10):**
- `knowledge-update`: 97.4%
- `single-session-assistant`: 100.0%

## Misses @ k=10

**61 / 500** questions had zero sessions retrieved in top-10.

<details>
<summary>Show all 61 missed question IDs</summary>

```
e47becba
6f9b354f
5d3d2817
726462e0
ad7109d1
d52b4f67
bc8a6e93
c19f7a0b
faba32e5
36580ce8
a82c026e
bc8a6e93_abs
f4f1d8a4_abs
dd2973ad
d23cf73b
gpt4_2ba83207
60bf93ed
10d9b85a
60bf93ed_abs
0edc2aef
32260d93
195a1a1b
06f04340
09d032c9
38146c39
d24813b1
57f827a0
d6233ab6
b6025781
1d4e3b97
1c0ddc50
0a34ad58
92a0aa75
c18a7dc8
8e91e7d9
e56a43b9
efc3f7c2
a96c20ee_abs
gpt4_f49edff3
gpt4_7f6b06db
gpt4_e061b84f
8077ef71
gpt4_21adecb5
5e1b23de
gpt4_e061b84g
71017277
gpt4_4929293b
gpt4_468eb064
gpt4_fa19884d
9a707b82
6e984302
gpt4_8279ba03
gpt4_b5700ca0
gpt4_68e94288
gpt4_2487a7cb
993da5e2
a3045048
gpt4_d31cdae3
gpt4_2f56ae70
2698e78f
6aeb4375_abs
```
</details>
