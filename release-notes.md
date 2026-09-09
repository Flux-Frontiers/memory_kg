# Release Notes — v0.11.0

> Released: 2026-09-08

MemoryKG's snapshot manager now configures the shared `kgmodule-utils` base
through its extension points instead of overriding its methods, and the
dependency floors move to the releases that make that possible.

## What changed

**The remaining snapshot overrides are gone.** After 0.10.0 removed the
`Snapshot` subclass, `SnapshotManager` still carried its own `__init__`,
`capture` and `diff_snapshots`. Each existed to do one thing the shared base
could not express: name the package, derive `meaningful_nodes` and declare
the MemoryKG metric defaults, and add a timestamp to each side of a diff.
`kgmodule-utils` 0.20.0 added a `package_name` class attribute and a
`_domain_metrics()` hook for exactly the first two, and its `diff_snapshots`
already includes the timestamp. So the three overrides are deleted, and
`snapshots.py` drops from 494 lines to 229. Only
`_compute_delta_from_metrics` remains, because coverage and issue deltas are
genuinely MemoryKG-specific. Seven new tests pin the behaviour the deleted
code used to provide. Snapshot files, manifests, the CLI and the MCP tools
are unchanged.

**`kgmodule-utils` 0.20.0 is a hard requirement.** The extension points this
release relies on do not exist in 0.19.x. Installed against an older SDK the
manager silently reports itself as `kg-utils` and drops `meaningful_nodes`
from every snapshot, so the floor is raised rather than left as a preference.

**The `kg` tooling group catches up.** The optional group that installs the
`dockg` and `pycodekg` CLIs this repo uses to index itself was pinned four
and five releases behind, the most stale pair in the fleet. It now requires
`doc-kg` 0.26.0 and `pycode-kg` 0.27.0, the releases that made the same move
onto the shared SDK, so `poetry install --with kg` cannot resolve a tool that
predates the extension points into the same environment.

## Upgrading

Run `poetry lock` (or `pip install -U memory-kg`) so `kgmodule-utils`
resolves to 0.20.0 or later; nothing else changes for normal use. Code that
subclassed `SnapshotManager` and relied on the deleted `capture` or
`diff_snapshots` overrides should move to the `_domain_metrics()` hook.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
