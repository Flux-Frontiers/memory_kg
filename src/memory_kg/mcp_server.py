#!/usr/bin/env python3
"""
mcp_server.py — MemoryKG MCP Server

Serves a memory corpus's knowledge graph to any MCP-compatible agent over the
fleet's shared server base, :mod:`kg_utils.mcp`.

The server answers the fleet's canonical tools -- ``stats``, ``query``,
``pack``, ``get_node``, ``neighbors`` -- under the same names as every other
KG server. ``query`` and ``pack`` are MemoryKG's own: its search fuses dense
and keyword (BM25) seeds, and ``pack`` sizes excerpts in characters.
``stats``, ``get_node`` and ``neighbors`` are the shared ones.

The tool list is not kept by hand anywhere: each tool's docstring is its
description, the server's instructions are generated from them, and::

    memorykg mcp --manifest

prints the whole list as JSON without opening the graph.

Usage
-----
::

    memorykg mcp --repo /path/to/corpus

``--db`` and ``--vectors`` default to ``.memorykg/graph.sqlite`` and
``.memorykg/vectors.sqlite``; a relative path is taken from ``--repo``.
``memorykg-mcp`` is the same command under its older name.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from kg_utils.mcp import Context, KGServer, kg_from, make_server

from memory_kg import MemoryKG, __version__
from memory_kg.memorykg import DEFAULT_MODEL
from memory_kg.store import DEFAULT_RELS

#: Relations ``query`` and ``pack`` follow when the caller names none: the
#: store's defaults plus CO_OCCURS_WITH, as the server has always used.
SERVER_RELS: tuple[str, ...] = (*DEFAULT_RELS, "CO_OCCURS_WITH")

PREAMBLE = (
    "MemoryKG is a hybrid semantic + structural knowledge graph for conversational "
    "memory and document corpora. Nodes are documents or sessions ('doc:<file>'), "
    "sections ('sec:<file>:<heading-slug>'), chunks ('chunk:<file>:<0000>'), the "
    "topics, entities and keywords drawn from them ('topic:<slug>', 'entity:<slug>', "
    "'keyword:<slug>'), and, where the semantic memory layer is built, assertions and "
    "events. Edges: CONTAINS (document → section → chunk), NEXT (reading order), "
    "REFERENCES, SIMILAR_TO, HAS_TOPIC, MENTIONS_ENTITY, HAS_KEYWORD and "
    "CO_OCCURS_WITH; the memory layer adds SUPPORTS, ABOUT, REFERS_TO, INVOLVES, "
    "DESCRIBES, SUPERSEDES and DERIVED_FROM.\n\n"
    "## Recommended workflows\n\n"
    "- **Orientation**: stats\n"
    "- **Recall material on a subject**: query → get_node\n"
    "- **Read it**: pack with a descriptive query\n"
    "- **Walk the structure**: neighbors(node_id) — a session's sections, a chunk's "
    "NEXT and SIMILAR_TO neighbours, an assertion's subject and supporting chunks; "
    "narrow with rels=[...] or direction"
)


def query(
    q: str,
    k: int = 8,
    hop: int = 1,
    max_nodes: int = 25,
    rels: list[str] | None = None,
    *,
    ctx: Context,
) -> dict[str, Any]:
    """
    Hybrid search over the memory: ranked sessions, sections, chunks and topics, and the edges among them.

    Seeds fuse dense (vector) and keyword (BM25) matches, then expand through
    the graph. Use ``pack`` instead when you want the text itself.

    :param q: Natural-language query.
    :param k: Seeds to start from (1-100, default 8).
    :param hop: Graph expansion hops from each seed (0-5, default 1).
    :param max_nodes: Most nodes to return (default 25).
    :param rels: Edge types to follow; omit for the corpus relations listed above.
    """
    result = kg_from(ctx).query(
        q, k=k, hop=hop, rels=tuple(rels) if rels else SERVER_RELS, max_nodes=max_nodes
    )
    return result.to_dict()


def pack(
    q: str,
    k: int = 8,
    hop: int = 1,
    max_nodes: int = 15,
    rels: list[str] | None = None,
    max_chars: int = 2000,
    *,
    ctx: Context,
) -> str:
    """
    Hybrid search rendered as a Markdown pack of text excerpts, ready to read.

    :param q: Natural-language query.
    :param k: Seeds to start from (1-100, default 8).
    :param hop: Graph expansion hops (0-5, default 1).
    :param max_nodes: Most excerpts (default 15).
    :param rels: Edge types to follow; omit for the corpus relations listed above.
    :param max_chars: Longest excerpt, in characters (default 2000).
    """
    result = kg_from(ctx).pack(
        q,
        k=k,
        hop=hop,
        rels=tuple(rels) if rels else SERVER_RELS,
        max_chars=max_chars,
        max_nodes=max_nodes,
    )
    return result.to_markdown()


def build_server(
    repo: str | Path,
    db: str | Path | None = None,
    vectors: str | Path | None = None,
    model: str | None = None,
) -> KGServer:
    """Build the MemoryKG MCP server for one corpus, without opening its graph.

    :param repo: Corpus root the graph was built from.
    :param db: Graph database; ``None`` for ``<repo>/.memorykg/graph.sqlite``.
    :param vectors: Vector store; ``None`` for ``<repo>/.memorykg/vectors.sqlite``.
    :param model: Embedding model; ``None`` for :data:`DEFAULT_MODEL`.
    :return: The server; serve it with :func:`kg_utils.mcp.run`.
    """
    root = Path(repo).resolve()

    def open_kg() -> MemoryKG:
        return MemoryKG(root, db, vectors, model=model or DEFAULT_MODEL)

    server = make_server(
        open_kg, name="memorykg", kind="memory", version=__version__, instructions=PREAMBLE
    )
    server.canonical("query")(query)
    server.canonical("pack")(pack)
    return server


def main(argv: list[str] | None = None) -> None:
    """Entry point for ``memorykg-mcp``: the same command as ``memorykg mcp``.

    :param argv: Arguments; ``None`` for ``sys.argv[1:]``.
    """
    from memory_kg.cli.cmd_mcp import mcp_command  # pylint: disable=import-outside-toplevel

    mcp_command.main(args=argv, prog_name="memorykg-mcp")


if __name__ == "__main__":
    main()
