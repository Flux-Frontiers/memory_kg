# MemoryKG × LongMemEval — Multi-Run Comparison

**Generated:** 2026-04-09 11:45:52  
**Repository:** memory_kg @ `2142eaf` (develop)  
**Machine:** Apple M5 Max MacBook Pro, 64 GB RAM, 2 TB SSD  

---

## Recall@k Comparison

| k | results_bge_hop0 | results_heading_minilm | results_k150_fixes | results_k150_kw_temporal | results_k150_pref | results_bge_hop1 |
|--:|--:|--:|--:|--:|--:|--:|
|  1 | 0.796 | 0.708 | 0.808 | 0.274 | 0.808 | 0.824 |
|  3 | 0.824 | 0.736 | 0.834 | 0.352 | 0.832 | 0.858 |
|  5 | 0.834 | 0.758 | 0.846 | 0.406 | 0.846 | 0.866 |
| 10 | 0.870 | 0.818 | 0.878 | 0.530 | 0.876 | 0.894 |
| 30 | 0.946 | 0.928 | 0.954 | 0.820 | 0.954 | 0.954 |
| 50 | 0.998 | 0.998 | 0.998 | 0.994 | 0.998 | 1.000 |

## NDCG@k Comparison

| k | results_bge_hop0 | results_heading_minilm | results_k150_fixes | results_k150_kw_temporal | results_k150_pref | results_bge_hop1 |
|--:|--:|--:|--:|--:|--:|--:|
|  1 | 0.796 | 0.708 | 0.808 | 0.274 | 0.808 | 0.824 |
|  3 | 0.813 | 0.723 | 0.823 | 0.322 | 0.822 | 0.844 |
|  5 | 0.816 | 0.730 | 0.825 | 0.343 | 0.826 | 0.846 |
| 10 | 0.823 | 0.742 | 0.830 | 0.380 | 0.829 | 0.852 |
| 30 | 0.815 | 0.741 | 0.824 | 0.438 | 0.822 | 0.841 |
| 50 | 0.805 | 0.733 | 0.818 | 0.455 | 0.816 | 0.832 |

---

## Run: `results_bge_hop0` (n=500)

## Session-Level Retrieval Metrics

| k | Recall@k | NDCG@k |
|--:|--:|--:|
|  1 | 0.796 | 0.796 |
|  3 | 0.824 | 0.813 |
|  5 | 0.834 | 0.816 |
| 10 | 0.870 | 0.823 |
| 30 | 0.946 | 0.815 |
| 50 | 0.998 | 0.805 |

## Per-Type Breakdown

| Question Type | n | Recall@5 | Recall@10 | NDCG@10 |
|---|--:|--:|--:|--:|
| knowledge-update | 78 | 0.949 | 0.962 | 0.937 |
| multi-session | 133 | 0.857 | 0.910 | 0.845 |
| single-session-assistant | 56 | 1.000 | 1.000 | 1.000 |
| single-session-preference | 30 | 0.467 | 0.567 | 0.497 |
| single-session-user | 70 | 0.729 | 0.757 | 0.710 |
| temporal-reasoning | 133 | 0.812 | 0.850 | 0.793 |

## Key Findings

- **Top-1 recall:** 79.6% — immediate precision of the semantic seed
- **Top-5 recall:** 83.4%
- **Top-10 recall:** 87.0%
- **Top-50 recall (coverage ceiling):** 99.8%

**Hardest question types (by Recall@10):**
- `single-session-preference`: 56.7%
- `single-session-user`: 75.7%

**Easiest question types (by Recall@10):**
- `knowledge-update`: 96.2%
- `single-session-assistant`: 100.0%

## Misses @ k=10

**65 / 500** questions had zero sessions retrieved in top-10.

<details>
<summary>Show all 65 missed question IDs</summary>

