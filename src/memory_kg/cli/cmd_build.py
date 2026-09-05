"""
cmd_build.py

Click subcommands for building the MemoryKG:

    build       — full pipeline: parse corpus → SQLite → vectors + SIMILAR_TO edges
    build-graph — parse corpus → SQLite only
    build-index — SQLite → vectors + optional SIMILAR_TO edges

Two-phase build (embedding paid once, reusable across index rebuilds):

    build-embeddings       — SQLite → JSONL embedding cache only
    build-index-from-cache — JSONL embedding cache → vectors (no model inference)
    build-two-phase        — SQLite → cache → vectors, end to end

Author: Eric G. Suchanek, PhD
"""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.rule import Rule

from memory_kg.cli.group import cli
from memory_kg.cli.options import (
    model_option,
    repo_option,
    sqlite_option,
    vectors_option,
)
from memory_kg.config import load_exclude_dirs
from memory_kg.kg import MemoryKG

_console = Console()


@cli.command("build")
@repo_option
@sqlite_option
@vectors_option
@model_option
@click.option(
    "--chunk-size",
    type=int,
    default=512,
    show_default=True,
    help="Approximate max characters per chunk.",
)
@click.option(
    "--chunk-overlap",
    type=int,
    default=64,
    show_default=True,
    help="Character overlap between consecutive chunks.",
)
@click.option(
    "--similarity-threshold",
    type=float,
    default=0.75,
    show_default=True,
    help="Cosine similarity threshold for semantic split detection.",
)
@click.option(
    "--enable-topics/--no-topics",
    default=True,
    show_default=True,
    help="Enable chunk->topic extraction and HAS_TOPIC edges.",
)
@click.option(
    "--enable-entities/--no-entities",
    default=True,
    show_default=True,
    help="Enable chunk->entity extraction and MENTIONS_ENTITY edges.",
)
@click.option(
    "--enable-keywords/--no-keywords",
    default=True,
    show_default=True,
    help="Enable chunk->keyword extraction and HAS_KEYWORD edges.",
)
@click.option(
    "--emit-cooccur/--no-cooccur",
    default=True,
    show_default=True,
    help="Emit CO_OCCURS_WITH edges among semantic nodes in each chunk.",
)
@click.option(
    "--cooccur-window",
    type=int,
    default=1,
    show_default=True,
    help="Co-occurrence window metadata for emitted CO_OCCURS_WITH edges.",
)
@click.option(
    "--topic-threshold",
    type=float,
    default=0.2,
    show_default=True,
    help="Topic confidence threshold in [0, 1].",
)
@click.option(
    "--topics-file",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Optional JSON/YAML topic catalog file.",
)
@click.option(
    "--no-similar",
    is_flag=True,
    default=False,
    help="Skip SIMILAR_TO edge discovery after indexing.",
)
@click.option(
    "--batch",
    type=int,
    default=256,
    show_default=True,
    help="Embedding batch size.",
)
@click.option(
    "--workers",
    type=int,
    default=8,
    show_default=True,
    help="Number of parallel embedding workers (>1 uses multi-process CorpusEmbedder).",
)
@click.option(
    "--update",
    is_flag=True,
    default=False,
    help="Incremental update — keep existing data instead of wiping.",
)
@click.option(
    "--ext",
    multiple=True,
    default=(".md", ".txt"),
    show_default=True,
    help="File extensions to include (repeatable).",
)
@click.option(
    "--exclude-dir",
    multiple=True,
    metavar="DIR",
    help=(
        "Directory name to exclude at every depth during the file walk (repeatable). "
        "Merged with [tool.memorykg].exclude from pyproject.toml."
    ),
)
def build(
    repo: str,
    sqlite: str,
    vectors: str,
    model: str,
    chunk_size: int,
    chunk_overlap: int,
    similarity_threshold: float,
    enable_topics: bool,
    enable_entities: bool,
    enable_keywords: bool,
    emit_cooccur: bool,
    cooccur_window: int,
    topic_threshold: float,
    topics_file: str | None,
    no_similar: bool,
    batch: int,
    workers: int,
    update: bool,
    ext: tuple[str, ...],
    exclude_dir: tuple[str, ...],
) -> None:
    """Build the MemoryKG from a corpus directory.

    Parses all .md and .txt files under CORPUS_ROOT, builds the structural
    and semantic graph, persists it to SQLite, and indexes it in sqlite-vec.
    Also discovers SIMILAR_TO edges between semantically related chunks.
    """
    repo_root = Path(repo).resolve()
    db_path = Path(sqlite) if sqlite else repo_root / ".memorykg" / "graph.sqlite"
    vectors_path = Path(vectors) if vectors else repo_root / ".memorykg" / "vectors.sqlite"
    wipe = not update
    extensions = {e if e.startswith(".") else f".{e}" for e in ext}
    exclude = load_exclude_dirs(repo_root) | set(exclude_dir)

    kg = MemoryKG(
        corpus_root=repo_root,
        exclude=exclude or None,
        db_path=db_path,
        vectors_path=vectors_path,
        model=model,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        similarity_threshold=similarity_threshold,
        enable_topics=enable_topics,
        enable_entities=enable_entities,
        enable_keywords=enable_keywords,
        emit_cooccur=emit_cooccur,
        cooccur_window=cooccur_window,
        topic_threshold=topic_threshold,
        topics_file=topics_file,
        n_workers=workers,
    )

    # Override graph extensions if provided
    if extensions:
        kg.graph.extensions = extensions

    features = (
        "  ".join(
            f
            for f, on in [
                ("topics", enable_topics),
                ("entities", enable_entities),
                ("keywords", enable_keywords),
            ]
            if on
        )
        or "(none)"
    )

    _console.print(Rule(f"MemoryKG build — {repo_root.name}", style="bold blue"))
    _console.print(f"  corpus   : {repo_root}")
    _console.print(f"  model    : {model}")
    _console.print(f"  batch    : {batch}")
    _console.print(f"  sqlite   : {db_path}")
    _console.print(f"  vectors  : {vectors_path}")
    _console.print(f"  ext      : {', '.join(sorted(extensions))}")
    _console.print(f"  exclude  : {', '.join(sorted(exclude)) if exclude else '(none)'}")
    _console.print(f"  features : {features}")

    # Step 1: Parse corpus → SQLite
    _console.print("\n[bold][1/2][/bold] Parsing corpus \u2192 SQLite \u2026")
    graph_stats = kg.build_graph(wipe=wipe)
    for kind, count in sorted(graph_stats.node_counts.items()):
        _console.print(f"  {kind:<12} {count:>6}")
    _console.print(f"  {'─' * 19}")
    _console.print(f"  {'nodes':<12} {graph_stats.total_nodes:>6}  edges {graph_stats.total_edges}")

    # Step 2: SQLite → vectors + SIMILAR_TO
    _console.print("\n[bold][2/2][/bold] Embedding nodes \u2192 vectors \u2026")
    idx_stats = kg.index.build(
        kg.store,
        wipe=wipe,
        batch_size=batch,
        discover_similar=not no_similar,
        quiet=False,
        n_workers=workers,
    )
    _console.print(f"  model    : {idx_stats['model_name']}  dim={idx_stats['dim']}")
    _console.print(f"  indexed  : {idx_stats['indexed_rows']} vectors")
    if not no_similar:
        _console.print(f"  SIMILAR_TO: {idx_stats.get('similar_edges_added', 0)} edges")

    _console.print("\n[green]Build complete.[/green]")
    kg.close()


