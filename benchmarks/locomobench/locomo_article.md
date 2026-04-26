# 98.1% Session Recall on LoCoMo: MemoryKG's Hybrid Semantic-Graph Architecture Achieves Near-Perfect Retrieval Across 1,986 Questions with No LLM Required

**Eric G. Suchanek, PhD** — suchanek@flux-frontiers.com
**Date:** April 25, 2026

---

## Abstract

We evaluate MemoryKG, a conversational memory system based on DocKG, on the
[LoCoMo benchmark](https://arxiv.org/abs/2402.15048) (Maharana et al., 2024),
a dataset of 1,986 questions spanning five categories that require locating
specific sessions within long-horizon social conversation corpora.

MemoryKG achieves **98.1% average session-level recall** across all five categories,
with **96.5% of questions answered perfectly** (all evidence sessions retrieved), and
only **1.0% total misses**. No LLM is required at any stage.

The hardest category is *Temporal-inference* (89.0%), which requires cross-session
reasoning rather than direct lookup; the easiest are *Temporal* and *Adversarial*
(both 99.6%).

A key architectural finding is that **session granularity substantially outperforms
dialog-turn granularity**: 98.1% vs. 73.9% — a **24.2 percentage point gap** —
confirming that session-level context aggregation is the correct retrieval unit for
LoCoMo's multi-turn evidence structure.

The full 1,986-question evaluation completes in **67.4 seconds** on Apple Silicon
(0.03 s/question).

---

## 1. Introduction

Long-horizon conversational memory — the ability to locate specific facts or events
from months of prior dialogue — is increasingly central to AI assistant design.
Retrieval approaches must navigate the dual challenge of semantic matching (finding
sessions whose *content* is relevant) and structural disambiguation (identifying
*which* session holds the evidence when many sessions discuss related topics).

The LoCoMo benchmark evaluates retrieval over long-horizon social conversation corpora.
Unlike single-fact or short-history benchmarks, LoCoMo conversations span many sessions
over extended time periods, with evidence scattered across temporally ordered dialog turns.

MemoryKG builds a persistent knowledge graph over verbatim conversation sessions,
combining semantic vector search (LanceDB) with structured graph expansion (SQLite).
In this paper we report MemoryKG's performance on LoCoMo and analyse the architectural
factors driving the results, with particular attention to the granularity question:
should retrieval units be entire sessions or individual dialog turns?

---

## 2. The LoCoMo Benchmark

LoCoMo contains 10 long-horizon social conversations between two participants, each
spanning many sessions over an extended period. From these, 1,986 QA pairs are
constructed, each paired with one or more *evidence dialog IDs* — the specific turns
whose content is necessary to answer the question.

| Category | n | Description |
|---|---|---|
| Single-hop | 282 | Answerable from a single dialog turn |
| Temporal | 321 | Requires knowing *when* an event occurred |
| Temporal-inference | 96 | Requires reasoning about event ordering across sessions |
| Open-domain | 841 | General questions; may draw on any session |
| Adversarial | 446 | Designed to exploit surface-level lexical overlap with wrong sessions |

The original LoCoMo paper reports end-to-end QA accuracy (requiring an LLM to generate
a free-form answer); we report session-level retrieval recall — whether the evidence
session is *present* in the retrieved context. These are complementary but distinct.
Our metric is a strict prerequisite for QA accuracy: no downstream reader can correctly
answer a question whose evidence was not retrieved.

---

## 3. MemoryKG Architecture

MemoryKG represents a conversation corpus as a four-layer knowledge graph:

1. **Document layer.** Each conversation session is a root document node.
2. **Section layer.** Markdown headings (one per dialog turn) produce section nodes
   connected to their parent document by `CONTAINS` edges.
3. **Chunk layer.** Section content is split into sentence-aligned chunks linked by
   `NEXT` edges.
4. **Semantic index.** All nodes are embedded and stored in LanceDB for ANN retrieval.

### Query pipeline

**Stage 1 — Semantic seeding.** The top-*k* nodes by cosine similarity are retrieved
from LanceDB. For LoCoMo, seeding is restricted to the current conversation's session
files via a per-query `haystack_files` filter — per-conversation isolation without
rebuilding the KG.

**Stage 2 — Graph expansion.** BFS expansion walks outward for *h* hops along edges in:

```
CONTAINS, NEXT, REFERENCES, SIMILAR_TO, HAS_TOPIC, MENTIONS_ENTITY, HAS_KEYWORD
```

Reachable nodes are ranked by a composite key combining seed distance, hop depth, and
structural position. For LoCoMo we use *k*=50 seeds and *h*=1 hop.

### LoCoMo corpus format

Each session is serialised as a Markdown file with the session as top-level heading and
each dialog turn as a second-level heading:

```markdown
# session_3

**Conversation:** conv-05
**Date:** 2023-08-14

## D3:1

Alice said, "I finally signed up for that pottery class."

## D3:2

Bob said, "That's great! You've been talking about it for months."
```

The heading chunk strategy splits at `##` boundaries, so each dialog turn becomes one
chunk node while the parent session document aggregates all turns.

---

## 4. Experimental Setup

| Parameter | Value |
|---|---|
| Chunk strategy | `heading` |
| Enrichment | Topics, entities, keywords enabled |
| SIMILAR_TO edges | Disabled (speed) |
| Workers | 8 |
| Batch size | 1,024 |
| Model | `BAAI/bge-small-en-v1.5` (384-dim) |
| k (seeds) | 50 |
| hop | 1 |

A single `SentenceTransformerEmbedder` is initialised once and passed to `MemoryKG`
via the `embedder=` argument, reused across all 1,986 questions.

**Recall computation:** Evidence dialog IDs (e.g. `D3:7`) are mapped to session IDs
(`session_3`). Recall is the fraction of evidence sessions present in the top-*k*
retrieved session IDs.

---

## 5. Results

### 5.1 Overall session-level recall

| Category | n | Recall |
|---|---|---|
| Single-hop | 282 | 0.950 |
| Temporal | 321 | 0.996 |
| Temporal-inference | 96 | 0.890 |
| Open-domain | 841 | 0.988 |
| Adversarial | 446 | 0.996 |
| **Overall** | **1,986** | **0.981** |

### 5.2 Recall distribution

| Outcome | Count | % |
|---|---|---|
| Perfect (1.0) | 1,916 | 96.5% |
| Partial (0–1) | 50 | 2.5% |
| Zero (0.0) | 20 | 1.0% |

### 5.3 Session vs. dialog granularity

| Category | Session | Dialog | Δ |
|---|---|---|---|
| Single-hop | **0.950** | 0.591 | +35.9 pp |
| Temporal | **0.996** | 0.786 | +21.0 pp |
| Temporal-inference | **0.890** | 0.579 | +31.1 pp |
| Open-domain | **0.988** | 0.808 | +18.0 pp |
| Adversarial | **0.996** | 0.703 | +29.3 pp |
| **Overall** | **0.981** | **0.739** | **+24.2 pp** |

Session granularity outperforms dialog-turn granularity across every category,
with gains exceeding 30 pp on Single-hop and Temporal-inference.

### 5.4 Throughput

| Metric | Value |
|---|---|
| Total time | 67.4 s |
| Per-question | 0.03 s |
| Hardware | Apple M5 Max, 64 GB RAM |

---

## 6. Analysis

### 6.1 Temporal-inference is the hardest category

Temporal-inference (89.0%) requires cross-session reasoning: not just finding
the session where an event occurred, but comparing the timing of multiple events
across sessions. A question such as "Which happened first, Alice starting pottery
or Bob changing jobs?" requires retrieving sessions for *both* events, where the
question vocabulary may match neither directly.

The 10.4% miss rate (vs. 0.4% for Temporal) reflects cases where events are
mentioned only briefly in sessions dominated by unrelated topics — a vocabulary
mismatch that neither semantic seeding nor one-hop graph expansion fully resolves.

### 6.2 Single-hop is harder than expected

Single-hop (95.0%) scores lower than Open-domain (98.8%) and Adversarial (99.6%).
The explanation: Single-hop evidence tends to be a specific isolated fact (a date,
a name, a number) mentioned in one turn without surrounding context that would boost
that session's embedding similarity to the question. Open-domain questions are
broader, matching more sessions and benefiting from aggregated topic and entity edges.

### 6.3 Adversarial questions and graph expansion

Adversarial questions (99.6%) are designed to share surface vocabulary with incorrect
sessions. MemoryKG's `HAS_TOPIC` and `MENTIONS_ENTITY` edges connect sessions to
their underlying semantic content, not just surface tokens. BFS expansion from a
correctly seeded session pulls in the true evidence even when the question vocabulary
superficially matches other sessions.

### 6.4 Why dialog granularity fails

At dialog-turn granularity, a single LoCoMo conversation produces 200–300 individual
turn files. With *k*=50 seeds, the system retrieves at most *k* × (fan-out) nodes —
but because each turn is now its own file, `CONTAINS` edges no longer propagate
session-level recall. The graph's enrichment edges have almost no text per file to
work with. The result is effectively flat vector search over individual turns, with
negligible graph advantage — explaining the 73.9% ceiling.

### 6.5 The persistent-KG advantage

Unlike per-conversation ChromaDB approaches (which rebuild an index for each
conversation), MemoryKG builds one persistent graph over all 10 conversations.
Per-conversation isolation is achieved at query time via `haystack_files` filtering
in LanceDB — restricting the *k*-NN seed search to the current conversation's files
without any rebuild. This is the key to 0.03 s/question throughput: the per-question
cost is vector search plus graph expansion only.

---

## 7. Conclusion

MemoryKG achieves **98.1% average session-level recall** on the full 1,986-question
LoCoMo benchmark, with **96.5% perfect** and only **1.0% total misses**. No LLM is
required at any stage.

The central finding is that **session granularity is the correct retrieval unit for
LoCoMo**, outperforming dialog-turn-level indexing by 24.2 pp overall. The graph's
`CONTAINS` edges from session documents to their constituent turn-level section nodes
mean that any turn appearing in the seed set propagates recall to the whole session —
a propagation mechanism that dialog-turn granularity destroys.

The hardest remaining category is Temporal-inference (89.0%), where miss cases involve
events whose sessions are semantically distant from the question vocabulary. Deeper
graph expansion (*h*=2) or temporal-aware reranking are natural directions for
improvement.

**Limitations.** Retrieval recall measures whether evidence is *present* in the
retrieved context, not whether a downstream reader can correctly extract the answer.
End-to-end QA accuracy on LoCoMo with a MemoryKG retrieval front-end is left for
future work.

**Reproducibility.** All benchmark scripts and result files are in the MemoryKG repo.

```bash
# Build the KG (one time):
python benchmarks/locomobench/locomo_bench_memkg.py prepare \
    benchmarks/locomobench/data/locomo10.json

# Run all 1,986 questions:
python benchmarks/locomobench/locomo_bench_memkg.py run \
    benchmarks/locomobench/data/locomo10.json
```

---

## References

- Maharana, A., Lee, D., Tuladhar, B., Piper, M., Choi, N., & Bansal, M. (2024).
  *LoCoMo: Long Context Motivated Long-Term Memory Consolidation and Retrieval.*
  arXiv:2402.15048. <https://arxiv.org/abs/2402.15048>

- Suchanek, E. G. (2026). *MemoryKG: A Hybrid Semantic-Graph Knowledge Base for
  Conversational Memory.* <https://github.com/Flux-Frontiers/memory_kg>

- Suchanek, E. G. (2026). *DocKG: Semantic Knowledge Graph for Document Corpora.*
  Version 0.11.0. DOI: <https://doi.org/10.5281/zenodo.19770973>

- Wang, X., et al. (2024). *LongMemEval: Benchmarking Chat Assistants on Long-Term
  Interactive Memory.* arXiv:2410.10813. <https://arxiv.org/abs/2410.10813>

- Pakhomov, E., Nijkamp, E., & Xiong, C. (2025). *ConvoMem Benchmark: Why Your
  First 150 Conversations Don't Need RAG.* arXiv:2511.10523.
  <https://arxiv.org/abs/2511.10523>
