"""
main.py

MemoryKG CLI entry point.

Usage::

    memorykg build          [OPTIONS] [CORPUS_ROOT]
    memorykg build-graph    [OPTIONS] [CORPUS_ROOT]
    memorykg build-index    [OPTIONS] [CORPUS_ROOT]
    memorykg query          [OPTIONS] QUERY
    memorykg pack           [OPTIONS] QUERY
    memorykg analyze        [OPTIONS] [CORPUS_ROOT]
    memorykg download-model [OPTIONS]
    memorykg snapshot       [COMMAND]
    memorykg viz            [OPTIONS]

Author: Eric G. Suchanek, PhD
"""

from __future__ import annotations

# Side-effect imports: each module registers its subcommands against the shared
# `cli` group at import time. `cli` itself is re-exported as the entry point.
from memory_kg.cli import (  # noqa: F401
    cmd_analyze,
    cmd_build,
    cmd_hooks,
    cmd_mcp,
    cmd_model,
    cmd_pipeline,
    cmd_query,
    cmd_semantic_analyze,
    cmd_snapshot,
    cmd_viz,
)
from memory_kg.cli.group import cli

__all__ = ["cli"]
