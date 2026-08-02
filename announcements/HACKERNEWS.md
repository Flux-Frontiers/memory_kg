# Show HN: MemoryKG — a deterministic knowledge graph for conversational memory

**Tagline:** Structure-first retrieval over conversational logs and document corpora. SQLite is the source of truth; embeddings are an acceleration layer. 97.6% R@5 on LongMemEval-S with zero inference calls.

---

## The pitch

Most long-term memory for agents is a flat vector index. Chunk everything, embed it, retrieve by cosine similarity. It works surprisingly well and fails opaquely — when the right passage doesn't come back there is nothing to inspect, because there is no structure, only a distance.

MemoryKG takes the other approach. It semantically chunks a corpus, extracts topics, entities and keywords, links them with typed provenance-carrying edges, and stores all of it in SQLite. A `vectors.sqlite` index sits alongside for fast natural-language seeding. Retrieval seeds from vectors, then expands through the graph and ranks score-first.

The graph is the product. The embeddings are a convenience.

## Why you might care

- **You can audit it.** The graph is a SQLite file. Open it with `sqlite3` and ask why something ranked where it did. Every edge carries provenance.
- **It's rebuildable.** The vector index is derived and disposable. Delete it, rebuild it, lose nothing.
- **No server.** SQLite plus a single-file vector index. No daemon, no external service, no network calls at query time.
- **Embeddings never decide.** They find entry points. Typed-edge traversal decides what comes back and in what order.

## Results

LongMemEval-S, 500 questions, session-granularity retrieval, BGE-small-en-v1.5:

**97.6% R@5 · 99.2% R@10 · zero inference calls.**

No LLM reranker anywhere in the pipeline. Full tables and the per-question-type breakdown are in `benchmarks/RESULTS_SUMMARY.md`.

The interesting part is the ablation. Going from MiniLM to BGE-small bought 3.6 pp of R@5 (holding haystack scoping constant). **Haystack-scoped seeding bought 11.0 pp** — restricting vector seeds to the per-question candidate sessions rather than searching all 23,867 sessions. Second-largest was score-first ranking (ordering by base distance rather than hop distance), worth 8.8 pp.

That ordering is the whole thesis in miniature: the retrieval structure mattered several times more than the embedding model.

## How it works

```
corpus (Markdown / text / conversational logs)
   │
   ├─ semantic chunking (semantic | heading | sentence_group | fixed)
   ├─ topic / entity / keyword extraction
   ├─ typed edges + co-occurrence + similarity
   │
   ├──► graph.sqlite     canonical, auditable
   └──► vectors.sqlite   derived, disposable
```

Query: vector seed → graph expansion along typed edges → score-first ranking → source-grounded passage pack.

## Try it

```bash
pip install 'memory-kg @ git+https://github.com/Flux-Frontiers/memory_kg.git'

memorykg build --repo ./corpus
memorykg query "what did we decide about retries"
memorykg pack "deployment runbook" --fmt md --out context.md
```

There's an MCP server too (`memorykg mcp`), exposing `query_docs`, `pack_docs`, `get_node` and `graph_stats` — so Claude Code or any MCP client can query the corpus as structure instead of as a wall of text.

## Related

Two siblings share the architecture: **PyCodeKG** for Python codebases and **DocKG** for general document corpora. All three register with **KGRAG** for federated cross-corpus queries.

## Caveats, honestly

- Retrieval quality above is **session-granularity on LongMemEval-S**. Your corpus is not that corpus.
- Haystack scoping needs a per-question candidate pool. Without one you are running unscoped search and should expect the unscoped numbers (86.6% R@5), not the headline.
- Extraction is deterministic, not clever. Topics and entities come from statistical extractors, not an LLM. That is the point, but it does mean the graph is only as good as the extractors.
- Elastic License 2.0, not OSI-approved. Check it before building a product on it.

Repo: https://github.com/Flux-Frontiers/memory_kg
