"""
cmd_analyze.py

Click subcommand for running a thorough MemoryKG corpus analysis:

  analyze  — run MemoryKGAnalyzer, emit a Markdown report and JSON snapshot
"""

from __future__ import annotations

import click

from memory_kg.cli.group import cli
from memory_kg.cli.options import repo_option
from memory_kg.memorykg_thorough_analysis import main as run_analysis


@cli.command("analyze")
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
    help="Markdown report output path (default: <corpus>/analysis/memory_kg_analysis_<YYYYMMDD>.md).",
)
@click.option(
    "--json",
    "-j",
    "json_path",
    default=None,
    type=click.Path(),
    help="JSON snapshot output path (default: ~/.claude/memorykg_analysis_latest.json).",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Suppress the Rich console summary table.",
)
def analyze(
    repo: str,
    db: str | None,
    vectors: str | None,
    output: str | None,
    json_path: str | None,
    quiet: bool,
) -> None:
    """Run a thorough analysis of a document corpus graph."""
    run_analysis(
        corpus_root=repo,
        db_path=db,
        vectors_path=vectors,
        report_path=output,
        json_path=json_path,
        quiet=quiet,
    )
