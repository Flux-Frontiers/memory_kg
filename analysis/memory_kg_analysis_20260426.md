> **Analysis Report Metadata**
> - **Generated:** 2026-04-26T02:52:08Z
> - **Version:** pycode-kg 0.16.0
> - **Commit:** a3b7ad6 (main)
> - **Platform:** macOS 26.4.1 | arm64 (arm) | Turing | Python 3.12.13
> - **Graph:** 4425 nodes · 4205 edges (346 meaningful)
> - **Included directories:** src
> - **Excluded directories:** tests
> - **Elapsed time:** 4s

# memory_kg Analysis

**Generated:** 2026-04-26 02:52:08 UTC

---

## Executive Summary

This report provides a comprehensive architectural analysis of the **memory_kg** repository using PyCodeKG's knowledge graph. The analysis covers complexity hotspots, module coupling, key call chains, and code quality signals to guide refactoring and architecture decisions.

| Overall Quality | Grade | Score |
|----------------|-------|-------|
| [A] **Excellent** | **A** | 90 / 100 |

---

## Baseline Metrics

| Metric | Value |
|--------|-------|
| **Total Nodes** | 4425 |
| **Total Edges** | 4205 |
| **Modules** | 39 (of 39 total) |
| **Functions** | 95 |
| **Classes** | 46 |
| **Methods** | 166 |

### Edge Distribution

| Relationship Type | Count |
|-------------------|-------|
| CALLS | 1456 |
| CONTAINS | 307 |
| IMPORTS | 307 |
| ATTR_ACCESS | 1322 |
| INHERITS | 3 |

---

## Fan-In Ranking

Most-called functions are potential bottlenecks or core functionality. These functions are heavily depended upon across the codebase.

| # | Function | Module | Callers |
|---|----------|--------|---------|
| 1 | `close()` | src/memory_kg/kg.py | **11** |
| 2 | `close()` | src/memory_kg/store.py | **11** |
| 3 | `con()` | src/memory_kg/store.py | **9** |
| 4 | `store()` | src/memory_kg/kg.py | **6** |
| 5 | `_rewrap()` | src/memory_kg/snapshots.py | **5** |
| 6 | `_extract_links()` | src/memory_kg/chunker.py | **5** |
| 7 | `extract()` | src/memory_kg/graph.py | **4** |
| 8 | `_groups_to_chunks()` | src/memory_kg/chunker.py | **4** |
| 9 | `_get_kg()` | src/memory_kg/mcp_server.py | **4** |
| 10 | `embed_texts()` | src/memory_kg/index.py | **4** |
| 11 | `to_json()` | src/memory_kg/kg.py | **4** |
| 12 | `to_markdown()` | src/memory_kg/kg.py | **4** |
| 13 | `_slug()` | src/memory_kg/relations.py | **3** |
| 14 | `to_dict()` | src/memory_kg/kg.py | **3** |
| 15 | `_split_sentences()` | src/memory_kg/chunker.py | **3** |


**Insight:** Functions with high fan-in are either core APIs or bottlenecks. Review these for:
- Thread safety and performance
- Clear documentation and contracts
- Potential for breaking changes

---

## High Fan-Out Functions (Orchestrators)

Functions that call many others may indicate complex orchestration logic or poor separation of concerns.

No extreme high fan-out functions detected. Well-balanced architecture.

---

## Module Architecture

Top modules by dependency coupling and cohesion (showing up to 10 with activity).
Cohesion = incoming / (incoming + outgoing + 1); higher = more internally focused.

