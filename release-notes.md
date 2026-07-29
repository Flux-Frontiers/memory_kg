# Release Notes — v0.6.1

> Released: 2026-07-29

A dependency-correctness release. The headline is a hard upper bound on `mcp`: a clean
`pip install memory-kg` could resolve mcp 2.x, which crashed `memorykg-mcp` on import
before it registered a single tool. If your MCP server failed to start with a
`ModuleNotFoundError` on `mcp.server.fastmcp`, upgrading fixes it. Parallel embedding also
moves onto the shared, production-hardened implementation, closing a real OOM path on
Apple Silicon.

## What changed

**`mcp` pinned below 2.0.** mcp 2.0 split FastMCP out into a standalone `fastmcp` package
and removed the bundled `mcp.server.fastmcp` module. Because the MCP server imports
`FastMCP` at module scope, the previous unbounded `mcp>=1.0.0` let a fresh install pick up
2.x and fail immediately. Developers never saw it — a pinned lock file kept every local
checkout working, which is exactly how this reached the index in three sibling packages
before anyone noticed. The pin is now `mcp<2`, and it stays until the server is ported to
the standalone `fastmcp` package.

**Import-level tests so this can't recur silently.** A new `tests/test_mcp_server.py`
builds the real `FastMCP` instance and registers all four tools, so an incompatible `mcp`
release breaks CI at import time rather than in a user's terminal. One test asserts
`mcp.server.fastmcp` exists directly, so a future break names the incompatibility instead
of surfacing as an opaque `ImportError`.

**Parallel embedding consolidated onto `kg_utils.corpus_embedder`.** The local
`embedder_worker.py` was a stale pre-0.15.9 fork that never received the device-pinning and
GPU-guard fixes a production incident forced onto its sibling. Concretely it had no device
pinning at all and fanned out to `n_workers` processes for any corpus of 50+ texts — the
pattern that lets N workers each grab MPS and stack N GPU allocations into an OOM, reachable
by default since `--workers` defaults to `cpu_count/2`. The implementation now lives in
`kgmodule-utils>=0.8.0` with the GPU→single-process guard and shard recycling;
`memory_kg.embedder_worker` re-exports the public names, so no caller changes.

**A device flag for embedding, and a single version.** `memorykg pipeline embed` accepts
`--device {cpu,mps,cuda}` and prints an honest banner showing the resolved device and
whether the run is parallel-CPU or single-process GPU streaming. Separately, a vestigial
`src/__init__.py` carrying a *second*, stale `__version__` was removed — the 0.6.0 bump had
left it reading `0.5.3` — so the package version now has one source of truth.

## Upgrading

Upgrade in place; nothing to rebuild and no graph migration. If a previous install pulled
mcp 2.x and left `memorykg-mcp` broken, this release repairs it on install. Anyone importing
`CorpusEmbedder` or `EmbeddingCache` from `memory_kg.embedder_worker` can keep doing so —
the names re-export unchanged — and the new `kgmodule-utils>=0.8.0` floor defaults
`vector_backend` to `"auto"`, which keeps existing corpora on the backend they already use.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
