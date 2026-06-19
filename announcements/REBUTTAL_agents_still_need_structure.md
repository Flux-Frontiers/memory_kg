# Your Agent Doesn't Need Vector Search. It Needs Structure — and a Graph Is the Cheapest Place to Put It.

*A response to "AI Agents Don't Need Vector Search Anymore: Inside the Agentic Search Stack Replacing RAG in 2026."*

Grewal's piece is the best articulation I've read of a real shift: coding agents that
`grep`, `glob`, and `read` their way to an answer are beating bolted-on vector
indexes, and Boris Cherny isn't exaggerating when he says it "outperformed
everything." If you are building a coding agent and you reach for "embed the whole
repo, do one top-k lookup" as your retrieval layer, you should stop. That part is
correct, and it's correct for the reasons the article gives.

But the title smuggles in a bigger claim than the body defends, and the bigger claim
is wrong. "Agents don't need vector search" quietly becomes "agents don't need a
**precomputed index**," and those are not the same statement. What the article has
actually shown is that *one specific, impoverished use of vectors* — flatten
everything into a single embedding space and retrieve once — loses to an agent that
re-derives structure at query time. The right conclusion isn't "throw away the index."
It's **"put structure in the index, and let the agent call it as a tool."**

## The strawman in the middle of the argument

Read the five criticisms of "RAG" carefully and notice they are all criticisms of the
*same naive system*:

1. Semantic similarity isn't structural relevance (it misses imports and call graphs).
2. `processPayment` vs `handlePayment` needs exact identifiers, not fuzzy cosine.
3. Every commit invalidates part of the index.
4. The index is a second copy of your code on weaker infra.
5. Single-shot top-k gets one chance and answers confidently from half the evidence.

Every one of these is an indictment of **flat embeddings + one-shot retrieval**. None
of them is an indictment of *precomputed retrieval as a category*. The article even
says so itself when it lists the approaches it likes — Cline, Probe, ast-grep, "the
structural / AST-aware flavour." Those are precomputed structure. The author isn't
against indexes. He's against *bad* indexes and in favor of *grep, which is also an
index* — just one that's recomputed from cold on every call.

So the honest framing isn't "vector search vs. agents." It's a single axis:

> **precomputed structure  ⟷  just-in-time re-derivation**

And the two ends fail in mirror-image places. The article is candid about where
agentic search loses, and the list is devastating if you actually have a product SLA:

- **5–30× the tokens** per task (15× for multi-agent).
- **Seconds of latency**, 5–10 tool calls per query — unusable for interactive chat.
- **Non-deterministic** — you cannot regression-test or SLA an agentic loop.
- **No advantage on massive corpora** — `ripgrep` over a 10M-file monorepo is just a
  scan.
- **Loses on scattered synonyms** — `backoff` / `requeue` / `circuit_breaker` defeat
  literal search.

Every item on that list is a home game for a precomputed structural index. Determinism,
millisecond latency, $0 per query, and concept-level (not literal) matching are
exactly what you give up when you replace the index with a `grep` loop.

## What "the index" should have been all along

The thing the article is really arguing against — and the thing it accidentally argues
*for* — is a knowledge graph the agent queries as a tool. Concretely, the design we've
been shipping (PyCodeKG for Python code, MemoryKG for documents, DocKG for general
corpora) inverts the naive RAG assumption:

> **Structure is ground truth. The vector index is an accelerator, not the source of
> truth.** Semantic search only *seeds*; typed-edge graph traversal *expands*; a
> deterministic score *ranks*. No LLM in the retrieval loop.

Walk the five criticisms again, this time against a typed graph instead of a flat
blob:

| The article's complaint about "RAG" | What a structural KG actually does |
|---|---|
| Similarity ≠ structural relevance | The edges **are** the structure. PyCodeKG extracts `CALLS`, `IMPORTS`, `INHERITS`, `CONTAINS`, `RESOLVES_TO` straight from the AST. Graph proximity is a first-class ranking signal, not an afterthought. |
| Identifier exact-match | Retrieval is scored by lexical containment, not pure cosine, and `RESOLVES_TO` resolves import aliases so fan-in is **exact**, not fuzzy. |
| Single-shot brittleness | Two answers: (a) the index is a *tool the agent re-queries* deterministically, not a one-shot pipeline; and (b) graph expansion measurably recovers cross-file targets that single-shot similarity misses — **+0.21 symbol-recall@20 on multi-file SWE-bench fixes** — though only in that regime (see the regime map below). |
| Staleness on every commit | Incremental rebuilds + temporal **snapshots and diffs**: you can ask "what changed structurally between v1 and v2," deterministically. |
| Non-deterministic, un-testable | The whole pipeline is deterministic, explainable, snapshot-diffable, and free per query — the *opposite* of an agentic loop. |

