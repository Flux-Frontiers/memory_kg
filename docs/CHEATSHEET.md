# MemoryKG Query Cheatsheet

A practical reference for the five MCP tools, with examples drawn from document corpora.
All queries below work against a live MemoryKG knowledge graph built from `.md` and `.txt` files.

---

## The Five Tools at a Glance

| Tool | Best for | Returns |
|---|---|---|
| `stats()` | Orientation — size and shape of the corpus | JSON: node/edge counts by kind |
| `query(q)` | Structural exploration — *what exists, how topics relate* | JSON: ranked nodes + edges |
| `pack(q)` | Document text retrieval — *actual excerpts from files* | Markdown: chunks with file paths and line ranges |
| `get_node(node_id)` | Pinpoint lookup — one node by its stable ID | JSON: full node metadata |
| `neighbors(node_id)` | Walk the structure — the edges touching one node | JSON: edges + the nodes at their other ends |

---

## 1. Orient First with `stats`

Always start here when approaching an unfamiliar corpus or after a rebuild.

```python
stats()
```

Returns counts broken down by node kind and edge relation.
Example output:

```json
{
  "total_nodes": 1500,
  "total_edges": 2100,
  "node_counts": {
    "document": 12,
    "section": 48,
    "chunk": 850,
    "topic": 120,
    "entity": 200,
    "keyword": 270
  },
  "edge_counts": {
    "CONTAINS": 900,
    "NEXT": 450,
    "SIMILAR_TO": 350,
    "HAS_TOPIC": 200,
    "MENTIONS_ENTITY": 150,
    "HAS_KEYWORD": 50
  }
}
```

High chunk and symbol counts indicate a rich corpus. High `SIMILAR_TO` counts mean semantic clustering is active.

---

## 2. Semantic Exploration with `query`

Returns a ranked set of nodes and the edges between them. Good for mapping unknown territory.

### Find documents about a topic

```python
query("authentication and authorization")
```

Returns documents, sections, and chunks related to security topics — no need to know filenames.

### Trace topics across the corpus

```python
query("deployment pipeline CI/CD", rels=["HAS_TOPIC"])
```

`rels=` restricts graph expansion to a single edge type. Set it to `"HAS_TOPIC"` to follow topic classification edges only.

### Find mentions of specific entities

```python
query("PostgreSQL database", rels=["MENTIONS_ENTITY"])
```

Locates all chunks that mention specific tools, technologies, or entities.

### Find structurally related content

```python
query("error handling", rels=["CONTAINS", "NEXT"])
```

`CONTAINS` follows the document hierarchy (doc → section → chunk).
`NEXT` follows reading order (adjacent chunks).

### Find semantically similar chunks

```python
query("performance optimization", rels=["SIMILAR_TO"])
```

Returns chunks across the corpus that are semantically similar (cosine similarity ≥ 0.85).

### Increase graph depth

```python
query("API design patterns", hop=2)
```

`hop=2` follows edges two levels out from each seed. Useful when the entry point is one hop away from related content.

### Combine multiple relation types

```python
query("authentication", rels=["HAS_TOPIC", "MENTIONS_ENTITY", "SIMILAR_TO"])
```

Comma-separated `rels` expand through multiple relation types simultaneously.

---

## 3. Document Text Retrieval with `pack`

Returns Markdown with actual document excerpts, ranked and deduplicated. Use this when you need to *read* the content, not just locate it.

### Understand documentation about a feature

```python
pack("user authentication flow")
```

Returns relevant document chunks with file paths and context.

### Get excerpts for a specific concept

```python
pack("deployment steps installation", max_nodes=5)
```

`max_nodes` limits the number of chunks returned — useful when you only need the top results.

### Widen the text window

```python
pack("API endpoint documentation", max_chars=3000)
```

`max_chars=` controls the total character limit for all returned chunks. Default is 2000.

### Increase semantic seeds

```python
pack("configuration management environment variables", k=12)
```

`k=` is the number of semantic seed nodes before graph expansion. Raise it when the first results feel off-target.

### Find related content across files

```python
pack("monitoring and observability", rels=["SIMILAR_TO", "HAS_TOPIC"])
```

Returns chunks related by semantic similarity or topic classification across the entire corpus.

---

## 4. Pinpoint Lookup with `get_node`

Fetch a single node by its stable ID. Node IDs appear in `query` and `pack` results.

### Node ID format

```
<kind>:<path_or_slug>

document:docs/authentication.md
section:docs/authentication.md:oauth2-flow
chunk:docs/authentication.md:0042
topic:authentication
entity:oauth2
keyword:jwt-token
```

### Fetch a document

```python
get_node("doc:docs/api-reference.md")
```

Returns file path, sections, full text content.

### Fetch a section

```python
get_node("sec:docs/api-reference.md:rest-endpoints")
```

### Fetch a chunk

```python
get_node("chunk:docs/api-reference.md:0015")
```

Returns raw text, semantic score, adjacent chunks.

### Fetch a topic or entity

```python
get_node("topic:authentication")
get_node("entity:postgresql")
```

---

## 5. Node & Edge Reference

### Node Kinds

| Kind | ID prefix | Description |
|---|---|---|
| `document` | `document:<file>` | Top-level document (one per `.md` or `.txt` file) |
| `section` | `section:<file>:<slug>` | Markdown heading block or text division |
| `chunk` | `chunk:<file>:<index>` | Text fragment (≈512 chars, overlapping) |
| `topic` | `topic:<slug>` | Inferred topic category (e.g., `topic:api`) |
| `entity` | `entity:<slug>` | Named entity extracted from text |
| `keyword` | `keyword:<slug>` | Significant keyword or phrase |

