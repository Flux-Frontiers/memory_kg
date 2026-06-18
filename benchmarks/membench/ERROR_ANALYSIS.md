# MemBench Error Analysis — where the 12% goes, and why BM25 won't fix it

**Run analyzed:** `results/membench_memkg_all_all_k20_hop1_20260426_0048.jsonl`
(1,100 items, k=20, hop=1, **overall recall 87.7%**)

This analysis was done to decide whether porting doc_kg's **hybrid lexical (BM25)
+ dense** retrieval into MemoryKG is worth the risk. Conclusion: **no** — the
remaining headroom is reasoning/aggregation, not lexical retrieval, and BM25
would likely *regress* the worst category.

## Per-category recall (k=20)

| Category | Recall | Mean evidence turns | Nature of the gap |
|---|---|---|---|
| lowlevel_rec | 1.00 | 2.0 | — |
| highlevel | 1.00 | 4.0 | — |
| knowledge_update | 0.99 | 1.0 | — |
| comparative | 0.97 | 2.0 | — |
| simple | 0.97 | 1.0 | — |
| highlevel_rec | 0.98 | 2.6 | — |
| RecMultiSession | 0.98 | 4.4 | — |
| **aggregative** | **0.87** | 8.0 | multi-evidence breadth + counting |
| **conditional** | **0.745** | 2.0 | 2-hop relational lookup |
| **post_processing** | **0.72** | 2.0 | 2-hop lookup + post-processing |
| **noisy** | **0.42** | 2.0 | distractor robustness |

## The decisive finding

Across the four weak categories there are **237 misses (recall < 1.0)**. Broken
down by how many evidence turns the item requires:

| Category | Misses | Single-evidence (retrieval-addressable) | Multi-evidence (reasoning/aggregation) |
|---|---|---|---|
| noisy | 92 | **0** | 92 |
| conditional | 49 | **0** | 49 |
| post_processing | 53 | **0** | 53 |
| aggregative | 43 | **0** | 43 |

**0 of 237 misses are single-evidence retrieval failures.** Every miss is a
multi-evidence item where the system retrieves *some* of the required turns but
not *all* of them. The single-fact / single-evidence categories that BM25 would
help (`simple`, `lowlevel_rec`, `knowledge_update`) are already at 0.97–1.00 —
dense retrieval is **not** losing on vocabulary mismatch.

## What each weak category actually is

**noisy (0.42)** — the question is padded with rambling distractor sentences,
*including decoy questions*, before the real ask:

> *"I was thinking about going for a hike this weekend, but then again, I
> remembered I need to finish that book. Did you see the weather forecast? …
> Oh, what I truly wanted to clarify is, **What position does someone who has
> rock climbing as a hobby hold?**"* → `Customer Service Representative`

The distractor text pollutes the dense query embedding. **BM25 would make this
worse**, not better — it matches the distractor tokens ("hike", "book", "oven",
"keys") directly. This is the textbook case where lexical search hurts.

**conditional (0.745)** — 2-hop relational lookup:

> *"What is the email address of the person who is 148 cm tall?"* →
> `lila.thompson@…` (recall 0.50 = found the height turn **or** the email turn,
> not both)

The bottleneck is bridging two turns by entity, not finding a lexically-distinct
chunk. A graph-traversal / entity-linking problem.

**post_processing (0.72)** — find-by-attribute, then read/compute another field:

> *"What are the main responsibilities of a person born on August 23rd?"* →
> requires the birthday turn **and** the responsibilities turn.

**aggregative (0.87)** — must retrieve **all** N evidence turns and count:

> *"How many people live in Philadelphia, PA?"* → found 6/8, 7/8 … recall is
> turn-completeness. Bottleneck is recall breadth + the k budget, not vocabulary.

## Verdict

**Do not port BM25 hybrid retrieval to chase MemBench.** It cannot touch the
reasoning/aggregation gaps that make up 100% of the headroom, and it would
likely regress `noisy` (the worst category), where distractors share vocabulary.

## The `noisy` gap is a query-surface artifact, not a retrieval weakness

This is a **probe, not a scoreboard result.** To test whether `noisy`'s low score
reflects a real retrieval weakness, we strip the rambling preamble from the query
(keeping only the trailing real question) and re-seed (`denoise.py` +
`measure_denoise.py`):

| | recall |
|---|---|
| raw (baseline) | 0.4250 |
| denoised | 0.7450 |
| delta | +0.3200 (59 improved, 2 regressed, 39 unchanged) |

When the surface noise is removed, retrieval recovers — so the gap was the
**query's surface form, not MemoryKG's memory/retrieval ability.** That is the
finding worth keeping.

> ⚠️ **Honesty caveat — do NOT report this as a MemBench improvement.** The
> denoiser's "last capitalized wh-clause" rule is *fitted to MemBench's synthetic
> `noisy` generator* (real question always last, capitalized wh-word, lowercase
> pivots). Those are artifacts of that generator, not robust properties of real
> rambling queries — so this is a **benchmark-shaped heuristic**, and the implied
> "≈ +2.9pp overall" must **not** be folded into any headline MemBench number.
> It is shipped only as an **opt-in, default-off** `denoise=True` flag, documented
> as a probe. To claim it as a real capability, validate generalization on a
> different noise distribution (or replace the regex with a principled
> query-rewriter). It is a no-op on clean categories (0/100 changed on `simple`,
> `conditional`, `aggregative`, `comparative`, `knowledge_update`).

## Real levers (play to the graph, not lexical search)

1. **conditional / post_processing** — strengthen entity-linking so the bridging
   entity connects the two turns; consider higher `hop`/expansion for
   attribute-lookup queries. This is what the KG is *for*.
2. **aggregative** — aggregation-aware retrieval (gather all turns for the
   matched entity) and a higher `k` for counting questions.

## Reproduce

```bash
python - <<'PY'
import json
f="benchmarks/membench/results/membench_memkg_all_all_k20_hop1_20260426_0048.jsonl"
items=[json.loads(l) for l in open(f) if l.strip() and not json.loads(l).get("_meta")]
weak=["noisy","conditional","post_processing","aggregative"]
for c in weak:
    ds=[x for x in items if x["category"]==c and x["recall"]<1.0]
    single=[x for x in ds if x["details"]["evidence_turns"]==1]
    print(f"{c}: {len(ds)} misses, {len(single)} single-evidence (BM25-addressable)")
PY
```
