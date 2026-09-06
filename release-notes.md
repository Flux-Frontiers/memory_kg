# Release Notes — v0.10.0

> Released: 2026-09-06

MemoryKG's snapshot support is rebuilt on the fleet's shared model, closing
the class of bug that shipped in 0.8.0 and was caught here before release.

## What changed

**The `Snapshot` subclass is gone.** MemoryKG used to subclass the shared
`kg_utils.snapshots.Snapshot` to expose `metrics`, `vs_previous`, and
`vs_baseline` as typed properties instead of plain dicts. That forced a
hand-written copy of nine manager methods — `capture`, `save_snapshot`,
`load_snapshot`, `get_previous`, `get_baseline`, `diff_snapshots`,
`_compute_delta`, `to_dict`, and `from_dict` — and one of those copies is
the exact shape of bug that shipped in doc-kg 0.24.0 and pycode-kg 0.25.0
this week, dropping the snapshot key and provenance fields. MemoryKG's own
copy was caught and fixed in 0.9.0 before it ever shipped a bad key.
Removing the subclass entirely, rather than patching the one copy, removes
the whole class of bug instead of the one instance of it.

A snapshot's `metrics`, `vs_previous`, and `vs_baseline` are now plain
dicts. `SnapshotMetrics` and `SnapshotDelta` remain available as converters
for code that wants attribute access. Snapshot files, manifests, and CLI
output are unchanged.

**The `kgmodule-utils` 0.19.1 delta-backfill fix now reaches MemoryKG.**
Loading a saved snapshot previously reported domain delta fields as
absent, even though listing and diffing snapshots computed them correctly
for the same pair — the exact read path `snapshot show` uses was the one
giving the wrong answer. With the floor resolving to 0.19.1, `snapshot
show` now reports the same numbers as every other view of a snapshot.

## Upgrading

No action required for normal use — snapshot files, the CLI, and MCP
tools are unchanged. If your code accessed `Snapshot.metrics` as an object
with attributes (`snap.metrics.total_nodes`), switch to dict access
(`snap.metrics["total_nodes"]`) or call `metrics_from_dict(snap.metrics)`
for the old style with attribute access.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
