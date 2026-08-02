# MemoryKG: conversational memory that you can actually inspect

**We just released MemoryKG.** It builds a deterministic knowledge graph over conversational logs and document corpora — SQLite for structure, a single-file vector index for speed. Retrieval seeds from embeddings and then expands through typed edges, so you can always ask *why* something came back.

---

## The problem it solves

Flat vector memory works right up until it doesn't, and then you are stuck. A passage you know exists doesn't surface, and there is nothing to debug — no structure, no provenance, just a cosine distance that came out lower than you hoped.

Meanwhile the corpus already has structure. Sessions have topics. Topics recur. Entities show up in more than one place. MemoryKG extracts that, stores it in SQLite as the canonical record, and uses embeddings only to find entry points.

## What it does

- **Chunk** a corpus — `semantic` (embedding-boundary detection), `heading`, `sentence_group`, or `fixed`
- **Extract** topics, named entities, keywords; build co-occurrence and similarity edges
- **Store** everything in SQLite with provenance on every edge
- **Index** into `vectors.sqlite` for fast natural-language seeding
- **Query** by seeding from vectors, expanding through the graph, ranking score-first
- **Pack** source-grounded passages ready to paste into a prompt

## Numbers

LongMemEval-S, 500 questions, session-granularity retrieval:

**97.6% R@5, 99.2% R@10, zero inference calls.** No LLM reranker.

The ablation is the interesting bit. Swapping MiniLM for BGE-small was worth 3.6 pp of R@5 (with haystack scoping held constant). **Restricting vector seeding to the per-question candidate sessions was worth 11.0 pp.** Score-first ranking was worth 8.8 pp.

Retrieval structure mattered several times more than the embedding model — which is roughly the argument for the whole project.

## Try it

```bash
pip install 'memory-kg @ git+https://github.com/Flux-Frontiers/memory_kg.git'

memorykg build --repo ./corpus
memorykg query "what did we decide about retries"
memorykg pack "deployment runbook" --fmt md --out context.md
```

Everything lands in `.memorykg/` — `graph.sqlite` (canonical) and `vectors.sqlite` (derived, delete and rebuild whenever). No server, no daemon.

There is an MCP server as well, so Claude Code or any MCP client can query the corpus directly.

## Honest caveats

- The benchmark numbers are **session-granularity on LongMemEval-S**. Different corpus, different results.
- Haystack scoping assumes you have a per-question candidate pool. Without one, expect the unscoped figure (86.6% R@5) rather than the headline.
- Topic and entity extraction is statistical, not LLM-driven. Deliberate — it keeps the graph deterministic — but the graph is only as good as the extractors.
- Licensed under Elastic 2.0, which is not OSI-approved.

## Related

**PyCodeKG** does the same thing for Python codebases; **DocKG** for general document corpora. All three register with **KGRAG** for federated queries across corpora.

Repo: https://github.com/Flux-Frontiers/memory_kg — feedback and issues welcome.
