# Release Notes — v0.7.0

> Released: 2026-08-02

MemoryKG's vector store moves from LanceDB to sqlite-vec. A knowledge graph is now two
files instead of a file and a directory tree — `.memorykg/graph.sqlite` alongside
`.memorykg/vectors.sqlite` — and `lancedb` leaves the dependency tree entirely, taking
`pyarrow` and the `lance-namespace` packages with it. This is a **breaking** change: the
constructor parameters and the CLI flag are renamed with no fallback, and existing vector
stores must be rebuilt. Retrieval quality is unchanged, and this release carries the
evidence for that claim across four public benchmarks.

## What changed

**The vector store is a file now.** `MemoryKG(lancedb_dir=…)` becomes
`MemoryKG(vectors_path=…)`, `SemanticIndex` loses its LanceDB-only `table` parameter, and
`--lancedb PATH` becomes `--vectors PATH` on every command that took it. Raw `_distance`
values roughly halve, because the old LanceDB table was created without an explicit metric
and silently defaulted to squared L2 where sqlite-vec uses cosine. Ranking is unaffected —
on normalised embeddings the two are a monotonic transform of one another, and nothing in
the codebase derives a score from the distance.

**Parity is measured, not asserted.** All four benchmark suites were re-run on the new
backend and diffed per item against the LanceDB-era results. LongMemEval reproduces
identically across all 500 questions, including the provenance chunk behind each retrieved
session. LoCoMo reproduces avg recall 0.981 across 1,986 questions. ConvoMem holds at 0.963
tier-1 recall over 1,897 items, and MemBench at 87.7% over 1,100 items, with every
per-category figure intact. The MemBench graph rebuilt on sqlite-vec matches the old build
node for node and edge for edge.

**Retrieval is now reproducible across processes.** Chasing the handful of rows that did
differ in those parity runs turned up a bug that predated the migration by four months:
graph expansion iterated a `set`, so when several seeds reached the same node, which one
claimed it depended on Python's per-process string hash randomisation. That choice feeds
the ranking key, so the result tail reordered between runs and a different node fell off
the `max_nodes` cut. Two runs of identical code against an identical index could differ on
4 of 1,100 benchmark items while average recall moved by 0.001 — invisible in aggregate,
and enough to make backend parity unfalsifiable. Expansion now traverses in sorted order.

**The benchmark runners work again.** The rename broke all five of them, and nothing
caught it: they are not imported by the package and no test touched them. They are fixed
and now pinned by static guards that run in milliseconds without a corpus, a model, or a
network. Release metadata gained similar guards, after the version bump left several
declaration sites still reading the old number.

## Upgrading

Delete the old vector store and rebuild — there is no conversion step, since vectors are
derived data:

```bash
rm -rf .memorykg/lancedb
memorykg build-index --repo <corpus>
```

Then update any code passing `lancedb_dir=` to `vectors_path=`, and any scripts passing
`--lancedb` to `--vectors`. The environment variable is `MEMORYKG_VECTORS`. Note that
`vectors_path` names a **file**: code that did `mkdir -p` on the old directory path will
create a directory where the database belongs, and `sqlite3.connect` then fails.

Nothing needs re-tuning. Distances changed scale but not order, so thresholds derived from
ranks are unaffected; if you persisted raw `_distance` values, they are no longer
comparable to ones recorded before this release.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
