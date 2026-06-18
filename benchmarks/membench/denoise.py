"""denoise.py — re-export of the package query denoiser for benchmark scripts.

The canonical implementation now lives in :mod:`memory_kg.query_denoise` (shipped
as an opt-in ``MemoryKG.query(..., denoise=True)`` feature). This shim keeps
``measure_denoise.py`` and any existing references importing from the benchmark
directory working.
"""

from __future__ import annotations

from memory_kg.query_denoise import denoise_query

__all__ = ["denoise_query"]
