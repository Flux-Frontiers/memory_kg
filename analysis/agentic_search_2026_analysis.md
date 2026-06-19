# Agentic Search vs. the KG Stack — Analysis (June 2026)

**Source:** Abdullah Grewal, *"AI Agents Don't Need Vector Search Anymore: Inside the
Agentic Search Stack Replacing RAG in 2026"* (Medium, 2026).

**Scope of this note:** what the article actually claims, how those claims land
against the Flux-Frontiers KG stack — **PyCodeKG** (Python code), **MemoryKG**
(conversational memory + docs), **DocKG** (general document corpora) — and a new
benchmark (**HotpotQA**) added to put a number on the central claim.

---

## 1. What the article actually argues

The headline is broad; the argument is narrow. The real claim is: **for a coding
agent operating over a live filesystem, just-in-time tool calls (`grep`/`glob`/`read`)
beat a pre-built vector index.** Retrieval becomes a *behaviour of the agent*, not a
system upstream of it. Supporting anecdote: Boris Cherny on Claude Code — *"It
outperformed everything. By a lot."*

Five criticisms of vector RAG:

1. **Semantic similarity ≠ relevance** — flat embeddings miss explicit structure:
   imports, call graphs, inheritance.
2. **Identifier matching** — `processPayment` vs `handlePayment` needs exact keyword
   search; vectors hallucinate near-misses.
3. **Index staleness** — "every commit invalidates part of the index."
4. **Security** — a vector index is a second copy of proprietary code on weaker infra.
5. **Single-shot brittleness** — top-k gets one chance; miss the file → confidently
   wrong.

And the article's own concessions — where agentic `grep` loses:

- **5–30× more tokens** per task; multi-agent ~15×.
- **Latency** — seconds, 5–10 tool calls per query; unfit for interactive chat.
- **Non-determinism** — agentic loops aren't reproducible; bad for SLAs and
  regression tests.
- **Massive corpora** — `ripgrep` over a 10M-file monorepo has no precomputed-index
  advantage.
- **Semantic synonyms** — concepts scattered as `backoff`/`requeue`/`circuit_breaker`
  defeat literal search.

---

## 2. The key reframing

The article is arguing against a **strawman RAG**: "flatten everything into one
embedding, do one top-k lookup, stop." That is precisely the design the KG stack was
built to *not* be. Across all three siblings the architecture is the same and is the
rebuttal:

> **Structure is ground truth; the vector index is an acceleration layer, not the
> source of truth.** Semantic search *seeds*; typed-edge graph traversal *expands*;
> a deterministic score ranks.

So the honest framing is not "agentic search vs. KG." It's a **precomputed-structure
↔ just-in-time axis**, and the two ends fail in opposite places. Every weakness the
article concedes for agentic search — latency, determinism, massive fixed corpora,
scattered-synonym concepts — is a KG home-game. And the KG isn't *outside* the
agentic stack: the MCP server (`query_docs`/`query_codebase`/`pack_*`) is exactly a
**tool an agent calls** instead of re-grepping from cold. The right posture is
"agents should call the deterministic index," not "RAG is dead, we disagree."

### Claim-by-claim

| Article's criticism of "RAG" | KG-stack answer |
|---|---|
| Similarity ≠ structural relevance | Typed edges *are* the structure: MemoryKG `HAS_TOPIC`/`MENTIONS_ENTITY`; **PyCodeKG `CALLS`/`IMPORTS`/`INHERITS`/`CONTAINS`/`RESOLVES_TO`**. Graph proximity is a ranking signal, not an afterthought. |
| Identifier / exact-match failure | Recall is scored by **substring containment**, not pure cosine — the stack already leans lexical. PyCodeKG's `RESOLVES_TO` resolves import aliases so fan-in is exact, not fuzzy. |
| Single-shot brittleness | **Structural expansion**: a weak seed surfaces strongly-linked neighbours (the second hop). Multi-hop by construction, not one-shot. |
| Index staleness | Incremental `build --update`; temporal **snapshots + diffs** track version-over-version drift deterministically. |
| Non-deterministic, un-regression-testable | The whole stack is **deterministic, explainable, $0/query, no LLM** — the exact opposite of an agentic loop, and snapshot-diffable in CI. |
| Massive corpora / latency | Precomputed SQLite+LanceDB answers in milliseconds; no per-query agent loop. |

---

## 3. PyCodeKG — the system the article is *actually* aimed at

The article is about **code** search; MemoryKG is about docs/memory. The sibling that
sits squarely in the article's crosshairs is **PyCodeKG** (v0.19.3). It is the
strongest counter-example to criticism #1, because it does the one thing the author
says vector search can't:

- Walks the **AST** of every module/class/function/method and extracts the typed
  relationships that "actually hold the code together": `CONTAINS`, `CALLS`,
  `IMPORTS`, `INHERITS`, `RESOLVES_TO`.
- Ranks functions by **structural importance** (centrality, **bridge_centrality**),
  traces **fan-in across import aliases**, detects **circular imports** and **dead
  code** — all from the graph, no inference.
- A LanceDB index sits *alongside* the graph so `"authentication flow"` and
  `verify_jwt` both find a starting node — then traversal does the rest.