| Module | Functions | Classes | Incoming | Outgoing | Cohesion |
|--------|-----------|---------|----------|----------|----------|
| `src/memory_kg/kg.py` | 1 | 4 | 9 | 3 | 0.23 |
| `src/memory_kg/index.py` | 7 | 4 | 3 | 0 | 0.00 |
| `src/memory_kg/snapshots.py` | 5 | 4 | 1 | 0 | 0.00 |
| `src/memory_kg/chunker.py` | 5 | 3 | 1 | 0 | 0.00 |
| `src/memory_kg/memorykg_semantic_analysis.py` | 5 | 4 | 1 | 2 | 0.50 |
| `src/memory_kg/store.py` | 1 | 2 | 6 | 1 | 0.12 |
| `src/memory_kg/memorykg_thorough_analysis.py` | 5 | 2 | 2 | 2 | 0.40 |
| `src/memory_kg/sampler.py` | 0 | 3 | 1 | 0 | 0.00 |
| `src/memory_kg/memorykg.py` | 12 | 2 | 5 | 2 | 0.25 |
| `src/memory_kg/embedder_worker.py` | 1 | 2 | 0 | 0 | 0.00 |

---

## Key Call Chains

Deepest call chains in the codebase.

**Chain 1** (depth: 3)

```
__exit__ → close → close
```

**Chain 2** (depth: 3)

```
build_graph → store → GraphStore
```

---

## Public API Surface

Identified public APIs (module-level functions with high usage).

| Function | Module | Fan-In | Type |
|----------|--------|--------|------|
| `MemoryKG()` | src/memory_kg/kg.py | 10 | class |
| `SnapshotManager()` | src/memory_kg/snapshots.py | 5 | class |
| `pack()` | src/memory_kg/cli/cmd_query.py | 3 | function |
| `SentenceTransformerEmbedder()` | src/memory_kg/index.py | 3 | class |
| `GraphStore()` | src/memory_kg/store.py | 3 | class |
| `build()` | src/memory_kg/cli/cmd_build.py | 3 | function |
| `DocEdge()` | src/memory_kg/memorykg.py | 3 | class |
| `BuildStats()` | src/memory_kg/kg.py | 2 | class |
| `DocNode()` | src/memory_kg/memorykg.py | 2 | class |
| `main()` | src/memory_kg/memorykg_semantic_analysis.py | 1 | function |
---

## Docstring Coverage

Docstring coverage directly determines semantic retrieval quality. Nodes without
docstrings embed only structured identifiers (`KIND/NAME/QUALNAME/MODULE`), where
keyword search is as effective as vector embeddings. The semantic model earns its
value only when a docstring is present.

| Kind | Documented | Total | Coverage |
|------|-----------|-------|----------|
| `function` | 95 | 95 | [OK] 100.0% |
| `method` | 163 | 166 | [OK] 98.2% |
| `class` | 46 | 46 | [OK] 100.0% |
| `module` | 38 | 39 | [OK] 97.4% |
| **total** | **342** | **346** | **[OK] 98.8%** |

---

## Structural Importance Ranking (SIR)

Weighted PageRank aggregated by module — reveals architectural spine. Cross-module edges boosted 1.5×; private symbols penalized 0.85×. Node-level detail: `pycodekg centrality --top 25`

| Rank | Score | Members | Module |
|------|-------|---------|--------|
| 1 | 0.185163 | 2 | `src/memory_kg/cli/group.py` |
| 2 | 0.109899 | 22 | `src/memory_kg/store.py` |
| 3 | 0.108045 | 31 | `src/memory_kg/kg.py` |
| 4 | 0.067713 | 24 | `src/memory_kg/snapshots.py` |
| 5 | 0.065612 | 26 | `src/memory_kg/index.py` |
| 6 | 0.053587 | 23 | `src/memory_kg/chunker.py` |
| 7 | 0.040636 | 16 | `src/memory_kg/sampler.py` |
| 8 | 0.039995 | 15 | `src/memory_kg/memorykg.py` |
| 9 | 0.037326 | 22 | `src/memory_kg/memorykg_semantic_analysis.py` |
| 10 | 0.036782 | 9 | `src/memory_kg/graph.py` |
| 11 | 0.030006 | 18 | `src/memory_kg/memorykg_thorough_analysis.py` |
| 12 | 0.029545 | 12 | `src/memory_kg/embedder_worker.py` |
| 13 | 0.026367 | 11 | `src/memory_kg/topics.py` |
| 14 | 0.024750 | 9 | `src/memory_kg/semantic_extractor.py` |
| 15 | 0.021244 | 12 | `src/memory_kg/pipeline.py` |



