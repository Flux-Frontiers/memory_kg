"""
cmd_semantic_analyze.py

Click subcommand for semantic MemoryKG corpus analysis:

  semantic-analyze  — topics, themes, entities, language measures, document signatures
"""

from __future__ import annotations

import click

from memory_kg.cli.group import cli
from memory_kg.cli.options import repo_option
from memory_kg.memorykg_semantic_analysis import main as run_semantic_analysis


@cli.command("semantic-analyze")
@repo_option
@click.option(
    "--db",
    default=None,
    type=click.Path(),
    help="SQLite knowledge graph path (default: <corpus>/.memorykg/graph.sqlite).",
)
@click.option(
    "--vectors",
    default=None,
    type=click.Path(),
    help="sqlite-vec store (default: <corpus>/.memorykg/vectors.sqlite).",
)
@click.option(
    "--output",
    "-o",
    default=None,
    type=click.Path(),
    help="Markdown report output path (default: <corpus>/analysis/memory_kg_semantic_<YYYYMMDD>.md).",
)
@click.option(
    "--json",
    "-j",
    "json_path",
    default=None,
    type=click.Path(),
    help="JSON output path (default: ~/.claude/memorykg_semantic_latest.json).",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Suppress the Rich console summary table.",
)
def semantic_analyze(
    repo: str,
    db: str | None,
    vectors: str | None,
    output: str | None,
    json_path: str | None,
    quiet: bool,
) -> None:
    """Semantic analysis: topics, themes, entities, language measures, document signatures."""
    run_semantic_analysis(
        corpus_root=repo,
        db_path=db,
        vectors_path=vectors,
        report_path=output,
        json_path=json_path,
        quiet=quiet,
    )
