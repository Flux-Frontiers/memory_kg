# MemoryKG × ConvoMem Benchmark Results

**Date:** 2026-04-26
**Model:** BAAI/bge-small-en-v1.5
**Retrieval:** top-20 semantic seeds, hop=1 graph expansion (primary)
**System:** MemoryKG v0.4.1

---

## Summary

MemoryKG achieves **96.3% tier-1 retrieval recall** at k=20, exceeding MemPal's published
92.9% by +3.4 pp. Results across 1,897 items spanning tiers 1–4.

Key finding: **seed count beats model size**. k=10→k=20 gains +4.5 pp tier-1 at zero
latency cost; switching to bge-large (5× slower) gains only +0.6 pp.

Graph expansion contributes zero recall improvement (hop=0 == hop=1) — all recall from
semantic seeding alone.

---

## Results by Tier (k=20)

### Tier 1 — Single-message evidence (500 items)

| Category | Items | Recall | Perfect |
|---|--:|--:|--:|
| User Facts | 100 | 0.990 | 99/100 |
| Assistant Facts | 100 | 0.990 | 99/100 |
| Abstention | 100 | 0.950 | 94/100 |
| Implicit Connections | 100 | 0.923 | 91/100 |
| Preferences | 100 | 0.960 | 96/100 |
| **Total** | **500** | **0.963** | **479/500** |

### Tier 2 — Two-message evidence (597 items)

| Category | Items | Recall | Perfect |
|---|--:|--:|--:|
| User Facts | 100 | 0.965 | 93/100 |
| Assistant Facts | 100 | 0.945 | 89/100 |
| Abstention | 100 | 0.990 | 98/100 |
| Implicit Connections | 100 | 0.725 | 50/100 |
| Preferences | 97 | 0.711 | 52/97 |
| Changing Facts | 100 | 0.975 | 95/100 |
| **Total** | **597** | **0.886** | **477/597** |

### Tier 3 — Three-message evidence (500 items)

| Category | Items | Recall | Perfect |
|---|--:|--:|--:|
| User Facts | 100 | 0.877 | 72/100 |
| Assistant Facts | 100 | 0.923 | 84/100 |
| Abstention | 100 | 0.917 | 78/100 |
| Implicit Connections | 100 | 0.557 | 19/100 |
| Changing Facts | 100 | 0.913 | 80/100 |
| **Total** | **500** | **0.837** | **333/500** |

### Tier 4 — Four-message evidence (300 items)

| Category | Items | Recall | Perfect |
|---|--:|--:|--:|
| User Facts | 100 | 0.807 | 58/100 |
| Assistant Facts | 100 | 0.902 | 71/100 |
| Changing Facts | 100 | 0.818 | 52/100 |
| **Total** | **300** | **0.843** | **181/300** |

### Overall

| Tier | Items | Recall |
|---|--:|--:|
| 1 | 500 | **0.963** |
| 2 | 597 | **0.886** |
| 3 | 500 | **0.837** |
| 4 | 300 | **0.843** |
| **Total** | **1,897** | **0.887** |

---

## Seed-Count Ablation (tier 1)

| Category | k=10 | k=20 | Δ |
|---|--:|--:|--:|
| User Facts | 0.990 | 0.990 | 0.000 |
| Assistant Facts | 0.990 | 0.990 | 0.000 |
| Abstention | 0.945 | 0.950 | +0.005 |
| Implicit Connections | 0.823 | 0.923 | +0.100 |
| Preferences | 0.840 | 0.960 | +0.120 |
| **Overall** | **0.918** | **0.963** | **+0.045** |

---

## Comparison with MemPal (tier 1, k=20)

| Category | MemPal | MemoryKG | Δ |
|---|--:|--:|--:|
| User Facts | 98.0% | **99.0%** | +1.0 pp |
| Assistant Facts | **100%** | 99.0% | −1.0 pp |
| Abstention | 91.0% | **95.0%** | +4.0 pp |
| Implicit Connections | 89.3% | **92.3%** | +3.0 pp |
| Preferences | 86.0% | **96.0%** | +10.0 pp |
| **Overall** | **92.9%** | **96.3%** | **+3.4 pp** |

---

## Methodology

For each evidence item:

1. All conversations are written to a temp directory as Markdown files (one per conversation,
   each message as a `##`-headed section).
2. A fresh MemoryKG is built over that corpus (heading chunks, no enrichment).
3. The question is issued as a semantic query (k=20 seeds, hop=1 expansion).
4. Recall = fraction of evidence messages whose text appears verbatim in any returned node.

A single `SentenceTransformerEmbedder` (BAAI/bge-small-en-v1.5) is reused across all
items: ~0.07s/item on Apple Silicon.

Graph expansion (hop=0 vs hop=1) produces identical recall — all recall attributable to
semantic seeding alone. Per-item KGs are small (13–88 nodes); k=20 seeds already cover
most of the corpus.

---

## Reproducibility

```bash
python benchmarks/convomem/convomem_bench.py --tier 1 --k 20
python benchmarks/convomem/convomem_bench.py --tier 2 --k 20
python benchmarks/convomem/convomem_bench.py --tier 3 --k 20
python benchmarks/convomem/convomem_bench.py --tier 4 --k 20
```

---

*Results verified April 2026. Scoring bug (empty-node false match) fixed 2026-04-26.*
*Previous claimed result of 100% recall across 17,463 items was incorrect due to this bug.*
