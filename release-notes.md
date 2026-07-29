# Release Notes — v0.6.2

> Released: 2026-07-29

A small dependency-hygiene release. MemoryKG's floor for `kgmodule-utils` had drifted a
release behind what was published, so a fresh install could resolve an older shared core
than the one the package is developed and tested against. The floor now matches the
current release. There are no code changes and no behavioural difference.

## What changed

**`kgmodule-utils` floor lifted to `>=0.9.0`.** The floor sat at `0.8.0` while `0.9.0` was
the published release. Nothing was broken by that — the lock file already resolved higher
locally — but a consumer installing from the index could land on the older core, which is
precisely the class of drift that makes bug reports hard to reproduce. The lock has been
regenerated and the suite is green against 0.9.0 (269 passed).

**Housekeeping: `.gitignore` normalized across the KG fleet.** MemoryKG's ignore rules had
accumulated a `**/.memorykg/` pattern that swallowed its own `snapshots/` directory, so
every pre-commit run generated snapshots and then silently discarded them — none were ever
tracked. The ignore rules now follow one canonical form shared across all eleven KG repos:
databases, vector indexes and model caches are ignored, `snapshots/` never is. Recovering
the previously-dropped snapshot history is a separate, deliberate step.

## Upgrading

Nothing to do. `pip install --upgrade memory-kg` picks up the corrected floor; no rebuild,
no migration, no API change.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
