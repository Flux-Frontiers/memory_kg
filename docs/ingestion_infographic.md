# MemoryKG Ingestion Architecture — Infographic Reference

**Two pipelines. One hybrid knowledge graph.**

---

## THE TWO PIPELINES

```
DOCUMENT CORPUS  (.md / .txt / .rst)
         │
    ┌────┴────┐
    ▼         ▼
CORE BUILD   MULTIPASS ANALYSIS
memorykg     memorykg pipeline run
build
    │         │
    ▼         ▼
SQLite +    .psv files +
LanceDB     embeddings.json
    │         │
    ▼         ▼
MCP server  Manifold / MRL
query/pack  analysis
```

---

## PIPELINE 1 — CORE BUILD (`memorykg build`)

**Purpose:** Fast, deterministic graph for MCP server, queries, and packing.

### Data Flow

```
Corpus files
  └─► PASS 1: DocGraph / parse_corpus  →  SQLite (GraphStore)
        │  Per file:
        │  1. Parse headings → section hierarchy
        │  2. Emit doc + section nodes + CONTAINS edges
        │  3. Chunk text (strategy: semantic/fixed/sentence_group/heading)
        │  4. Emit chunk nodes + CONTAINS + NEXT edges
        │  5. Detect hyperlinks → REFERENCES edges
        │  6. Topic classify → HAS_TOPIC edges
        │  7. Entity extract → MENTIONS_ENTITY edges
        │  8. Keyword extract → HAS_KEYWORD edges
        │  9. Co-occurrence* → CO_OCCURS_WITH edges  (* off by default)
        │
        └─► PASS 2: SemanticIndex.build  →  LanceDB + SIMILAR_TO
              1. Read all nodes from SQLite
              2. Batch-embed via SentenceTransformerEmbedder
              3. Write vectors to LanceDB
              4. k-NN per chunk → SIMILAR_TO edges (cosine ≥ 0.85)
```

### Key Components

| Class / Function | File | Role |
|-----------------|------|------|
| `MemoryKG` | `kg.py` | Orchestrator: `build()`, `query()`, `pack()` |
| `DocGraph` | `graph.py` | OO corpus layer (wraps `parse_corpus`, cached) |
| `parse_corpus()` | `memorykg.py` | Deterministic file → nodes + edges |
| `TextChunker` | `chunker.py` | Semantic segmentation (4 strategies) |
| `GraphStore` | `store.py` | SQLite persistence |
| `SemanticIndex` | `index.py` | LanceDB vector index + SIMILAR_TO discovery |
| `TopicExtractor` | `topics.py` | Keyword-based topic classification |

### Node Kinds

| Kind | ID Pattern | One Per |
|------|-----------|---------|
| `document` | `doc:<file_path>` | `.md` / `.txt` file |
| `section` | `sec:<file_path>:<slug>` | Markdown heading |
| `chunk` | `chunk:<file_path>:<0000>` | ~512-char text block |
| `topic` | `topic:<slug>` | Topic label |
| `entity` | `entity:<slug>` | Titlecase / acronym |
| `keyword` | `keyword:<slug>` | Salient keyword |

### Edge Types

| Edge | Direction | When |
|------|-----------|------|
| `CONTAINS` | doc → sec → chunk | Always |
| `NEXT` | chunk → chunk | Always |
| `REFERENCES` | chunk → doc | Hyperlinks present |
| `SIMILAR_TO` | chunk ↔ chunk | Cosine ≥ 0.85 |
| `HAS_TOPIC` | chunk → topic | `--enable-topics` |
| `MENTIONS_ENTITY` | chunk → entity | `--enable-entities` |
| `HAS_KEYWORD` | chunk → keyword | `--enable-keywords` |
| `CO_OCCURS_WITH` | semantic ↔ semantic | `--emit-cooccur` (off by default) |

### Embedding Model (Core Build)

| Model | Dims | Notes |
|-------|------|-------|
| `BAAI/bge-small-en-v1.5` | 384 | Default (`MEMORYKG_MODEL` env override) |
| `all-mpnet-base-v2` | 768 | Higher-quality alternative |

### Commands

```bash
memorykg build --repo docs                         # Full build (default: wipe)
memorykg build --repo docs --update                # Incremental
memorykg build-graph --repo docs                   # Pass 1 only → SQLite
memorykg build-index                               # Pass 2 only → LanceDB
```

---

## PIPELINE 2 — MULTIPASS ANALYSIS (`memorykg pipeline`)

**Purpose:** Deep NLP, diversity sampling, corpus embedding, manifold analysis.

### 5-Phase Data Flow

