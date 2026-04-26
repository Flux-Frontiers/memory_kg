# MemoryKG Python API

The `MemoryKG` class is the primary programmatic entry point. It wraps the
build pipeline, hybrid query engine, and passage packer in a single object.

```python
from memory_kg import MemoryKG

kg = MemoryKG(corpus_root="docs/", chunk_strategy="heading")
kg.build(wipe=True)
```

## Hybrid query

```python
result = kg.query("deployment configuration", k=8, hop=1)
for node in result.nodes:
    print(node["id"], node["name"])
```

`k` is the seed count (top-K vector matches); `hop` is the graph-expansion
depth applied to each seed.

## Haystack-scoped query (benchmark mode)

When the benchmark or application defines a per-question candidate pool,
restrict vector seeding to that pool with `haystack_files`:

```python
result = kg.query(
    "Dr. Chen's recommendation",
    k=50,
    hop=1,
    haystack_files=["session_2024_01_12.md", "session_2024_01_19.md"],
)
```

This is the +11 pp fix that closed the gap to the inference-based
LongMemEval leaderboard.

## Passage pack for LLM context

```python
pack = kg.pack("authentication flow")
pack.save("context.md")
```

The pack is source-grounded Markdown — headings preserved, ready to paste
into an LLM prompt.

## See also

- [docs/cli-reference.md](cli-reference.md) — equivalent CLI flags
- [docs/ingestion.md](ingestion.md) — pipeline architecture and schema
- [docs/MCP.md](MCP.md) — MCP server for AI agents