@cli.command("build-graph")
@repo_option
@sqlite_option
@model_option
@click.option(
    "--chunk-size",
    type=int,
    default=512,
    show_default=True,
    help="Approximate max characters per chunk.",
)
@click.option(
    "--chunk-overlap",
    type=int,
    default=64,
    show_default=True,
    help="Character overlap between consecutive chunks.",
)
@click.option(
    "--similarity-threshold",
    type=float,
    default=0.75,
    show_default=True,
    help="Cosine similarity threshold for semantic split detection.",
)
@click.option(
    "--enable-topics/--no-topics",
    default=True,
    show_default=True,
    help="Enable chunk->topic extraction and HAS_TOPIC edges.",
)
@click.option(
    "--enable-entities/--no-entities",
    default=True,
    show_default=True,
    help="Enable chunk->entity extraction and MENTIONS_ENTITY edges.",
)
@click.option(
    "--enable-keywords/--no-keywords",
    default=True,
    show_default=True,
    help="Enable chunk->keyword extraction and HAS_KEYWORD edges.",
)
@click.option(
    "--emit-cooccur/--no-cooccur",
    default=True,
    show_default=True,
    help="Emit CO_OCCURS_WITH edges among semantic nodes in each chunk.",
)
@click.option(
    "--cooccur-window",
    type=int,
    default=1,
    show_default=True,
    help="Co-occurrence window metadata for emitted CO_OCCURS_WITH edges.",
)
@click.option(
    "--topic-threshold",
    type=float,
    default=0.2,
    show_default=True,
    help="Topic confidence threshold in [0, 1].",
)
@click.option(
    "--topics-file",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Optional JSON/YAML topic catalog file.",
)
@click.option(
    "--update",
    is_flag=True,
    default=False,
    help="Incremental update — keep existing SQLite graph instead of wiping.",
)
@click.option(
    "--ext",
    multiple=True,
    default=(".md", ".txt"),
    show_default=True,
    help="File extensions to include (repeatable).",
)
@click.option(
    "--exclude-dir",
    multiple=True,
    metavar="DIR",
    help=(
        "Directory name to exclude at every depth during the file walk (repeatable). "
        "Merged with [tool.memorykg].exclude from pyproject.toml."
    ),
)
def build_graph(
    repo: str,
    sqlite: str,
    model: str,
    chunk_size: int,
    chunk_overlap: int,
    similarity_threshold: float,
    enable_topics: bool,
    enable_entities: bool,
    enable_keywords: bool,
    emit_cooccur: bool,
    cooccur_window: int,
    topic_threshold: float,
    topics_file: str | None,
    update: bool,
    ext: tuple[str, ...],
    exclude_dir: tuple[str, ...],
) -> None:
    """Build only the SQLite graph from a corpus directory."""
    repo_root = Path(repo).resolve()
    db_path = Path(sqlite) if sqlite else repo_root / ".memorykg" / "graph.sqlite"
    wipe = not update
    extensions = {e if e.startswith(".") else f".{e}" for e in ext}
    exclude = load_exclude_dirs(repo_root) | set(exclude_dir)

    kg = MemoryKG(
        corpus_root=repo_root,
        db_path=db_path,
        exclude=exclude or None,
        model=model,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        similarity_threshold=similarity_threshold,
        enable_topics=enable_topics,
        enable_entities=enable_entities,
        enable_keywords=enable_keywords,
        emit_cooccur=emit_cooccur,
        cooccur_window=cooccur_window,
        topic_threshold=topic_threshold,
        topics_file=topics_file,
    )

    if extensions:
        kg.graph.extensions = extensions

    _console.print(Rule(f"MemoryKG build-graph — {repo_root.name}", style="bold blue"))
    _console.print(f"  corpus  : {repo_root}")
    _console.print(f"  sqlite  : {db_path}")
    _console.print(f"  ext     : {', '.join(sorted(extensions))}")
    _console.print(f"  exclude : {', '.join(sorted(exclude)) if exclude else '(none)'}")

    stats = kg.build_graph(wipe=wipe)
    for kind, count in sorted(stats.node_counts.items()):
        _console.print(f"  {kind:<12} {count:>6}")
    _console.print(f"  {'─' * 19}")
    _console.print(f"  {'nodes':<12} {stats.total_nodes:>6}  edges {stats.total_edges}")
    _console.print("\n[green]Build complete.[/green]")
    kg.close()


