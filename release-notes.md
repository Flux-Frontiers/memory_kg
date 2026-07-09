# Release Notes — v0.5.3

> Released: 2026-07-09

A maintenance release covering CI and packaging hygiene, and the first release archived to Zenodo now that the GitHub–Zenodo integration is enabled. There are no functional code changes since v0.5.2.

## What changed

**CI badge repaired.** The README status badge pointed at `publish.yml`, which was renamed to `release.yml` — so it 404'd and never rendered on GitHub. It now points at the real `ci.yml` workflow.

**Runner deprecation cleared.** Both workflows were bumped to `actions/checkout@v5` and `actions/setup-python@v6`, moving off the deprecated Node 20 runtime onto Node 24.

**Repository hygiene.** The `dist/` ignore (previously commented out) is now active, so built wheels and sdists — which the release workflow rebuilds and attaches to each GitHub Release — are no longer tracked in git.

## Upgrading

Nothing to do. No API, dependency, or behavioural changes since v0.5.2; reinstall only if you want the refreshed metadata.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