### Edge Types

| Relation | Direction | Meaning |
|---|---|---|
| `CONTAINS` | document → section → chunk | Structural hierarchy |
| `NEXT` | chunk → chunk | Sequential adjacency (reading order) |
| `SIMILAR_TO` | chunk → chunk | High semantic similarity (≥0.85) |
| `HAS_TOPIC` | chunk → topic | Topic classification |
| `MENTIONS_ENTITY` | chunk → entity | Named entity mention |
| `HAS_KEYWORD` | chunk → keyword | Keyword occurrence |
| `REFERENCES` | chunk → document | Cross-document link |
| `CO_OCCURS_WITH` | topic/entity/keyword → topic/entity/keyword | Co-occurrence in chunk |

---

## 6. Common Query Patterns

### "What does this corpus say about X?"

```python
pack("X concept or topic")
```

### "Find all documents about topic T"

```python
query("T", rels=["HAS_TOPIC"])
```

### "What chunks mention entity E?"

```python
pack("E name or technology")
# or
query("E", rels=["MENTIONS_ENTITY"])
```

### "Find chunks similar to this one"

```python
query("concept", rels=["SIMILAR_TO"])
```

### "Show the structure of a document"

```python
query("document name", rels=["CONTAINS"], hop=2)
```

### "Find cross-references between documents"

```python
query("topic", rels=["REFERENCES"])
```

### "Get adjacent context around a chunk"

```python
query("chunk text", rels=["CONTAINS", "NEXT"])
```

---

## 7. Parameter Quick Reference

### `query` and `pack` shared params

| Parameter | Default | Effect |
|---|---|---|
| `q` | *(required)* | Natural-language query |
| `k` | `8` | Semantic seed nodes before expansion |
| `hop` | `1` | Graph expansion hops from each seed |
| `rels` | All edge types | Edge types to traverse |
| `max_nodes` | `25` / `15` | Cap returned nodes |

### `pack` only

| Parameter | Default | Effect |
|---|---|---|
| `max_chars` | `2000` | Longest excerpt, in characters |

### `neighbors`

| Parameter | Default | Effect |
|---|---|---|
| `node_id` | *(required)* | The node to start from |
| `rels` | All edge types | Edge types to keep |
| `direction` | `"both"` | `"out"`, `"in"` or `"both"` |
| `limit` | `50` | Most edges (1-500), ordered by relation, source, target |

---

## 8. Excluding Directories from Indexing

By default, MemoryKG indexes all `.md` and `.txt` files and skips common directories (`.git`, `.venv`, `__pycache__`, etc.).

**Why exclude?** Archive directories, drafts, and vendored docs pollute the graph with irrelevant nodes.

**Configuration (`pyproject.toml`, persistent — recommended):**

```toml
[tool.memorykg]
exclude = ["archive", "vendor", "drafts"]
```

**CLI flags (per-command override):**

```bash
memorykg build docs --exclude-dir archive --exclude-dir vendor
```

Both options are additive — CLI flags extend `pyproject.toml` excludes.

---

## 9. Multipass Analysis Pipeline

MemoryKG also includes a diary_kg-style multipass pipeline for deep NLP analysis. This is complementary to the core build and MCP tools.

### Pipeline Commands

```bash
# 5-phase analysis: sampling → chunking → classification → memory → output
memorykg pipeline run --repo docs --batch 20

# Multi-process corpus embedding (nomic-embed-text-v1, 768-d)
memorykg pipeline embed --repo docs --workers 4

# Manifold analysis (PCA, TwoNN, MRL truncation quality)
memorykg pipeline manifold
```

### Key Differences from Core Build

| Aspect | Core Build (`memorykg build`) | Pipeline (`memorykg pipeline run`) |
|---|---|---|
| Purpose | Searchable graph for MCP/CLI | Deep NLP analysis with provenance |
| Embedding model | `BAAI/bge-small-en-v1.5` | `nomic-ai/nomic-embed-text-v1` |
| Chunking | Semantic (embedding-based) | Sentence-group (4 sentences) |
| Topic classification | Supervised only | Hybrid: supervised + unsupervised K-means |
| Sampling | All files | Diversity sampling (K-means on features) |
| Output | SQLite + sqlite-vec | Pipe-delimited `.psv` + JSON embedding cache |

### Pipeline Output

```
# .memorykg/pipeline/PipelineRun_<id>_<ts>.psv
pchunk:docs/auth.md:3f8a2b1c | authentication | 0.44 | supervised | oauth,token | The OAuth2 flow...
```

See `docs/ingestion.md` for the full ingestion architecture.

---

## 10. This Corpus Live Stats

```
Nodes: 1,500   (document: 12 · section: 48 · chunk: 850 · topic: 120 · entity: 200 · keyword: 270)
Edges: 2,100   (CONTAINS: 900 · NEXT: 450 · SIMILAR_TO: 350 · HAS_TOPIC: 200 · MENTIONS_ENTITY: 150 · HAS_KEYWORD: 50)
DB:    .memorykg/graph.sqlite
Model: BAAI/bge-small-en-v1.5 (core build) · nomic-ai/nomic-embed-text-v1 (pipeline)
```

*Rebuild after significant content changes: `memorykg build docs`*