- Ships the result to an agent over **MCP** (`query_codebase`, `callers`, `explain`,
  `centrality`, `bridge_centrality`, `framework_nodes`, `rank_nodes`).

In the article's own terms: PyCodeKG is the **"structural / AST-aware" flavour** it
lists approvingly (alongside Cline, Probe, ast-grep) — *not* the flat-embedding
strawman it attacks. The agentic-`grep` approach recovers structure by *re-deriving*
it at query time, every time, non-deterministically. PyCodeKG computes it **once**,
deterministically, and hands an agent the answer. For a fixed repo analysed
repeatedly (CI, architecture review, onboarding), precompute wins on cost, latency,
and reproducibility — the agent's three weak spots.

**SWE-bench result (now measured).** PyCodeKG had no retrieval benchmark (only an
embedder micro-benchmark), so we built one (`benchmarks/swebench/`) and ran it: real
GitHub issue → AST KG over the repo@base_commit → query → score whether retrieval
surfaces the file(s) the gold patch edits. On a 13-instance Lite sample
(requests/flask/seaborn), **flat semantic retrieval put the gold file in the top-5 on
10/13 instances (recall@5 = 0.77, MRR = 0.49)** — competitive, deterministic,
$0/query. **AST graph hop-expansion changed nothing (Δ = 0.000 on every metric):**
each Lite instance edits one file, so once seeding surfaces it, `CALLS`/`IMPORTS`
neighbours only map to already-ranked files. Hop-expansion is the wrong lever for
*file*-level localization (it would matter for symbol-level or multi-file fixes).

> Note (per discussion): **DocKG** performs the same multi-hop graph expansion for
> general document corpora, so structural expansion is a *stack-wide* property of all
> three siblings, not a MemoryKG-only trick.

We also built the *symbol*-level metric — does retrieval surface the exact
function/method the patch edits (node span overlaps a gold base-commit line) — because
that is the regime where call-graph expansion *should* finally pay off. It didn't:
sym_recall@10 = 0.692 for both hops, Δ symbol-MRR = **+0.006**, with hop-1 recovering
exactly one gold symbol and only at rank ≤20.

### Synthesis — structural expansion is regime-specific (and we found the regime)

Five measurements, and the pattern is precise rather than uniform:

| benchmark / regime | does hop>0 help? |
|---|---|
| HotpotQA (dense passage QA, co-occurrence edges) | **hurts** (−0.09 recall_all@5) |
| SWE-bench single-file, file-level | null (Δ 0.000) |
| SWE-bench single-file, symbol-level | ~null (Δ MRR +0.006) |
| SWE-bench **multi-file, file-level** | null (Δ 0.000) |
| SWE-bench **multi-file, symbol-level** (n=14) | **helps** (+0.21 sym_recall@20; 3/14 recovered, 0 regressed) |

The multi-file/symbol result is the one positive, and it is exactly where theory
predicts: a fix spanning several files has an edited symbol that pure similarity to the
issue text misses, but cross-file `CALLS`/`IMPORTS` expansion reaches. All three wins
are the **pylint multi-file patches (2–4 gold files)**; the gain grows with file count,
and nothing regresses. So the honest claim is **not** "the graph always reranks better"
— four of five measurements say it doesn't — but rather: **retrieval topology must
match data topology, and when the answer is genuinely cross-file and structural,
structural expansion recovers what flat retrieval cannot.** That is a *confirmation* of
the article's own deepest point ("similarity ≠ structural relevance"), now with a sign
and a magnitude. The rebuttal rests on three things the data supports:

1. **A precomputed, deterministic index is already competitive** (0.77 file-level
   recall@5) at $0/query, milliseconds, fully reproducible — the axes where the
   article admits agentic `grep` loses (5–30× tokens, seconds, non-determinism).
2. **The graph answers structural queries embeddings cannot express and `grep`
   approximates badly** — measured in `benchmarks/capabilities/` on `psf/requests`:
   - **"Who calls `httpbin`?"** PyCodeKG returns **45 exact caller functions**; `grep`
     returns **98 raw textual hits** it cannot attribute to a function or tell apart
     from comments/strings.
   - **Fan-in blast-radius** and a **235-function dead-code set** — aggregate views no
     similarity score can produce.
   - **Honest limitation:** PyCodeKG's Python call graph resolves method calls *by name*
     (no type inference), so caller sets for shared names (e.g. `get`) are
     over-approximations — the same failure class as `grep`, just structured. The clean,
     exact wins are for uniquely-named symbols and the aggregate views. (Filed as a
     finding: `analysis/pycodekg_call_resolution_finding.md`.)
3. **Structural expansion helps in its own regime** — multi-file, symbol-level code
   localization: +0.21 sym_recall@20 over flat retrieval, recovering cross-file symbols
   similarity misses. Not a universal reranker, but a real, measurable win where the
   answer is cross-file and structural.

Structure earns its keep as **deterministic substrate + queryable capability +
regime-matched expansion** — not as a magic reranker, and "more graph" is not
automatically better.

---

## 4. The real gap the article exposed — and the benchmark we added