---

## Code Quality Issues

- [WARN] 2 orphaned functions found (`main`, `_silent_init`) -- consider archiving or documenting

---

## Architectural Strengths

- Well-structured with 15 core functions identified
- No god objects or god functions detected
- Good docstring coverage: 98.8% of functions/methods/classes/modules documented

---

## Recommendations

### Immediate Actions
1. **Remove or archive orphaned functions** — `main`, `_silent_init` have zero callers and add maintenance burden

### Medium-term Refactoring
1. **Harden high fan-in functions** — `close`, `close`, `con` are widely depended upon; review for thread safety, clear contracts, and stable interfaces
2. **Reduce module coupling** — consider splitting tightly coupled modules or introducing interface boundaries
3. **Add tests for key call chains** — the identified call chains represent well-traveled execution paths that benefit most from regression coverage

### Long-term Architecture
1. **Version and stabilize the public API** — document breaking-change policies for `MemoryKG`, `SnapshotManager`, `pack`
2. **Enforce layer boundaries** — add linting or CI checks to prevent unexpected cross-module dependencies as the codebase grows
3. **Monitor hot paths** — instrument the high fan-in functions identified here to catch performance regressions early

---

## Inheritance Hierarchy

**3** INHERITS edges across **4** classes. Max depth: **1**.

| Class | Module | Depth | Parents | Children |
|-------|--------|-------|---------|----------|
| `SentenceTransformerEmbedder` | src/memory_kg/index.py | 1 | 1 | 0 |
| `Embedder` | src/memory_kg/index.py | 0 | 0 | 1 |
| `Snapshot` | src/memory_kg/snapshots.py | 0 | 1 | 0 |
| `SnapshotManager` | src/memory_kg/snapshots.py | 0 | 1 | 0 |


---

## Snapshot History

Recent snapshots in reverse chronological order. Δ columns show change vs. the immediately preceding snapshot.

| # | Timestamp | Branch | Version | Nodes | Edges | Coverage | Δ Nodes | Δ Edges | Δ Coverage |
|---|-----------|--------|---------|-------|-------|----------|---------|---------|------------|
| 1 | 2026-04-25 15:17:53 | develop | 0.11.0 | 4417 | 4201 | 78.0% | — | — | — |


---

## Appendix: Orphaned Code

Functions with zero callers (potential dead code):

| Function | Module | Lines |
|----------|--------|-------|
| `main()` | src/memory_kg/app.py | 110 |
| `_silent_init()` | src/memory_kg/index.py | 3 |
---

## CodeRank -- Global Structural Importance

Weighted PageRank over CALLS + IMPORTS + INHERITS edges (test paths excluded). Scores are normalized to sum to 1.0. This ranking seeds Phase 2 fan-in discovery and Phase 15 concern queries.

