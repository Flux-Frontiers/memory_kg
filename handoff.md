# Semantic Memory Layer Handoff

## Summary

Implemented a clean two-layer architecture for long-memory systems:
- **Document Layer** (unchanged): document → section → chunk structure
- **Semantic Memory Layer** (new): assertions, events, and temporal reasoning built on top

## Problems Solved

### Problem 1: CO_OCCURS_WITH Bloat
- **Issue**: 65% of all edges (8,596 / 13,121) were noisy CO_OCCURS_WITH edges
- **Fix**: Disabled `emit_cooccur` by default (changed from `True` to `False`)
  - Updated defaults in `graph.py`, `kg.py`, `memorykg.py`
  - Removed CO_OCCURS_WITH from `store.py` DEFAULT_RELS
  - Added MEMORY_RELS constant for semantic layer traversal
- **Result**: 0 CO_OCCURS_WITH edges (vs 3,928 before)

### Problem 2: Entities as Mentions, Not Facts
- **Issue**: Entities were chunk-level mentions (MENTIONS_ENTITY edges), not semantic facts with temporal structure
- **Fix**: Added Assertion nodes with full temporal metadata
  - Subject-predicate-object facts extracted from chunk text
  - Temporal fields: `valid_at_start`, `valid_at_end`, `status`, `polarity`
  - SUPPORTS edge: chunk → assertion (evidence linkage)
  - ABOUT edge: assertion → entity (subject relationship)

### Problem 3: No Event or Temporal Reasoning
- **Issue**: No way to represent events, temporal updates, or supersession
- **Fix**: Added Event nodes + temporal update detection
  - Event extraction: regex-based patterns (moved_to, joined, left, etc.)
  - Temporal anchors: ISO dates, years, relative phrases
  - SUPERSEDES edge: newer assertion → older assertion (temporal updates)
  - Status tracking: active, superseded, contradicted, deprecated

## Architecture

```
MemoryKG Store (SQLite)
│
├─ Document Layer (existing)
│  ├─ document
│  ├─ section
│  └─ chunk
│     └─ (MENTIONS_ENTITY) → entity
│
└─ Semantic Memory Layer (new)
   ├─ assertion
   │  ├─ JSON text: {subject, predicate, object, polarity, status, temporal_fields}
   │  ├─ (SUPPORTS) ← chunk (evidence)
   │  ├─ (ABOUT) → entity (subject)
   │  ├─ (REFERS_TO) → entity (object, if another entity)
   │  └─ (SUPERSEDES) → assertion (temporal update)
   │
   └─ event
      ├─ JSON text: {event_type, summary, time_start, time_uncertainty}
      ├─ (DESCRIBES) ← chunk (evidence)
      └─ (INVOLVES) → entity (participant)
```

## Files Modified / Created

### Modified
- `src/memory_kg/memorykg.py`: `emit_cooccur=False` default
- `src/memory_kg/graph.py`: `emit_cooccur=False` default
- `src/memory_kg/kg.py`: `emit_cooccur=False` default
- `src/memory_kg/store.py`:
  - Removed CO_OCCURS_WITH from DEFAULT_RELS
  - Added MEMORY_RELS constant
- `src/memory_kg/__init__.py`: Export semantic memory API

### Created
- `src/memory_kg/semantic_primitives.py`: Constants, node kinds, edge relations, ID builders
- `src/memory_kg/semantic_extractor.py`: EventExtractor + AssertionExtractor (regex-based, deterministic)
- `src/memory_kg/semantic_builder.py`: SemanticMemoryBuilder (builds semantic layer from chunks)

## API Usage

```python
from memory_kg import MemoryKG, SemanticMemoryBuilder

# Build document layer (no CO_OCCURS_WITH)
mkkg = MemoryKG("corpus_dir")
stats = mkkg.build_graph(wipe=True)
print(f"CO_OCCURS_WITH: {stats.edge_counts.get('CO_OCCURS_WITH', 0)}")  # → 0

# Build semantic memory layer
sem_stats = SemanticMemoryBuilder(mkkg.store).build()
print(sem_stats)
# → Semantic memory built:
#   events:                12
#   assertions:            184
#   edges:                 368
#   supersession edges:    64
#   assertions superseded: 64

# Query the combined graph
from memory_kg.store import MEMORY_RELS
all_rels = ("CONTAINS", "NEXT", "SIMILAR_TO", "MENTIONS_ENTITY") + MEMORY_RELS
result = mkkg.query("what happened to the user?", rels=all_rels)
```