All four existing MemoryKG benchmarks (LongMemEval, LoCoMo, MemBench, ConvoMem) are
**conversational memory**: "find the message stating fact X." None test *combining
facts across documents* — the precise thing the article says flat retrieval fails at
and graph expansion is built for. So we added **HotpotQA (distractor)**, a multi-hop
Wikipedia QA benchmark: each question needs **two gold paragraphs** hidden among
eight distractors.

- Harness: `benchmarks/hotpotqa/hotpotqa_bench.py` (mirrors `convomem_bench.py`).
- Metric: **`recall_all@N`** — fraction of questions for which *every* gold paragraph
  is in the top-N retrieved chunks (partial recall is not credited; getting one hop
  is not enough). LLM-free, $0/query.
- The article's head-to-head is one flag: `--hop 0` (flat top-k, the baseline it
  defends) vs `--hop 1` (semantic seed **+** graph expansion).

### Results (100-question dev sample, BGE-small-en-v1.5, CPU)

| Metric | `--hop 0` (flat top-k) | `--hop 1` (+ graph expansion) |
|---|--:|--:|
| Para Recall@10 (per-paragraph) | **0.855** | 0.825 |
| recall_all@2 (both hops in top-2) | **0.43** | 0.36 |
| recall_all@5 (both hops in top-5) | **0.70** | 0.61 |
| recall_all@10 (both hops in top-10) | **0.71** | 0.67 |
| bridge questions, recall_all@5 (n=79) | **0.62** | 0.53 |
| comparison questions, recall_all@5 (n=21) | **1.00** | 0.91 |

Paired diagnostic (same questions, hop 0 vs hop 1), at recall_all@5: graph
**recovered 4** questions that flat retrieval missed, but **displaced gold in 13**
that flat retrieval had. Chunk-coverage of the returned set is nearly identical
(4.19 vs 4.33 chunks/question), so this is **not** a return-budget artifact — it is
the ranking.

### Reading the result — honestly

**This did *not* validate the "graph recovers the second hop" thesis on HotpotQA.**
In the default configuration MemoryKG's hybrid expansion *underperforms* a plain
chunk-only top-k, and it does so by net-displacing gold (−13/+4 at @5). The article's
flat baseline wins here. Reported straight, no spin.

Why — three likely causes, all config/transfer issues rather than a refutation of
graph retrieval in principle:

1. **Wrong bridge edge for this corpus.** The default expansion uses entity/keyword
   **co-occurrence** edges. On a dense 10-paragraph haystack, incidental shared
   entities link *distractor* paragraphs to the seed, and the seed-distance ranking
   floats them above gold. HotpotQA's real bridge is a *named-entity title overlap*,
   not co-occurrence of arbitrary terms.
2. **Tuned for a different shape.** The stack's expansion was tuned on conversational
   memory — *sparse* 50-session haystacks where the answer chunk is far from
   distractors. HotpotQA is the opposite: 8 deliberately *near* distractors. The
   regime doesn't transfer out of the box.
3. **Entity/keyword nodes dilute seeding.** With `seed_kinds=None`, the top-k semantic
   seeds include entity/keyword nodes, leaving fewer *chunk* seeds (~4 chunks surface
   per question). Flat top-k spends its whole budget on chunks.

**The honest takeaway:** on this benchmark the win for the stack is *not* "graph beats
flat" — it's that even flat MemoryKG retrieval is a legitimate, deterministic, $0,
no-API-key baseline (0.71 both-hops@10) that the agentic-`grep` approach has to beat
on cost and latency, not just accuracy. Making expansion *help* here is a tuning
problem (title-overlap edges, chunk-only seeding, `--no-entities` ablation, or simply
`hop=0` for dense haystacks), and that ablation is the obvious follow-up — but it must
be done as honest ablation, not tuned until the graph wins.

---

## 5. Recommendations

1. **Reposition, don't rebut.** Public messaging should be "the deterministic index
   is the tool your agent should call," not "vector search is fine." The article's
   audience already agrees structure matters — PyCodeKG *is* structure.
2. **Scale the SWE-bench harness (now built).** The Lite pilot (n=13) shows flat
   retrieval at 0.77 file-recall@5. Run SWE-bench Verified at larger n, add
   *symbol*-granularity scoring and multi-file instances — that is where AST expansion
   (`callers`/`CALLS`) might actually move the needle, since file-level localization
   provably doesn't exercise it.
3. **Do not publish any "graph reranks better" claim — our own data refutes it.** Both
   HotpotQA (expansion hurts) and SWE-bench (Δ = 0.000) say hop-expansion is not a
   ranking win. Lead instead with the two defensible pillars: (a) competitive
   *deterministic, $0, reproducible* retrieval, and (b) structural query capabilities
   (callers, fan-in, centrality, dead code) that embeddings cannot express at all.
   Expansion is corpus-shape-dependent and must only ever be claimed from honest
   ablation, never tuned until it flatters.
4. **Lean into the concessions.** Determinism, $0/query, snapshot-diffable retrieval,
   and millisecond latency on fixed corpora are the four axes where the article
   admits agents lose. That is the stack's marketing surface.