| Rank | Score | Kind | Name | Module |
|------|-------|------|------|--------|
| 1 | 0.000875 | method | `GraphStore.con` | src/memory_kg/store.py |
| 2 | 0.000807 | method | `DocGraph.extract` | src/memory_kg/graph.py |
| 3 | 0.000646 | function | `_rewrap` | src/memory_kg/snapshots.py |
| 4 | 0.000636 | function | `_slug` | src/memory_kg/relations.py |
| 5 | 0.000574 | method | `MemoryKG.store` | src/memory_kg/kg.py |
| 6 | 0.000544 | function | `_extract_links` | src/memory_kg/chunker.py |
| 7 | 0.000523 | method | `MemoryKG.embedder` | src/memory_kg/kg.py |
| 8 | 0.000489 | method | `TextPack.to_dict` | src/memory_kg/kg.py |
| 9 | 0.000456 | function | `_groups_to_chunks` | src/memory_kg/chunker.py |
| 10 | 0.000450 | function | `_embed_shard` | src/memory_kg/embedder_worker.py |
| 11 | 0.000449 | function | `_get_kg` | src/memory_kg/mcp_server.py |
| 12 | 0.000432 | function | `_split_sentences` | src/memory_kg/chunker.py |
| 13 | 0.000414 | function | `_load_store` | src/memory_kg/app.py |
| 14 | 0.000398 | method | `SentenceGroupChunker._sentence_group_chunks` | src/memory_kg/chunker.py |
| 15 | 0.000395 | method | `GraphStore.close` | src/memory_kg/store.py |
| 16 | 0.000395 | method | `SentenceTransformerEmbedder.embed_texts` | src/memory_kg/index.py |
| 17 | 0.000395 | method | `TopicExtractor._load_topic_map` | src/memory_kg/topics.py |
| 18 | 0.000395 | method | `MemoryKG.close` | src/memory_kg/kg.py |
| 19 | 0.000381 | class | `ThemeSummary` | src/memory_kg/memorykg_semantic_analysis.py |
| 20 | 0.000358 | function | `_delta_to_dict` | src/memory_kg/snapshots.py |

---

## Concern-Based Hybrid Ranking

Top structurally-dominant nodes per architectural concern (0.60 × semantic + 0.25 × CodeRank + 0.15 × graph proximity).

### Configuration Loading Initialization Setup

| Rank | Score | Kind | Name | Module |
|------|-------|------|------|--------|
| 1 | 0.75 | method | `MemoryKG.__init__` | src/memory_kg/kg.py |
| 2 | 0.7477 | function | `_init_state` | src/memory_kg/app.py |
| 3 | 0.7358 | method | `TextChunker.__init__` | src/memory_kg/chunker.py |
| 4 | 0.7354 | method | `HeadingChunker.__init__` | src/memory_kg/chunker.py |
| 5 | 0.7339 | method | `SentenceGroupChunker.__init__` | src/memory_kg/chunker.py |

### Data Persistence Storage Database

| Rank | Score | Kind | Name | Module |
|------|-------|------|------|--------|
| 1 | 0.8192 | method | `GraphStore.con` | src/memory_kg/store.py |
| 2 | 0.809 | method | `MemoryKG.store` | src/memory_kg/kg.py |
| 3 | 0.7017 | method | `ProvMeta.__init__` | src/memory_kg/store.py |
| 4 | 0.6995 | method | `SnapshotManager.save_snapshot` | src/memory_kg/snapshots.py |
| 5 | 0.6973 | method | `MemoryKG.build` | src/memory_kg/kg.py |

### Query Search Retrieval Semantic

| Rank | Score | Kind | Name | Module |
|------|-------|------|------|--------|
| 1 | 0.75 | method | `SemanticIndex.search` | src/memory_kg/index.py |
| 2 | 0.747 | method | `MemoryKG.query` | src/memory_kg/kg.py |
| 3 | 0.7375 | function | `query` | src/memory_kg/cli/cmd_query.py |
| 4 | 0.7179 | method | `Embedder.embed_query` | src/memory_kg/index.py |
| 5 | 0.7174 | function | `query_docs` | src/memory_kg/mcp_server.py |

### Graph Traversal Node Edge

| Rank | Score | Kind | Name | Module |
|------|-------|------|------|--------|
| 1 | 0.7576 | method | `DocGraph.edges` | src/memory_kg/graph.py |
| 2 | 0.7517 | method | `SemanticIndex._discover_similar_edges` | src/memory_kg/index.py |
| 3 | 0.7465 | method | `GraphStore.edges_from` | src/memory_kg/store.py |
| 4 | 0.7413 | method | `GraphStore.edges_within` | src/memory_kg/store.py |
| 5 | 0.7399 | method | `DocGraph.result` | src/memory_kg/graph.py |



---

*Report generated by PyCodeKG Thorough Analysis Tool — analysis completed in 4.1s*