```
1e043500
6ade9755
6f9b354f
5d3d2817
7527f7e2
3b6f954b
726462e0
75499fd8
d52b4f67
577d4d32
bc8a6e93
b320f3f8
19b5f2b3
a82c026e
0862e8bf_abs
bc8a6e93_abs
f4f1d8a4_abs
dd2973ad
d23cf73b
60bf93ed
10d9b85a
2b8f3739
60bf93ed_abs
06878be2
0edc2aef
32260d93
06f04340
09d032c9
38146c39
d24813b1
57f827a0
75f70248
d6233ab6
b6025781
1c0ddc50
0a34ad58
ef66a6e5
5025383b
92a0aa75
c18a7dc8
8e91e7d9
a96c20ee_abs
gpt4_7f6b06db
gpt4_6dc9b45b
gpt4_468eb063
gpt4_e061b84f
gpt4_21adecb5
5e1b23de
gpt4_e061b84g
71017277
gpt4_4929293b
gpt4_468eb064
gpt4_fa19884d
4dfccbf8
6e984302
gpt4_8279ba03
gpt4_b5700ca0
gpt4_68e94288
08f4fc43
a3045048
gpt4_d31cdae3
gpt4_1a1dc16d
45dc21b6
5831f84d
6aeb4375_abs
```
</details>

---

## Run: `results_heading_minilm` (n=500)

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

---

## Run: `results_k150_fixes` (n=500)

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

---

## Run: `results_k150_kw_temporal` (n=500)

## Session-Level Retrieval Metrics

| k | Recall@k | NDCG@k |
|--:|--:|--:|
|  1 | 0.274 | 0.274 |
|  3 | 0.352 | 0.322 |
|  5 | 0.406 | 0.343 |
| 10 | 0.530 | 0.380 |
| 30 | 0.820 | 0.438 |
| 50 | 0.994 | 0.455 |

## Per-Type Breakdown

| Question Type | n | Recall@5 | Recall@10 | NDCG@10 |
|---|--:|--:|--:|--:|
| knowledge-update | 78 | 0.577 | 0.718 | 0.502 |
| multi-session | 133 | 0.391 | 0.556 | 0.360 |
| single-session-assistant | 56 | 0.482 | 0.518 | 0.437 |
| single-session-preference | 30 | 0.067 | 0.233 | 0.119 |
| single-session-user | 70 | 0.243 | 0.343 | 0.251 |
| temporal-reasoning | 133 | 0.451 | 0.564 | 0.431 |

## Key Findings

- **Top-1 recall:** 27.4% — immediate precision of the semantic seed
- **Top-5 recall:** 40.6%
- **Top-10 recall:** 53.0%
- **Top-50 recall (coverage ceiling):** 99.4%

**Hardest question types (by Recall@10):**
- `single-session-preference`: 23.3%
- `single-session-user`: 34.3%

**Easiest question types (by Recall@10):**
- `temporal-reasoning`: 56.4%
- `knowledge-update`: 71.8%

## Misses @ k=10

**235 / 500** questions had zero sessions retrieved in top-10.

<details>
<summary>Show all 235 missed question IDs</summary>