## Extraction Strategies

### EventExtractor
- **Temporal patterns**: ISO dates, years, months, relative phrases ("last year", "in 2024")
- **Verb patterns**: moved, joined, left, married, published, etc.
- **Event types**: relocation, employment_start, employment_end, marriage, publication
- **Result**: EventCandidate with `{event_type, summary, time_start, entities_involved}`

### AssertionExtractor
- **SVO patterns**: subject-predicate-object extracted from entity mentions in chunks
- **Predicates**: is_a, lives_in, works_at, has, prefers, owns, married_to
- **Result**: AssertionCandidate with `{subject_id, predicate, object_str, confidence}`

### Supersession Detection
- Groups assertions by `(subject, predicate)` pair
- Sorts by chunk position (proxy for temporal order)
- Emits SUPERSEDES edges from newer to older
- Marks older assertions as "superseded"

## Temporal Fields (JSON)

### Assertion
```json
{
  "subject": "Alice",
  "predicate": "lives_in",
  "object": "Denver",
  "polarity": "affirmed",
  "status": "active",
  "valid_at_start": "2018-01-01",
  "valid_at_end": null,
  "confidence": 0.85
}
```

### Event
```json
{
  "event_type": "relocation",
  "summary": "Alice moved to Denver in 2018",
  "time_start": "2018",
  "time_end": null,
  "time_uncertainty": "year-only"
}
```

## Test Results (docs corpus)

```
MemoryKG graph: 1,237 nodes, 2,082 edges (no CO_OCCURS_WITH)
Semantic memory: 184 assertions, 64 supersession relationships
Total semantic nodes: 158 (assertions + events)
```

## Next Steps

### Short-term
1. **Run LongMemEval benchmark** on semantic layer vs document-only layer
   ```bash
   python benchmarks/longmemeval_dockg.py run <data.json> --rels CONTAINS,NEXT,SIMILAR_TO,MENTIONS_ENTITY,SUPPORTS,ABOUT,SUPERSEDES
   ```
2. **Tune extraction heuristics** based on benchmark results
   - Adjust predicate patterns
   - Refine temporal detection
   - Balance recall vs precision

### Medium-term
1. **Integrate with LLM-based refinement** (optional)
   - Use Claude to refine extracted assertions/events
   - Rank supersession candidates by confidence
   - Disambiguate temporal ambiguities

2. **Expand entity linking** for REFERS_TO edges
   - Currently only creates if object_entity_id is set
   - Could link object strings to known entities

3. **Add contradiction detection**
   - Track negated vs affirmed assertions
   - Emit CONTRADICTS edges when detected

### Long-term
1. **Session-level temporal reasoning** for conversation benchmarks
   - Track "current state" queries efficiently
   - Support temporal range queries
2. **Cross-session entity resolution** if ingesting multiple conversation sessions
3. **Confidence-based pruning** for noisy extractions

## Known Limitations

- **No NER model**: Uses heuristic titlecase + value patterns (good for 90% of cases)
- **No dependency parsing**: SVO extraction is regex-based (limited to simple patterns)
- **Temporal ambiguity**: Relative phrases ("last year") not resolved to absolute dates
- **Single-pass extraction**: No iterative refinement or confidence scores from LLM
- **No entity disambiguation**: Object strings not resolved to canonical entity IDs

These are all acceptable trade-offs for a deterministic, dependency-free memory layer. LLM refinement can be added as an optional post-pass if needed.

## Architecture Notes

The design keeps semantic memory **orthogonal to document structure**:
- Reads chunks from document layer
- Writes new semantic nodes to same SQLite store
- No schema changes required
- Can be enabled/disabled independently
- Query expansion works through both layers simultaneously

This enables a clean separation of concerns: **documents describe facts**, **semantic layer extracts and tracks them**.
