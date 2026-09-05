# MemoryKG Benchmarks

MemoryKG is evaluated across four public conversational-memory benchmarks. All evaluations use **pure retrieval — no inference, no LLM, no API key**.

All figures below were reproduced on 2026-08-26 at commit `9754508`; see [`results_2026-08/`](results_2026-08/) for the verification record and [`RESULTS_SUMMARY.md`](RESULTS_SUMMARY.md) for the canonical LongMemEval numbers.

---

## Results at a Glance

| Benchmark | Metric | Score | Items | Notes |
|---|---|--:|--:|---|
| **LongMemEval-S** | Recall@5 | **98.2%** | 500 questions | 4 misses at @10 |
| **LongMemEval-S** | Recall@10 | **99.2%** | 500 questions | 100% at @30 |
| **LongMemEval-S** | Recall_all@10 | **98.8%** | 500 questions | Multi-session coverage |
| **LongMemEval-S** | NDCG@10 | **0.954** | 500 questions | — |
| **LoCoMo** | Session Recall | **98.1%** | 1,986 questions | 10 conversations, 272 sessions |
| **MemBench** | Recall@20 | **87.8%** | 1,100 items | 11 categories, 3 topics; scoping essential |
| **ConvoMem** | Recall@20 (tier 1) | **96.3%** | 500 items | Beats MemPal (+3.4 pp); 88.7% over all 1,897 |

---

## LongMemEval

**Benchmark:** [LongMemEval-S](https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned) — 500 questions over a corpus of **19,195 unique sessions** (528,083 graph nodes). Each question carries its own ~50-session haystack; the 23,867 figure quoted previously was the sum of per-question haystack slots, which double-counts sessions shared between questions.

**Task:** Given a question about a user's past conversations, retrieve the session(s) containing the answer from a 50-session haystack.

**MemoryKG result:** 98.2% Recall@5, 99.2% Recall@10, 98.8% Recall_all@10, 0.954 NDCG@10 — no LLM.

| @k | Recall_any | Recall_all | NDCG |
|---|--:|--:|--:|
| @1 | 0.904 | 0.306 | 0.904 |
| @5 | 0.982 | 0.968 | 0.950 |
| @10 | **0.992** | **0.988** | **0.954** |
| @30 | 1.000 | 0.994 | 0.955 |

There is one configuration, not two. Earlier revisions listed a "baseline" and a
"sibling boost" mode; the sibling boost is applied unconditionally to multi-session
questions and cannot be disabled, so only the second row was ever reachable.

→ Full progression, the MemPalace head-to-head, and how the 97.6-vs-98.4 dispute
resolved: [RESULTS_SUMMARY.md](RESULTS_SUMMARY.md)

```bash
# Build KG + run evaluation
poetry run python benchmarks/longmemeval/longmemeval_memkg.py prepare \
  /tmp/longmemeval_s_cleaned.json --wipe
poetry run python benchmarks/longmemeval/longmemeval_memkg.py run \
  /tmp/longmemeval_s_cleaned.json
```

---

## LoCoMo

**Benchmark:** [LoCoMo](https://github.com/snap-research/locomo) — 10 long-form conversations, 272 sessions, 1,986 QA pairs across 5 reasoning categories (~200 questions *per conversation*, not in total).

**Task:** Retrieve the session(s) containing the answer to questions about past conversations.

**MemoryKG result:** 98.1% session recall over 1,986 questions — no LLM. Weakest category is `temporal-inference` (89.0%, n=96); strongest are `temporal` and `adversarial` (99.6% each).

```bash
# Build KG + run evaluation
poetry run python benchmarks/locomobench/locomo_bench_memkg.py prepare \
  /path/to/locomo10.json --download
poetry run python benchmarks/locomobench/locomo_bench_memkg.py run \
  /path/to/locomo10.json
```

---

## MemBench

**Benchmark:** [MemBench](https://github.com/import-myself/Membench) (ACL 2025) — 1,100 items across 11 memory categories and 3 topics (movie, food, book).

**Task:** Retrieve the target turn(s) from multi-turn conversations containing the answer.

**MemoryKG result:** 87.8% recall@20 across all categories and topics — no LLM. The essential mechanism is per-item haystack scoping; without it recall collapses to 8.9%. Note that 176 of the 1,100 items (16.0%) have turn counts at or below k=20 and are trivially perfect; the runner reports this figure itself.

| Category | k=20 Recall | Category | k=20 Recall |
|---|--:|---|--:|
| simple | 0.970 | highlevel | 1.000 |
| knowledge_update | 0.990 | aggregative | 0.870 |
| comparative | 0.970 | conditional | 0.745 |
| noisy | 0.420 | post_processing | 0.720 |
| highlevel_rec | 0.990 | lowlevel_rec | 1.000 |
| RecMultiSession | 0.984 | — | — |

→ Full results and analysis: [membench/membench_article.md](membench/membench_article.md)

```bash
# All-in-one: download data, build KG, run evaluation
poetry run python benchmarks/membench/membench_bench.py all --topic all --limit 100
```

---

## ConvoMem

**Benchmark:** [ConvoMem](https://arxiv.org/abs/2511.10523) (Salesforce, 2025) — 75,336 QA pairs across six evidence categories and up to six evidence tiers. MemoryKG is evaluated on the 1,897 items in tiers 1-4. Not every category exists at every tier: tier 3 has no Preferences, and tier 4 has only User/Assistant/Changing Facts.

**Task:** Locate the specific conversation turns that contain the answer to a question, from a corpus of up to 300 sessions.

**MemoryKG result:** 96.3% recall@20 at tier 1 (500 items), beating MemPal's published 92.9% by +3.4 pp — no LLM.

| Category (tier 1) | k=20 Recall | vs. MemPal |
|---|--:|--:|
| User Facts | 0.990 | +1.0 pp |
| Assistant Facts | 0.990 | −1.0 pp |
| Abstention | 0.950 | +4.0 pp |
| Implicit Connections | 0.923 | +3.0 pp |
| Preferences | 0.960 | +10.0 pp |
| **Overall** | **0.963** | **+3.4 pp** |

Key finding: k=10→k=20 gains +4.5 pp at zero latency cost; a 5× larger model gains only +0.6 pp.

→ Full results and analysis: [convomem/convomem_article.md](convomem/convomem_article.md)

```bash
poetry run python benchmarks/convomem/convomem_bench.py --tier 1 --k 20
```

---

## How It Works

All four benchmarks use the same core pattern:

1. **Write conversations as Markdown** — one file per session (LoCoMo, LongMemEval) or one file per item (MemBench). Each turn or dialog is a `## Heading` that becomes its own chunk.

2. **Build one persistent MemoryKG** — SQLite graph + sqlite-vec vector index over the entire corpus. Built once, queried many times.

3. **Query with `haystack_files` scoping** — at query time, vector seeding is restricted to the files relevant to the current question. This eliminates cross-conversation noise without needing a separate database per conversation.

4. **Graph expansion (hop=1)** — seed nodes expand through structural edges (CONTAINS, NEXT, HAS_TOPIC, MENTIONS_ENTITY, HAS_KEYWORD) to recover vocabulary-mismatched neighbors.

**No LLM. No fact extraction. No inference. No API key.**

---

## Requirements

```bash
poetry install  # all dependencies managed
```

- Python 3.10+
- No GPU required (MPS recommended on Apple Silicon, CPU works)
- No API key
- Data auto-downloaded where supported (MemBench, LoCoMo); LongMemEval requires manual download from HuggingFace