```
Corpus files
  └─► PHASE 1: CorpusSampler
        - NLP feature extraction per doc (tokens, entities, sentences)
        - K-means clustering on feature vectors
        - Proportional sample per cluster (default: 20 docs)
        - Feature cache: .memorykg/cache/<hash>.pkl
        │
        └─► PHASE 2: TextChunker / SentenceGroupChunker
              - Default: N sentences per chunk (N=4, ~400-500 chars)
              - Alt: semantic (embedding-based boundary detection)
              - Hard splits at Markdown section boundaries
              │
              └─► PHASE 3: TopicExtractor.classify_hybrid()
                    - Supervised: keyword catalog → score ≥ 0.3
                    - Unsupervised fallback: K-means on embeddings
                    - Keyword fallback: pseudo-topic from top keywords
                    │
                    └─► PHASE 4: EntryChunk creation
                          - chunk_id (content hash), text, provenance
                          - topics, topic_method, keywords, entities
                          - Optional embedding vector + run_id
                          │
                          └─► PHASE 5: .psv structured output
                                - .memorykg/pipeline/PipelineRun_<id>_<ts>.psv
                                - Header: run params
                                - Rows: chunk_id | topic | conf | method | kw | text
                                - Footer: classification statistics
```

### Post-Pipeline Stages

```
STAGE 3: CorpusEmbedder          STAGE 4: ManifoldAnalyzer
  nomic-ai/nomic-embed-text-v1     PCA elbow (90/95/99%)
  768-dim, asymmetric prefix       Participation Ratio
  Spawn-safe multiprocess          TwoNN intrinsic dimension
  Output: embeddings.json          MRL truncation quality (MRR@10)
```

### Key Components (Multipass)

| Class | File | Phase |
|-------|------|-------|
| `AnalysisPipeline` / `PipelineConfig` | `pipeline.py` | Orchestrator |
| `CorpusSampler` / `DocFeatures` | `sampler.py` | Phase 1 |
| `SentenceGroupChunker` | `chunker.py` | Phase 2 |
| `TopicExtractor.classify_hybrid()` | `topics.py` | Phase 3 |
| `EntryChunk` / `SourceProvenance` | `entry_chunk.py` | Phase 4 |
| `CorpusEmbedder` | `embedder_worker.py` | Stage 3 |
| `ManifoldAnalyzer` | `manifold.py` | Stage 4 |

### Sampling Strategies

| Strategy | Method | Use When |
|----------|--------|----------|
| `diversity` | K-means on NLP features | Default — thematic coverage |
| `random` | Simple random sample | Quick exploration |
| `temporal` | Evenly spaced by file order | Chronological corpora |

### Embedding Model (Pipeline)

| Model | Dims | Notes |
|-------|------|-------|
| `BAAI/bge-small-en-v1.5` | 384 | Default — reads `MEMORYKG_MODEL` env var (same as core build) |

### Commands

```bash
memorykg pipeline run --repo docs --batch 20 --strategy sentence_group
memorykg pipeline embed --repo docs --workers 4
memorykg pipeline manifold --repo docs
```

---

## PIPELINE 3 — POST-BUILD ANALYSIS

### Structural Analysis (`memorykg analyze`)
6 phases: baseline stats → doc metrics → semantic coverage →
orphan detection → hot chunk ranking → insight generation
Output: Markdown + JSON at `~/.claude/memorykg_analysis_latest.json`

### Semantic Analysis (`memorykg semantic-analyze`)
8 phases: themes → entities → keywords → language metrics →
doc signatures → heading vocab → cohesion score → insights
Output: Markdown + JSON at `~/.claude/memorykg_semantic_latest.json`

---

## STORAGE LAYOUT

```
.memorykg/
├── graph.sqlite        ← Core Build: authoritative graph
├── lancedb/            ← Core Build: vector index
├── snapshots/          ← Temporal snapshots (JSON, keep in git)
├── cache/              ← Multipass: per-file NLP feature caches
├── pipeline/           ← Multipass: .psv runs + embeddings.json
└── models/             ← Cached embedding models
```

`.gitignore`: `**/.memorykg/` (or exclude heavy artifacts, keep `snapshots/`)

---

## CHOOSING A PIPELINE

| Goal | Pipeline | Command |
|------|----------|---------|
| MCP server / query / pack | Core Build | `memorykg build` |
| Deep NLP + diversity sampling | Multipass | `memorykg pipeline run` |
| Corpus embedding | Multipass | `memorykg pipeline embed` |
| Intrinsic dimensionality / MRL | Multipass | `memorykg pipeline manifold` |
| Structural health check | Analysis | `memorykg analyze` |
| Theme / entity / language audit | Analysis | `memorykg semantic-analyze` |

> Core Build is always required for MCP, query, and pack.
> Multipass is complementary — deeper corpus intelligence, not a replacement.
