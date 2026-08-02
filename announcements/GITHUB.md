# MemoryKG: Deterministic Knowledge Graph for Conversational Logs and Document Corpora

**Tagline:** A deterministic, auditable knowledge graph over conversational logs and Markdown/text corpora, with semantic indexing and source-grounded passage packing. Structure is ground truth; embeddings are an acceleration layer.

---

## The Problem

Retrieval over long conversational history is usually a flat vector index: chunk everything, embed it, hope cosine similarity surfaces the right passage. That works until it doesn't, and when it doesn't you have no way to ask *why* — there is no structure to inspect, no provenance to follow, and no answer to "what else is this connected to".

Meanwhile the structure is right there in the text. Sessions have topics. Topics recur across sessions. Entities are mentioned in more than one place. Throwing that away and re-deriving it statistically at query time is a strange trade.

## What MemoryKG Does

MemoryKG semantically chunks conversational logs and document corpora, extracts topics, entities and keywords, links them through typed edges with provenance, and stores the whole thing in SQLite. A sqlite-vec vector index sits alongside as an *acceleration layer* — it seeds retrieval, it does not decide it.

1. **Chunk** with a strategy that fits the corpus — `semantic` (embedding-boundary detection), `heading`, `sentence_group`, or `fixed`
2. **Extract** topics, named entities and keywords; build co-occurrence and similarity edges automatically
3. **Store** everything in SQLite as the canonical, inspectable record
4. **Index** semantically with sqlite-vec for fast natural-language search
5. **Query** by seeding from vectors, then expanding through the graph and ranking score-first

## Why It's Different

- **Deterministic and auditable.** The graph is a SQLite file you can open with `sqlite3`. Every edge carries provenance. Nothing about the structure depends on a model's mood.
- **Structure as ground truth.** Semantic search finds entry points; typed-edge traversal decides what comes back. Embeddings are never a decision layer.
- **Rebuildable by construction.** The vector index is derived from SQLite and disposable — delete it and rebuild at any time with no data loss.
- **Haystack-scoped retrieval.** Vector seeding can be restricted to a per-question candidate pool, which is what makes benchmark-grade precision possible without a separate database per conversation.
- **Composable artifacts.** SQLite for structure, `vectors.sqlite` for vectors, Markdown/JSON for consumption. No server, no daemon, no external service.

## Benchmarks

On **LongMemEval-S** (500 questions, session-granularity retrieval), MemoryKG with haystack-filtered seeding and BGE-small-en-v1.5 reaches **97.6% R@5 and 99.2% R@10 with zero inference calls** — no LLM reranker anywhere in the pipeline.

Full tables, the per-question-type breakdown, and the ablation that got there are in [`benchmarks/RESULTS_SUMMARY.md`](../benchmarks/RESULTS_SUMMARY.md).

The single largest win was not the embedding model. It was **haystack-scoped seeding** — restricting vector seeds to the per-question candidate sessions rather than the full 23,867-session corpus (+11.0 pp R@5 on its own).

## Quick Start

```bash
pip install 'memory-kg @ git+https://github.com/Flux-Frontiers/memory_kg.git'

# Index a corpus — SQLite graph + vector index in one step
memorykg build --repo docs/

# Natural-language query, ranked chunks
memorykg query "authentication flow"

# Source-grounded passage pack, straight into an LLM prompt
memorykg pack "configuration reference" --fmt md --out context.md
```

`memorykg build` wipes and rebuilds by default. `memorykg build-graph` and
`memorykg build-index` run the two phases separately when you want to re-embed
without re-parsing.

## Artifacts

```
.memorykg/
├── graph.sqlite        # canonical graph — nodes, typed edges, provenance
├── vectors.sqlite      # derived semantic index (disposable)
└── snapshots/          # temporal metric snapshots (tracked in git)
```

## AI Agent Integration

MemoryKG ships an MCP server exposing four tools — `query_docs`, `pack_docs`, `get_node`, and `graph_stats`:

```bash
memorykg mcp --repo /path/to/corpus
```

Point Claude Code, Claude Desktop, or any MCP client at it and the corpus becomes queryable structure rather than a wall of text.

## Also Available

MemoryKG shares its architecture with two siblings:

- **[PyCodeKG](https://github.com/Flux-Frontiers/pycode_kg)** — the same approach applied to Python codebases
- **[DocKG](https://github.com/Flux-Frontiers/doc_kg)** — general document corpora

All three register with **KGRAG** for federated cross-corpus queries.

## Built With

- **SQLite** — canonical graph store
- **sqlite-vec** — vector index (exact search, single file, no server)
- **sentence-transformers** — embeddings, `BAAI/bge-small-en-v1.5` by default
- **Click**, **Rich**, **Streamlit**, **MCP**

## License

Elastic License 2.0.
