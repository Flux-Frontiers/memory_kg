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
| Single-shot brittleness | Expansion is multi-hop **by construction** — a strong seed pulls in its structurally-linked neighbours (the second hop). One shot is not the design. |
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
4. We're reporting that straight because it's the whole point: **structure is not a
free lunch — it has to be the *right* structure.** Generic "entities co-occur" edges
are the wrong glue for dense Wikipedia QA, just as flat embeddings are the wrong glue
for code. The lesson isn't "graphs don't work." It's the same lesson the article is
really teaching: *the topology of your retrieval has to match the topology of your
data.* For code, that topology is the call/import graph — which is precisely why
PyCodeKG parses the AST instead of hoping cosine similarity reconstructs it.

So the benchmark we're building next is the one that meets the article head-on:
SWE-bench file localization — *given a real GitHub issue, find the file to edit* —
driven by PyCodeKG's AST graph. That is the fair fight, on the article's own turf, and
it's the right way to settle this rather than trading anecdotes.

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
agents over MCP. The HotpotQA harness and the in-progress SWE-bench harness referenced
above are in the `benchmarks/` directory.*