@cli.command("build-index")
@repo_option
@sqlite_option
@vectors_option
@model_option
@click.option(
    "--update",
    is_flag=True,
    default=False,
    help="Incremental update — keep existing vectors instead of wiping.",
)
@click.option(
    "--no-similar",
    is_flag=True,
    default=False,
    help="Skip SIMILAR_TO edge discovery after indexing.",
)
@click.option(
    "--batch",
    type=int,
    default=256,
    show_default=True,
    help="Embedding batch size.",
)
@click.option(
    "--workers",
    type=int,
    default=8,
    show_default=True,
    help="Number of parallel embedding workers (>1 uses multi-process CorpusEmbedder).",
)
def build_index(
    repo: str,
    sqlite: str,
    vectors: str,
    model: str,
    update: bool,
    no_similar: bool,
    batch: int,
    workers: int,
) -> None:
    """Build only the sqlite-vec semantic index from an existing SQLite graph."""
    repo_root = Path(repo).resolve()
    db_path = Path(sqlite) if sqlite else repo_root / ".memorykg" / "graph.sqlite"
    vectors_path = Path(vectors) if vectors else repo_root / ".memorykg" / "vectors.sqlite"
    wipe = not update
    kg = MemoryKG(
        corpus_root=repo_root,
        db_path=db_path,
        vectors_path=vectors_path,
        model=model,
    )

    _console.print(Rule(f"MemoryKG build-index — {db_path.name}", style="bold blue"))
    _console.print(f"  sqlite  : {db_path}")
    _console.print(f"  vectors : {vectors_path}")

    _console.print("\nEmbedding nodes \u2192 vectors \u2026")
    idx_stats = kg.index.build(
        kg.store,
        wipe=wipe,
        batch_size=batch,
        discover_similar=not no_similar,
        quiet=False,
        n_workers=workers,
    )
    _console.print(f"  model    : {idx_stats['model_name']}  dim={idx_stats['dim']}")
    _console.print(f"  indexed  : {idx_stats['indexed_rows']} vectors")
    if not no_similar:
        _console.print(f"  SIMILAR_TO: {idx_stats.get('similar_edges_added', 0)} edges")
    _console.print("\n[green]Build complete.[/green]")
    kg.close()