```
e47becba
51a45a95
58bf7951
c5e8278d
6ade9755
6f9b354f
f8c5f88b
5d3d2817
7527f7e2
3b6f954b
726462e0
66f24dbb
ad7109d1
af8d2e46
8ebdbe50
6b168ec8
853b0a1d
37d43f65
b86304ba
d52b4f67
25e5aa4f
60d45044
3f1e9474
86b68151
577d4d32
ec81a493
e01b8e2f
bc8a6e93
001be529
19b5f2b3
4fd1909e
545bd2b5
8e9d538c
311778f1
c19f7a0b
4100d0a0
29f2956b
faba32e5
f4f1d8a4
c14c00dd
36580ce8
a82c026e
0862e8bf_abs
15745da0_abs
bc8a6e93_abs
f4f1d8a4_abs
0a995998
b5ef892d
e831120c
dd2973ad
6cb6f249
36b9f61e
d23cf73b
gpt4_7fce9456
gpt4_5501fe77
gpt4_2ba83207
2318644b
60bf93ed
60472f9c
a9f6b44c
gpt4_731e37d7
10d9b85a
2b8f3739
c2ac3c61
60bf93ed_abs
06878be2
0edc2aef
35a27287
32260d93
195a1a1b
54026fce
06f04340
09d032c9
38146c39
d24813b1
57f827a0
95228167
75f70248
d6233ab6
1da05512
fca70973
b6025781
a89d7624
b0479f84
1d4e3b97
07b6f563
1c0ddc50
0a34ad58
2311e44b
cc06de0d
a11281a2
4f54b7c9
1f2b8d4f
d905b33f
7405e8b1
6456829e
a4996e51
3c1045c8
60036106
e25c3b8d
ef66a6e5
5025383b
3fdac837
91b15a6e
720133ac
8979f9ec
0100672e
92a0aa75
3fe836c9
1c549ce4
6c49646a
bb7c3b45
61f8c8f8
ef9cf60a
09ba9854
d6062bb9
157a136e
c18a7dc8
55241a1f
a08a253f
f0e564bc
8cf4d046
8e91e7d9
87f22b4a
e56a43b9
efc3f7c2
2311e44b_abs
a96c20ee_abs
gpt4_f49edff3
71017276
gpt4_fa19884c
af082822
gpt4_b5700ca9
9a707b81
gpt4_1d80365e
gpt4_7f6b06db
gpt4_8279ba02
gpt4_a1b77f9c
4dfccbf7
gpt4_61e13b3c
2ebe6c90
370a8ff4
gpt4_ec93e27f
8077ef71
bcbe585f
gpt4_21adecb5
5e1b23de
gpt4_7ddcf75f
gpt4_85da3956
gpt4_b0863698
gpt4_7ca326fa
71017277
gpt4_e414231f
gpt4_4929293b
gpt4_468eb064
gpt4_fa19884d
9a707b82
4dfccbf8
6e984302
gpt4_8279ba03
gpt4_b5700ca0
gpt4_68e94288
gpt4_2655b836
gpt4_2487a7cb
gpt4_76048e76
2c63a862
gpt4_385a5000
bbf86515
gpt4_70e84552
c8090214
gpt4_483dd43c
e4e14d04
dcfa8644
gpt4_b4a80587
cc6d1ec1
993da5e2
a3045048
gpt4_d31cdae3
gpt4_4cd9eba1
b29f3365
gpt4_2f56ae70
gpt4_78cf46a3
gpt4_1a1dc16d
gpt4_70e84552_abs
982b5123_abs
c8090214_abs
6aeb4375
4d6b87c8
2698e78f
b6019101
45dc21b6
618f13b2
72e3ee87
6a27ffc2
18bc8abd
e61a7584
8fb83627
22d2cb42
7e974930
50635ada
dfde3500
cf22b7bf
a2f3aa27
5c40ec5b
26bdc477
6aeb4375_abs
031748ae_abs
89941a94
c4f10528
e9327a54
fea54f57
cc539528
488d3006
58470ed2
8cf51dda
1d4da289
8464fc84
8752c811
d596882b
e3fc4d6e
3e321797
e982271f
352ab8bd
fca762bc
7a8d0b71
8b9d4367
41275add
561fabcd
b759caee
16c90bf4
eaca4986
e48988bc
1de5cff2
65240037
778164c6
```
</details>

---

## Run: `results_k150_pref` (n=500)

## Session-Level Retrieval Metrics

| k | Recall@k | NDCG@k |
|--:|--:|--:|
|  1 | 0.808 | 0.808 |
|  3 | 0.832 | 0.822 |
|  5 | 0.846 | 0.826 |
| 10 | 0.876 | 0.829 |
| 30 | 0.954 | 0.822 |
| 50 | 0.998 | 0.816 |

## Per-Type Breakdown

