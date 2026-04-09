# MemoryKG × LongMemEval — Benchmark Report

**Run label:** `heading+minilm`
**Results file:** `results_heading_minilm.jsonl`
**Questions evaluated:** 500
**Generated:** 2026-04-08 23:49:51
**Machine:** Apple M5 Max MacBook Pro, 64 GB RAM, 2 TB SSD
**Repository:** memory_kg @ `99548e2` (main)
**Commit:** 2026-04-08 19:59:32 -0400 — refactoring and new chunking strategy push
**Python:** 3.12.13  |  **Host:** Turing

---

## Session-Level Retrieval Metrics

| k | Recall@k | NDCG@k |
|--:|--:|--:|
|  1 | 0.708 | 0.708 |
|  3 | 0.736 | 0.723 |
|  5 | 0.758 | 0.730 |
| 10 | 0.818 | 0.742 |
| 30 | 0.928 | 0.741 |
| 50 | 0.998 | 0.733 |

## Per-Type Breakdown

| Question Type | n | Recall@5 | Recall@10 | NDCG@10 |
|---|--:|--:|--:|--:|
| knowledge-update | 78 | 0.897 | 0.949 | 0.880 |
| multi-session | 133 | 0.744 | 0.827 | 0.709 |
| single-session-assistant | 56 | 1.000 | 1.000 | 1.000 |
| single-session-preference | 30 | 0.333 | 0.467 | 0.375 |
| single-session-user | 70 | 0.614 | 0.686 | 0.622 |
| temporal-reasoning | 133 | 0.759 | 0.805 | 0.731 |

## Key Findings

- **Top-1 recall:** 70.8% — immediate precision of the semantic seed
- **Top-5 recall:** 75.8%
- **Top-10 recall:** 81.8%
- **Top-50 recall (coverage ceiling):** 99.8%

**Hardest question types (by Recall@10):**
- `single-session-preference`: 46.7%
- `single-session-user`: 68.6%

**Easiest question types (by Recall@10):**
- `knowledge-update`: 94.9%
- `single-session-assistant`: 100.0%

## Misses @ k=10

**91 / 500** questions had zero sessions retrieved in top-10.

<details>
<summary>Show all 91 missed question IDs</summary>

```
e47becba
1e043500
c5e8278d
6f9b354f
5d3d2817
7527f7e2
3b6f954b
726462e0
ad7109d1
d52b4f67
25e5aa4f
577d4d32
e01b8e2f
bc8a6e93
b320f3f8
c19f7a0b
faba32e5
36580ce8
a82c026e
15745da0_abs
bc8a6e93_abs
f4f1d8a4_abs
dd2973ad
6cb6f249
80ec1f4f
d23cf73b
gpt4_2ba83207
60bf93ed
129d1232
a9f6b44c
10d9b85a
2b8f3739
60bf93ed_abs
06878be2
0edc2aef
32260d93
195a1a1b
06f04340
09d032c9
38146c39
d24813b1
57f827a0
95228167
d6233ab6
b6025781
1d4e3b97
07b6f563
1c0ddc50
0a34ad58
2311e44b
9aaed6a3
d905b33f
5025383b
92a0aa75
6c49646a
ef9cf60a
c18a7dc8
8e91e7d9
e56a43b9
efc3f7c2
a96c20ee_abs
gpt4_f49edff3
gpt4_7f6b06db
4dfccbf7
gpt4_e061b84f
8077ef71
gpt4_21adecb5
5e1b23de
gpt4_85da3956
gpt4_b0863698
gpt4_e061b84g
71017277
gpt4_e414231f
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
gpt4_1a1dc16d
2698e78f
6a27ffc2
18bc8abd
6aeb4375_abs
```
</details>