# ---------------------------------------------------------------------------
# Two-phase build
# ---------------------------------------------------------------------------

_cache_option = click.option(
    "--cache",
    type=click.Path(),
    default=None,
    help="Embedding cache path (default: <sqlite parent>/embeddings.jsonl). "
    "Must end in .jsonl or .jsonl.gz.",
)
_device_option = click.option(
    "--device",
    type=click.Choice(["cpu", "mps", "cuda", "auto"]),
    default="auto",
    show_default=True,
    help="Embedding device. 'auto' detects; MPS/CUDA stream single-process, "
    "CPU fans out across workers.",
)


def _resolve_cache_path(cache: str | None, db_path: Path) -> Path:
    """Return the embedding-cache path, defaulting beside the SQLite graph."""
    return Path(cache) if cache else db_path.parent / "embeddings.jsonl"


@cli.command("build-embeddings")
@repo_option
@sqlite_option
@vectors_option
@model_option
@_cache_option
@_device_option
@click.option(
    "--batch",
    type=int,
    default=128,
    show_default=True,
    help="Embedding batch size.",
)
@click.option(
    "--workers",
    type=int,
    default=None,
    help="Worker processes for CPU embedding (default: CPU count / 2). Ignored on GPU.",
)
@click.option("--force", is_flag=True, default=False, help="Overwrite an existing cache.")
def build_embeddings(
    repo: str,
    sqlite: str,
    vectors: str,
    model: str,
    cache: str | None,
    device: str,
    batch: int,
    workers: int | None,
    force: bool,
) -> None:
    """Embed an existing SQLite graph into a JSONL cache (phase 1 of two)."""
    repo_root = Path(repo).resolve()
    db_path = Path(sqlite) if sqlite else repo_root / ".memorykg" / "graph.sqlite"
    vectors_path = Path(vectors) if vectors else repo_root / ".memorykg" / "vectors.sqlite"
    cache_path = _resolve_cache_path(cache, db_path)

    if cache_path.exists() and not force:
        _console.print(f"[yellow]Cache already exists: {cache_path}[/yellow]")
        _console.print("Use --force to overwrite.")
        return

    kg = MemoryKG(
        corpus_root=repo_root,
        db_path=db_path,
        vectors_path=vectors_path,
        model=model,
    )

    _console.print(Rule(f"MemoryKG build-embeddings — {db_path.name}", style="bold blue"))
    _console.print(f"  sqlite  : {db_path}")
    _console.print(f"  cache   : {cache_path}")
    _console.print(f"  device  : {device}")

    _console.print("\nEmbedding nodes → cache …")
    out = kg.build_embeddings(
        cache_path,
        n_workers=workers,
        batch_size=batch,
        device=None if device == "auto" else device,
        quiet=False,
    )
    _console.print(f"\n[green]Embedding cache written:[/green] {out}")
    _console.print("Next: memorykg build-index-from-cache")
    kg.close()


