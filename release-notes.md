# Release Notes — v0.6.0

> Released: 2026-07-09

This release makes Phase 2 embedding **memory-bounded**. A large-corpus build that previously peaked at **25–32 GB and stalled on MPS around 230k rows** now completes with a **flat ~4 GB** footprint — same wall-clock, identical retrieval recall. If you have ever watched a big ingest balloon memory or hang mid-embed, this is the fix.

## What changed

**The memory fix.** Transformer attention memory scales with `batch × seq²`, and the encode batch defaulted to 1024 — so a single `model.encode` call on long chunks allocated 7–9 GB. Right-sizing the encode batch to **128** (throughput is flat above ~128 on both CPU and MPS, so this costs nothing) cuts peak RAM ~7×. Nodes are now **streamed** from SQLite rather than materialised in RAM, and SIMILAR_TO discovery uses a pre-allocated contiguous matrix instead of a Python list-of-lists.

**Leaner, faster build loop.** The embed path is now a straight stream — page → encode → buffer → write. A batch of GPU-oriented "drift" mitigations (adaptive/fixed embedder refresh, batch-shrink, per-window cache clearing) has been removed; they were compensating for the oversized batch and, on MPS, actively dragged throughput down by reloading the model every window.

**Shared embedder + one device knob.** The embedder is consolidated onto `kg_utils.embedder` (single source of truth for model loading and device handling), and device selection is unified on `KG_EMBED_DEVICE` (`DOCKG_DEVICE` is retired). Requires `kgmodule-utils>=0.4.6`, which carries the same 128 default so the dependency can't regress the fix.

**Search recall preserved.** `search()` remains an exact flat cosine scan — recall stays exact, which the benchmark suites depend on. Verified on LongMemEval: recall@30 1.000 / @10 0.992, unchanged.

## Upgrading

No action required for existing graphs — the index is derived and can be rebuilt at any time. Rebuilds will simply use less memory. On Apple Silicon, embedding auto-selects MPS (~9× faster than CPU); pin the device with `KG_EMBED_DEVICE=cpu|mps|cuda` if you need to. If you were setting `DOCKG_DEVICE`, switch to `KG_EMBED_DEVICE`.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
