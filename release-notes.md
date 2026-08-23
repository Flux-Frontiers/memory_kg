# Release Notes — v0.8.0

> Released: 2026-08-23

This release trims MemoryKG's packaging surface and fixes three bugs that shipped
in 0.7.0 and later: two in the pre-commit hook template `install-hooks` installs
into consuming repos, and one in the Streamlit demo app.

## What changed

**Dev tooling is no longer pip-installable.** The `dev` extra becomes an optional
Poetry group, joining the `kg` group already there — install it with
`poetry install --with dev` rather than `pip install memory-kg[dev]`. The `all`
aggregate extra is removed for the same reason: beside the three viz packages it
re-listed every dev tool by name, so the wheel advertised them as installable
regardless of where the dependencies actually lived. This is a **breaking** change
for anyone installing either extra.

**Dependency floors move up.** `kgmodule-utils` rises from 0.12.1 to 0.18.0 and
`doc-kg` to 0.22.0, both direct dependencies; `pycode-kg` rises to 0.23.1 in the
`kg` group.

**The installed pre-commit hook had two bugs.** `MEMORYKG_SKIP_SNAPSHOT` was meant
to skip only the per-commit snapshot step, but it sat above the quality-check
invocation and silently skipped ruff, ty, and pytest along with it — now it gates
only the snapshot, and the snapshot itself is opt-in via `MEMORYKG_SNAPSHOT=1`
(default off). Separately, hook entries called tools through `poetry run`, which
resolves against whichever environment the calling shell advertises; an inherited
`VIRTUAL_ENV` from a different repo could silently redirect a hook to the wrong
tool. Entries now call `.venv/bin/<tool>` directly.

**A Streamlit import relied on load order.** `app.py` called
`st.components.v1.html()` after only `import streamlit as st` — importing a
package doesn't bind its submodules, so this worked only because something else
in the import graph happened to pull `streamlit.components` in first. The import
is now explicit.

## Upgrading

If you install this package with `[dev]` or `[all]`, switch to
`poetry install --with dev`. Everything else in this release is additive or
internal; no other action is needed.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
