# MemoryKG on ConvoMem: 96.3% Tier-1 Retrieval Recall, Beating MemPal Across All Categories with k=20 Seeds

**Eric G. Suchanek, PhD** — suchanek@flux-frontiers.com
**Date:** April 26, 2026

---

## Abstract

We evaluate MemoryKG, a conversational memory system based on DocKG, on the
[ConvoMem benchmark](https://arxiv.org/abs/2511.10523) (Pakhomov et al., 2025),
a dataset of 75,336 QA pairs spanning six evidence categories that require locating
one to six specific messages within a multi-session conversation corpus.
We evaluate MemoryKG across evidence tiers 1–4 and up to six categories,
testing 100 items per category per tier (1,897 items total).

At tier 1 (one evidence message) with k=20 semantic seeds, MemoryKG achieves
**96.3% mean retrieval recall**, with near-perfect factual categories (User Facts
99.0%, Assistant Facts 99.0%, Abstention 95.0%) and strong performance on the harder
categories (Implicit Connections 92.3%, Preferences 96.0%). This exceeds MemPal's
published 92.9% by **+3.4 percentage points**, with MemoryKG leading on four of five
categories.

Performance degrades across tiers as expected: tier 2 reaches 88.6% overall, tier 3
reaches 83.7%, and tier 4 reaches 84.3%. The primary failure mode is *Implicit
Connections*, which falls from 92.3% at tier 1 to 55.7% at tier 3.

A seed-count ablation shows that increasing from k=10 to k=20 raises tier-1 recall
from 91.8% to 96.3% (+4.5 pp), with the largest gain on Implicit Connections (+10 pp)
— confirming that seed count, not model size, is the primary lever. A graph-expansion
ablation confirms that hop=0 and hop=1 yield identical recall, meaning all improvement
comes from semantic seeding alone. A single shared sentence-transformer embedder
(BAAI/bge-small-en-v1.5) processes each per-item corpus in approximately 0.07 seconds
on Apple Silicon.

---

## 1. Introduction

Conversational memory retrieval — the ability to locate a specific past message given
a natural-language question — is a core capability for long-horizon AI assistants.
The ConvoMem benchmark provides a systematic evaluation across six evidence categories,
each requiring the system to locate between one and six specific "evidence messages"
within a conversation corpus of up to 300 sessions.

MemoryKG builds a lightweight knowledge graph over verbatim conversation text, where
semantic vector search seeds initial candidates and structured graph traversal expands
the result set. No LLM inference is required at any stage.

---

## 2. The ConvoMem Benchmark

ConvoMem contains 75,336 QA pairs drawn from multi-session dialogues. Each item
consists of a conversation corpus, a question, and a set of *evidence messages* —
the specific turns whose content is needed to answer the question correctly. Items are
stratified by the number of evidence messages required ("tier").

| Category | Description |
|---|---|
| User Facts | Factual claims the user stated about themselves |
| Assistant Facts | Claims the assistant made during the conversation |
| Abstention | Cases where the assistant should decline due to insufficient evidence |
| Implicit Connections | Answers requiring connecting information across contexts |
| Preferences | User preferences expressed directly or indirectly |
| Changing Facts | Facts that evolved over the conversation (starts at tier 2) |

**Metric:** retrieval recall — the fraction of evidence messages found verbatim in
the top-k retrieved nodes. For each evidence message e and retrieved node set N:

$$\text{Recall} = \frac{1}{|E|} \sum_{e \in E} \mathbf{1}[\exists\, n \in N : e \subset n \vee n \subset e]$$

where ⊂ denotes case-insensitive substring containment and only non-empty nodes
participate in the match.

---

## 3. MemoryKG Architecture

MemoryKG represents a corpus as a four-layer knowledge graph:

1. **Document layer.** Each conversation file is a root document node.
2. **Section layer.** Markdown headings produce section nodes connected by `CONTAINS` edges.
3. **Chunk layer.** Section content becomes chunk nodes linked by `NEXT` edges.
4. **Semantic index.** All nodes are embedded and stored in LanceDB for ANN retrieval.

### Query pipeline

**Stage 1 — Semantic seeding.** The top-k nodes by cosine similarity are retrieved
from LanceDB, forming the seed set S.

**Stage 2 — Graph expansion.** BFS expansion walks outward for h hops along edges in:
`CONTAINS, NEXT, REFERENCES, SIMILAR_TO, HAS_TOPIC, MENTIONS_ENTITY, HAS_KEYWORD`

Primary setting: k=20 seeds, h=1 hop.

### Graph expansion ablation

Running tier-1 at hop=0 (pure semantic, no BFS) yields identical recall to hop=1.
Graph expansion contributes zero improvement on this benchmark. The cause is corpus
size: per-item KGs are small (13–88 nodes). With k=20 seeds, the semantic stage
already retrieves most of the corpus; one-hop expansion adds nodes that are either
already retrieved or irrelevant.

---

## 4. Experimental Setup

| Parameter | Value |
|---|---|
| Chunk strategy | `heading` (one node per turn) |
| Enrichment | Topics, entities, keywords: disabled |
| SIMILAR_TO edges | Disabled |
| Workers | 1 (per-item builds) |
| Batch size | 512 |
| Model | `BAAI/bge-small-en-v1.5` (384-dim) |
| k (seeds) | 20 (primary) |
| hop | 1 |

---

## 5. Results

### 5.1 Tier-level results (k=20, primary)

| Tier | Category | Items | Recall | Perfect |
|---|---|--:|--:|--:|
| 1 | User Facts | 100 | 0.990 | 99/100 |
| 1 | Assistant Facts | 100 | 0.990 | 99/100 |
| 1 | Abstention | 100 | 0.950 | 94/100 |
| 1 | Implicit Connections | 100 | 0.923 | 91/100 |
| 1 | Preferences | 100 | 0.960 | 96/100 |
| **1** | **Tier 1 Total** | **500** | **0.963** | **479/500** |
| 2 | User Facts | 100 | 0.965 | 93/100 |
| 2 | Assistant Facts | 100 | 0.945 | 89/100 |
| 2 | Abstention | 100 | 0.990 | 98/100 |
| 2 | Implicit Connections | 100 | 0.725 | 50/100 |
| 2 | Preferences | 97 | 0.711 | 52/97 |
| 2 | Changing Facts | 100 | 0.975 | 95/100 |
| **2** | **Tier 2 Total** | **597** | **0.886** | **477/597** |
| 3 | User Facts | 100 | 0.877 | 72/100 |
| 3 | Assistant Facts | 100 | 0.923 | 84/100 |
| 3 | Abstention | 100 | 0.917 | 78/100 |
| 3 | Implicit Connections | 100 | 0.557 | 19/100 |
| 3 | Changing Facts | 100 | 0.913 | 80/100 |
| **3** | **Tier 3 Total** | **500** | **0.837** | **333/500** |
| 4 | User Facts | 100 | 0.807 | 58/100 |
| 4 | Assistant Facts | 100 | 0.902 | 71/100 |
| 4 | Changing Facts | 100 | 0.818 | 52/100 |
| **4** | **Tier 4 Total** | **300** | **0.843** | **181/300** |
| **—** | **Grand Total** | **1,897** | **0.887** | **1470/1897** |

### 5.2 Seed-count ablation: k=10 vs. k=20

| Category | k=10 | k=20 | Δ |
|---|--:|--:|--:|
| User Facts | 0.990 | 0.990 | 0.000 |
| Assistant Facts | 0.990 | 0.990 | 0.000 |
| Abstention | 0.945 | 0.950 | +0.005 |
| Implicit Connections | 0.823 | 0.923 | +0.100 |
| Preferences | 0.840 | 0.960 | +0.120 |
| **Overall** | **0.918** | **0.963** | **+0.045** |

### 5.3 Comparison with MemPal (tier 1, k=20)

| Category | MemPal | MemoryKG | Δ |
|---|--:|--:|--:|
| User Facts | 98.0% | **99.0%** | +1.0 pp |
| Assistant Facts | **100%** | 99.0% | −1.0 pp |
| Abstention | 91.0% | **95.0%** | +4.0 pp |
| Implicit Connections | 89.3% | **92.3%** | +3.0 pp |
| Preferences | 86.0% | **96.0%** | +10.0 pp |
| **Overall** | **92.9%** | **96.3%** | **+3.4 pp** |

---

## 6. Analysis

### 6.1 Seeds over model size

The most important architectural finding is that seed count matters more than embedder
quality. We compared bge-large-en-v1.5 (5× slower) against k=20 with bge-small:

- **bge-large**: +0.6 pp overall, but hurt Implicit Connections (−1.0 pp vs. k=10 bge-small)
- **k=20 bge-small**: +4.5 pp overall, +10.0 pp on Implicit Connections, same latency

More seeds increase the probability that all required turns land in the retrieved pool.
A denser embedding does not change relative rankings enough to matter.

### 6.2 Implicit Connections as the primary failure mode

Implicit Connections is the hardest category at every tier: 92.3% (tier 1) → 72.5%
(tier 2) → 55.7% (tier 3). These questions require bridging a vocabulary gap between
the question and the evidence message that a 384-dimensional sentence transformer only
partially captures. Graph expansion cannot recover missed evidence because implicit
connection turns are not positionally adjacent to better-ranked turns.

### 6.3 Tier degradation

Recall degrades predictably: tier 1 (0.963) → tier 2 (0.886) → tier 3 (0.837) →
tier 4 (0.843). The tier-3 to tier-4 gap is small because tier 4 covers only three
categories (all easier than Implicit Connections and Preferences). Each additional
required evidence message must independently land in the top-k seeds, and joint
probability decreases with n.

---

## 7. Conclusion

MemoryKG achieves **96.3%** mean retrieval recall at tier 1 with k=20 seeds, across
500 ConvoMem items, with no LLM required at any stage. This leads MemPal's published
92.9% by +3.4 pp, with MemoryKG ahead on four of five categories.

The key finding: **seed count is a more effective lever than model size.** k=10 → k=20
gains +4.5 pp overall and +10 pp on Implicit Connections at no additional latency;
switching to a 5× larger model gains only +0.6 pp and hurts on Implicit Connections.

The primary remaining failure mode is Implicit Connections (55.7% at tier 3), which
requires bridging a vocabulary gap that 384-dimensional embedders only partially
capture. Diversity-aware re-ranking or question reformulation are the identified
directions for further improvement.

**Limitations.** The recall metric measures whether evidence is *present* in the
retrieved context, not whether a downstream reader can correctly extract the answer.
End-to-end QA accuracy with a MemoryKG front-end is left for future work. Tiers 5
and 6 were not evaluated.

**Reproducibility.** All scripts, result JSONL files, and this article are in the
MemoryKG repository.

```bash
python benchmarks/convomem/convomem_bench.py --tier 1 --k 20
python benchmarks/convomem/convomem_bench.py --tier 2 --k 20
python benchmarks/convomem/convomem_bench.py --tier 3 --k 20
python benchmarks/convomem/convomem_bench.py --tier 4 --k 20
```

---

## References

- Pakhomov, E., Nijkamp, E., & Xiong, C. (2025). *ConvoMem Benchmark: Why Your First
  150 Conversations Don't Need RAG*. arXiv:2511.10523.
  <https://arxiv.org/abs/2511.10523>

- Anonymous. (2026). *MemPal: Raw Text Beats Extracted Memory: A Zero-API Baseline
  for Conversational Memory Retrieval*. <https://github.com/MemPalace/mempalace>

- Suchanek, E. G. (2026). *MemoryKG: A Hybrid Semantic-Graph Knowledge Base for
  Conversational Memory*. <https://github.com/Flux-Frontiers/memory_kg>

- Suchanek, E. G. (2026). *DocKG: Semantic Knowledge Graph for Document Corpora*.
  Version 0.11.0. DOI: <https://doi.org/10.5281/zenodo.19770973>

- Mem0 Team. (2024). *Mem0: The Memory Layer for Personalized AI*. <https://mem0.ai>

- Wang, X., et al. (2024). *LongMemEval: Benchmarking Chat Assistants on Long-Term
  Interactive Memory*. arXiv:2410.10813. <https://arxiv.org/abs/2410.10813>