This is not a rebuttal we wrote after reading the article. It's the architecture, and
the article is describing — from the outside, as a gap — the system that already
closes it. The punchline writes itself: agentic search is right that your agent should
*call a tool* to retrieve. We just think the tool should be a precomputed graph, not a
cold `grep`, because the graph already knows what `grep` has to rediscover every time.

## We tried to prove ourselves wrong (and partly did)

Here's the part most "X is dead" rebuttals skip. We didn't want to assert that graph
beats flat — we wanted a number, so we built a multi-hop benchmark and ran it. On
HotpotQA (combine two facts hidden among eight distractors), we compared flat top-k
against the same retriever with graph expansion turned on.

**Graph expansion lost.** On a 100-question sample, flat top-k got both supporting
paragraphs into the top 5 on 70% of questions; turning on the default entity-based
expansion *dropped* it to 61%, net-displacing gold on 13 questions while rescuing only
4.

Then we ran the fight on the article's own turf — **SWE-bench** code localization,
*given a real GitHub issue, find what to edit*, driven by PyCodeKG's AST graph. We ran
it five ways, and the result is not a slogan in either direction — it's a *map* of
where structure helps:

| benchmark / regime | does graph expansion help? |
|---|---|
| HotpotQA (dense passage QA) | **hurts** (−0.09) |
| SWE-bench single-file, file-level | null |
| SWE-bench single-file, symbol-level | ~null (+0.006) |
| SWE-bench multi-file, file-level | null |
| **SWE-bench multi-file, symbol-level** | **helps (+0.21 recall@20)** |

Flat retrieval is already strong on the easy regimes (gold file in the top-5 on 10/13
single-file instances, $0/query, deterministic). And for four of five regimes, turning
on graph expansion does *nothing* or hurts — so we are **not** going to tell you the
graph is a magic reranker. But in the fifth — multi-file fixes, scored at the level of
the exact function being changed — expansion recovered **3 of 14** gold symbols that
flat retrieval missed *entirely* (symbol-recall@20 0.57 → 0.79), with **zero
regressions**, and every win was one of the patches that spans the most files. That is
the article's own deepest claim — *similarity isn't structural relevance* — confirmed
with a sign and a magnitude: when the answer is genuinely cross-file and structural,
the call graph reaches it and cosine doesn't.

So the honest finding, stated plainly: **graph expansion is regime-specific, not a
universal win** — and we can now point to exactly the regime where it pays. Two more
things the data says the article should sit with:

1. **A precomputed, deterministic index is already competitive** — 0.77 file-level
   recall@5, at $0 per query, in milliseconds, fully reproducible. That is the bar
   agentic `grep` has to clear while spending 5–30× the tokens and seconds of latency
   on a non-reproducible answer. On accuracy it's a wash; on cost, latency, and
   determinism the precomputed index wins outright.
2. **The graph's real value isn't ranking — it's queries embeddings can't express at
   all.** We measured this too, on `requests`. Ask *"who calls `httpbin`?"*: PyCodeKG
   returns **45 exact caller functions**; `grep "\bhttpbin\s*\("` returns **98 raw
   textual hits** with no idea which function each belongs to, mixed with comments and
   strings. Ask *"what's the change blast-radius"* or *"what's dead code"* (235
   functions with zero callers): no embedding produces these at all. (Honest caveat:
   PyCodeKG resolves Python method calls *by name*, so caller sets for names shared
   across classes — `get`, `__init__` — are over-approximations, the same failure class
   as `grep`. The exact wins are uniquely-named symbols and the aggregate views.) Even
   with that caveat, *this* is the structure the article says vectors miss — and it
   lives in typed edges, not in a similarity score.

The lesson from both nulls is the article's own, sharpened: *the topology of your
retrieval has to match the topology of your data, and "more graph" is not automatically
better.* Structure earns its keep as **deterministic substrate + queryable capability**,
not as a magic reranker. We'd rather publish that than a number we tuned until it
flattered us.

## What to actually do on Monday

- **If you have a coding agent over a live tree:** yes, let it use tools. But give it a
  *built* tool — an MCP server backed by a structural graph — so it spends tokens on
  reasoning, not on re-deriving the import graph with `grep` on every turn.
- **If you embedded your repo into a flat vector store:** the article is right, that's
  the weak design. Don't conclude "no index." Conclude "structural index."
- **If you need determinism, low latency, or $0/query:** the agentic loop can't give
  you those. A precomputed graph can.

Agents don't need vector search. They need structure — imports, calls, inheritance,
the actual shape of the code. Vector search was always just a lossy way to *guess* at
that structure. The fix isn't to guess harder at query time with an LLM and a `grep`.
It's to compute the structure once, exactly, and hand it to the agent.

Don't embed your repo. **Graph it.**

---

*PyCodeKG, MemoryKG, and DocKG are open-source structural knowledge-graph builders
(AST graph for code; semantic+structural graph for docs and memory), each exposed to
agents over MCP. The HotpotQA and SWE-bench harnesses referenced above — including the
null results — are in the `benchmarks/` directory, runnable and reproducible.*
