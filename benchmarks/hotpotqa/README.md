# MemoryKG × HotpotQA — Multi-Hop Retrieval

HotpotQA is the first **multi-hop, document-corpus** benchmark in this suite. The
other four (LongMemEval, LoCoMo, MemBench, ConvoMem) are conversational-memory
tasks — "find the message that states fact X." HotpotQA is different: every
question requires **combining two gold paragraphs** hidden among eight distractors,
so it tests the one thing flat top-k retrieval is weakest at and graph expansion
is built for — recovering the *second hop*.

## Why this benchmark

Abdullah Grewal's *"AI Agents Don't Need Vector Search Anymore"* (2026) argues
single-shot top-k retrieval is brittle: it "gets one chance," and the second-hop
passage is often only weakly similar to the question, so the agent confidently
answers from half the evidence. MemoryKG's reply is structural expansion — a
`MENTIONS_ENTITY` edge from the strongly-matching first-hop chunk surfaces the
bridge paragraph that cosine similarity never ranks highly. HotpotQA turns that
argument into a number.

The head-to-head is a single flag:

| `--hop` | Behaviour | Maps to |
|--------:|-----------|---------|
| `0` | pure semantic top-k | the flat RAG baseline the article defends |
| `1` | semantic seed **+** graph expansion | MemoryKG's structural recovery |

## Metric: `recall_all@N`

We report **paragraph-level `recall_all@N`** — the fraction of questions for which
*every* gold paragraph appears in the top-N retrieved chunks. This mirrors the
`recall_all@10` metric used on LongMemEval: for multi-hop, getting one hop is not
enough, so partial recall is not credited. `recall_all@2` is the hardest and most
revealing cutoff (both gold paragraphs pinned in the top 2 of 10). All scoring is
**LLM-free** — paragraph membership of retrieved chunks, no inference, no API key.

## Running it

```bash
# Downloads hotpot_dev_distractor_v1.json (~46 MB) to the cache on first run,
# then evaluates a 200-question sample with graph expansion.
poetry run python benchmarks/hotpotqa/hotpotqa_bench.py --limit 200

# The article's comparison — run both and diff recall_all@2/@5:
poetry run python benchmarks/hotpotqa/hotpotqa_bench.py --limit 200 --hop 0   # flat
poetry run python benchmarks/hotpotqa/hotpotqa_bench.py --limit 200 --hop 1   # + graph

# Ablate the bridge edges (entity/keyword linking off):
poetry run python benchmarks/hotpotqa/hotpotqa_bench.py --limit 200 --no-entities
```

If the CMU mirror is unreachable, download the distractor dev set manually from
<https://hotpotqa.github.io> and pass the path as the first positional argument.

## What to look for

The thesis is validated if `--hop 1` lifts `recall_all@2/@5` over `--hop 0`,
and if `--no-entities` erases that lift — i.e., the gain comes specifically from
the entity bridge edges, not from returning more nodes. Per-type breakdown
(`bridge` vs `comparison` questions) shows where the graph helps most: bridge
questions are the genuine two-hop chains.
