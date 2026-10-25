"""
cmd_mcp.py

``memorykg mcp`` -- the fleet's standard MCP command, from :mod:`kg_utils.mcp`:

    memorykg mcp [--repo DIR] [--db FILE] [--vectors FILE] [--model NAME]
                 [--transport stdio|streamable-http] [--host H] [--port N]
                 [--manifest]

Registering it imports neither ``mcp`` nor the server module, so every other
``memorykg`` command starts as fast as before.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from kg_utils.mcp import add_mcp_command

from memory_kg.cli.group import cli

if TYPE_CHECKING:
    from kg_utils.mcp import KGServer


def _build_server(repo: Path, db: Path | None, vectors: Path | None, model: str | None) -> KGServer:
    from memory_kg.mcp_server import build_server  # pylint: disable=import-outside-toplevel

    return build_server(repo, db, vectors, model)


mcp_command = add_mcp_command(cli, _build_server)