@cli.command("build-index-from-cache")
@repo_option
@sqlite_option
@vectors_option
@model_option
@_cache_option
@click.option(
    "--update",
    is_flag=True,
    default=False,
    help="Incremental update — keep existing vectors instead of wiping.",
)
@click.option(
    "--no-similar",
    is_flag=True,
    default=False,
    help="Skip SIMILAR_TO edge discovery after indexing.",
)
@click.option(
    "--batch",
    type=int,
    default=4096,
    show_default=True,
    help="Vector-store write batch size.",
)
def build_index_from_cache(
    repo: str,
    sqlite: str,
    vectors: str,
    model: str,
    cache: str | None,
    update: bool,
    no_similar: bool,
    batch: int,
) -> None:
    """Build the vector index from a JSONL embedding cache (phase 2 of two)."""
    repo_root = Path(repo).resolve()
    db_path = Path(sqlite) if sqlite else repo_root / ".memorykg" / "graph.sqlite"
    vectors_path = Path(vectors) if vectors else repo_root / ".memorykg" / "vectors.sqlite"
    cache_path = _resolve_cache_path(cache, db_path)

    if not cache_path.exists():
        raise click.ClickException(
            f"Embedding cache not found: {cache_path}. Run 'memorykg build-embeddings' first."
        )

    kg = MemoryKG(
        corpus_root=repo_root,
        db_path=db_path,
        vectors_path=vectors_path,
        model=model,
    )

    _console.print(Rule(f"MemoryKG build-index-from-cache — {db_path.name}", style="bold blue"))
    _console.print(f"  cache   : {cache_path}")
    _console.print(f"  vectors : {vectors_path}")

    _console.print("\nIndexing cache → vectors (no model inference) …")
    stats = kg.build_index_from_cache(
        cache_path,
        wipe=not update,
        batch_size=batch,
        discover_similar=not no_similar,
        quiet=False,
    )
    _console.print(f"  indexed  : {stats.indexed_rows} vectors  dim={stats.index_dim}")
    if not no_similar:
        _console.print(f"  SIMILAR_TO: {stats.similar_edges_added or 0} edges")
    _console.print("\n[green]Build complete.[/green]")
    kg.close()


@cli.command("build-two-phase")
@repo_option
@sqlite_option
@vectors_option
@model_option
@_cache_option
@_device_option
@click.option(
    "--no-similar",
    is_flag=True,
    default=False,
    help="Skip SIMILAR_TO edge discovery after indexing.",
)
@click.option(
    "--batch",
    type=int,
    default=128,
    show_default=True,
    help="Embedding batch size.",
)
@click.option(
    "--workers",
    type=int,
    default=None,
    help="Worker processes for CPU embedding (default: CPU count / 2). Ignored on GPU.",
)
@click.option(
    "--keep-cache",
    is_flag=True,
    default=False,
    help="Reuse an existing cache instead of re-embedding.",
)
def build_two_phase(
    repo: str,
    sqlite: str,
    vectors: str,
    model: str,
    cache: str | None,
    device: str,
    no_similar: bool,
    batch: int,
    workers: int | None,
    keep_cache: bool,
) -> None:
    """Embed to a JSONL cache, then index from it — the resumable build path."""
    repo_root = Path(repo).resolve()
    db_path = Path(sqlite) if sqlite else repo_root / ".memorykg" / "graph.sqlite"
    vectors_path = Path(vectors) if vectors else repo_root / ".memorykg" / "vectors.sqlite"
    cache_path = _resolve_cache_path(cache, db_path)

    kg = MemoryKG(
        corpus_root=repo_root,
        db_path=db_path,
        vectors_path=vectors_path,
        model=model,
    )

    _console.print(Rule(f"MemoryKG build-two-phase — {db_path.name}", style="bold blue"))
    _console.print(f"  sqlite  : {db_path}")
    _console.print(f"  cache   : {cache_path}")
    _console.print(f"  vectors : {vectors_path}")

    if keep_cache and cache_path.exists():
        _console.print(f"\n[yellow]Reusing existing cache:[/yellow] {cache_path}")
    else:
        _console.print("\nPhase 1: embedding nodes → cache …")
        kg.build_embeddings(
            cache_path,
            n_workers=workers,
            batch_size=batch,
            device=None if device == "auto" else device,
            quiet=False,
        )

    _console.print("\nPhase 2: indexing cache → vectors …")
    stats = kg.build_index_from_cache(
        cache_path,
        wipe=True,
        discover_similar=not no_similar,
        quiet=False,
    )
    _console.print(f"  indexed  : {stats.indexed_rows} vectors  dim={stats.index_dim}")
    if not no_similar:
        _console.print(f"  SIMILAR_TO: {stats.similar_edges_added or 0} edges")
    _console.print("\n[green]Build complete.[/green]")
    kg.close()
