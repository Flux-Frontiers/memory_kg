# Release Notes -- v0.13.1

> Released: 2026-11-09

A bugfix release. Rebuilding with `wipe` over a graph made before the
`metadata` column no longer crashes, and the dependency lock moves to the
latest releases. The benchmark harnesses also gained the scoring options used
in the latest comparison with MemPalace.

## What changed

**`wipe` replaces an older database.** `GraphStore.clear()` used to delete
rows and keep the tables, so a wipe rebuild over an older `graph.sqlite` kept
the old `nodes` table, and every insert failed with "table nodes has no column
named metadata". It now drops the tables and recreates them from the current
schema.

**Benchmarks.** ConvoMem and MemBench take `--score-top N`, which scores only
the top N ranked nodes, the cutoff MemPalace uses. ConvoMem's `--semantic`
builds topic, entity and keyword nodes. The LongMemEval temporal rerank now
reads LongMemEval's date format, so it actually runs; the 0.13.0 re-run gives
R@1 90.4%, R@5 98.2% and R@10 99.2%, unchanged from August.

**Dependencies.** The lock moves to the latest releases, including
kgmodule-utils 0.30.0, torch 2.15.0, transformers 5.22.2 and
sentence-transformers 6.2.0. Minimum versions are unchanged.

## Upgrading

`pip install -U memory-kg`. No rebuild is needed. If a `wipe` rebuild failed
on an older graph, run it again.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
