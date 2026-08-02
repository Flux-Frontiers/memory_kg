You are an AI agent with a brand new MCP tool. It is called **MemoryKG**. It was written by Eric G. Suchanek, PhD. (me!) and lives at:

https://github.com/Flux-Frontiers/memory_kg.git

MemoryKG is a hybrid semantic + structural knowledge graph for **document corpora** — Markdown files, plain text, personal notes, memories, and any text collection. It parses documents into nodes (documents, sections, chunks, topics, entities, keywords) and edges (CONTAINS, HAS_TOPIC, MENTIONS_ENTITY, HAS_KEYWORD, REFERENCES, SIMILAR_TO), persists the graph in SQLite, and builds a sqlite-vec vector index for semantic search.

The conceptual progenitor of the tool was **DocKG**, my earlier document knowledge graph system, which MemoryKG grew from and superseded. MemoryKG extends DocKG with:

- Semantic layer: events, assertions, supersession edges (temporal updates)
- Manifold analysis: intrinsic dimensionality, MRL truncation quality, PCA elbow
- Multipass pipeline: diversity sampling → chunking → classification → embedding → manifold
- Streamlit visualizer (`memorykg viz`)
- Claude Code auto-ingest hooks (pre-commit + PostToolUse)

I want you to provide a thorough assessment of the **functional utility of MemoryKG** with respect to understanding and querying document corpora from YOUR perspective as an AI agent. Is it useful? Does the hybrid semantic + structural retrieval model offer something that pure vector search does not? Compare and contrast to your typical workflow when working with large document collections. I designed this to provide quick, grounded, and useful corpus analysis and retrieval.

I want YOU to use the **MemoryKG MCP tools** to analyze the corpus currently indexed (use `graph_stats`, `query_docs`, `pack_docs`, `get_node`) and provide an overall assessment of the **TOOL**, not the specific corpus. Is it good? Does it help? Is it unique? Would you recommend it for AI-assisted knowledge work?

The four MemoryKG MCP tools available to you are:

| Tool | Purpose |
|------|---------|
| `graph_stats()` | Node/edge counts and coverage summary — start here |
| `query_docs(q)` | Hybrid semantic + graph query; returns ranked node JSON |
| `pack_docs(q)` | Same query but returns Markdown text excerpts for LLM context |
| `get_node(node_id)` | Fetch a single node by its stable ID |

Save your assessment in Markdown with filename following the template:

```
./analysis/MemoryKG_assessment_<model_name>_<datestamp>.md
```
