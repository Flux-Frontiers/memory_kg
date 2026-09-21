# Release Notes -- v0.12.0

> Released: 2026-09-21

MemoryKG's MCP server now closes the graph database when it shuts down. This
release also settles a long-standing puzzle in the changelog: why `[0.4.0]` and
`[0.4.1]` each appear twice. No index rebuild or migration is needed.

## What changed

**The MCP server closes the graph on shutdown.** `memorykg-mcp` wires an
`asynccontextmanager` into `FastMCP(lifespan=...)`, so the SQLite connection is
released when the server stops rather than left to process exit. One hook
covers both the stdio and SSE transports, because both route through the same
underlying `Server.run()`. This is the resource-cleanup pattern the fleet
standardised on, and it is verified against a real server run rather than a
stubbed `close`.

**The duplicate 0.4.x changelog headings are explained, not renumbered.** They
had been recorded as a defect -- one of each pair assumed to carry a wrong
version number. Neither does. This repository's git history begins 2026-04-08,
and at that first commit the changelog already carried the 2026-03 entries,
inherited wholesale from the project MemoryKG was rebranded out of; they
reference `doc-kg`, `code-kg` and `CODEKG_SKIP_SNAPSHOT` for that reason. The
2026-04-25 pair is MemoryKG's own, matching its version bumps and the `v0.4.1`
tag.

Both pairs therefore record real releases, of two different packages.
Renumbering either would have made an accurate file inaccurate, so a note now
marks where the inherited history begins and says why the numbers repeat.

## Upgrading

Nothing to do. If you run `memorykg-mcp` inside a long-lived process, it now
leaves no database handle behind when it stops.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