| Question Type | n | Recall@5 | Recall@10 | NDCG@10 |
|---|--:|--:|--:|--:|
| knowledge-update | 78 | 0.962 | 0.974 | 0.944 |
| multi-session | 133 | 0.880 | 0.910 | 0.847 |
| single-session-assistant | 56 | 1.000 | 1.000 | 1.000 |
| single-session-preference | 30 | 0.500 | 0.567 | 0.520 |
| single-session-user | 70 | 0.743 | 0.800 | 0.746 |
| temporal-reasoning | 133 | 0.812 | 0.842 | 0.784 |

## Key Findings

- **Top-1 recall:** 80.8% — immediate precision of the semantic seed
- **Top-5 recall:** 84.6%
- **Top-10 recall:** 87.6%
- **Top-50 recall (coverage ceiling):** 99.8%

**Hardest question types (by Recall@10):**
- `single-session-preference`: 56.7%
- `single-session-user`: 80.0%

**Easiest question types (by Recall@10):**
- `knowledge-update`: 97.4%
- `single-session-assistant`: 100.0%

## Misses @ k=10

**62 / 500** questions had zero sessions retrieved in top-10.

<details>
<summary>Show all 62 missed question IDs</summary>

```
e47becba
6f9b354f
5d3d2817
7527f7e2
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

---

## Run: `results_bge_hop1` (n=500)

## Session-Level Retrieval Metrics

| k | Recall@k | NDCG@k |
|--:|--:|--:|
|  1 | 0.824 | 0.824 |
|  3 | 0.858 | 0.844 |
|  5 | 0.866 | 0.846 |
| 10 | 0.894 | 0.852 |
| 30 | 0.954 | 0.841 |
| 50 | 1.000 | 0.832 |

## Per-Type Breakdown

| Question Type | n | Recall@5 | Recall@10 | NDCG@10 |
|---|--:|--:|--:|--:|
| knowledge-update | 78 | 0.974 | 0.987 | 0.966 |
| multi-session | 133 | 0.887 | 0.925 | 0.864 |
| single-session-assistant | 56 | 1.000 | 1.000 | 1.000 |
| single-session-preference | 30 | 0.467 | 0.567 | 0.485 |
| single-session-user | 70 | 0.800 | 0.814 | 0.780 |
| temporal-reasoning | 133 | 0.850 | 0.880 | 0.830 |

## Key Findings

- **Top-1 recall:** 82.4% — immediate precision of the semantic seed
- **Top-5 recall:** 86.6%
- **Top-10 recall:** 89.4%
- **Top-50 recall (coverage ceiling):** 100.0%

**Hardest question types (by Recall@10):**
- `single-session-preference`: 56.7%
- `single-session-user`: 81.4%

**Easiest question types (by Recall@10):**
- `knowledge-update`: 98.7%
- `single-session-assistant`: 100.0%

## Misses @ k=10

**53 / 500** questions had zero sessions retrieved in top-10.

<details>
<summary>Show all 53 missed question IDs</summary>

```
6f9b354f
5d3d2817
7527f7e2
3b6f954b
726462e0
d52b4f67
577d4d32
bc8a6e93
b320f3f8
a82c026e
0862e8bf_abs
bc8a6e93_abs
f4f1d8a4_abs
dd2973ad
d23cf73b
60bf93ed
2b8f3739
60bf93ed_abs
06878be2
0edc2aef
32260d93
06f04340
09d032c9
38146c39
d24813b1
57f827a0
75f70248
d6233ab6
b6025781
1c0ddc50
0a34ad58
ef66a6e5
5025383b
c18a7dc8
8e91e7d9
a96c20ee_abs
gpt4_e061b84f
gpt4_21adecb5
5e1b23de
gpt4_e061b84g
71017277
gpt4_4929293b
gpt4_468eb064
gpt4_fa19884d
4dfccbf8
6e984302
gpt4_8279ba03
gpt4_b5700ca0
gpt4_68e94288
a3045048
gpt4_d31cdae3
gpt4_1a1dc16d
6aeb4375_abs
```
</details>

