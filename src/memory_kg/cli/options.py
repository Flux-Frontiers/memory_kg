"""
options.py

Shared Click options for MemoryKG CLI commands.
"""

from __future__ import annotations

import click

from memory_kg.memorykg import DEFAULT_MODEL

sqlite_option = click.option(
    "--sqlite",
    default=None,
    show_default=False,
    type=click.Path(),
    help="Path to SQLite database (default: <repo>/.memorykg/graph.sqlite).",
)

vectors_option = click.option(
    "--vectors",
    default=None,
    show_default=False,
    type=click.Path(),
    help="Path to the sqlite-vec store (default: <repo>/.memorykg/vectors.sqlite).",
)

model_option = click.option(
    "--model",
    default=DEFAULT_MODEL,
    show_default=True,
    help="Sentence-transformer model name.",
)

corpus_root_option = click.option(
    "--corpus-root",
    default=".",
    type=click.Path(exists=True, file_okay=False),
    show_default=True,
    help="Root directory of the document corpus.",
)

repo_option = click.option(
    "--repo",
    default=".",
    type=click.Path(exists=True, file_okay=False),
    show_default=True,
    help="Root directory of the document corpus.",
)
