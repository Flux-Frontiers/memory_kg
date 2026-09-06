# Release Notes — v0.9.0

> Released: 2026-09-06

This release does three things at once: it gives MemoryKG real temporal
memory, it makes large-corpus builds practical, and it stops snapshots from
being keyed on a hash that never resolved.

## What changed

**Temporal memory: `occurred_start` and `recorded_at`.** A note written
tonight about last Tuesday happened on Tuesday and was recorded tonight — a
timeline that files it under tonight is wrong. Documents, sections and chunks
now all carry both, distinguishing what a memory is about from when it was
written down. The date parser was rewritten against a real corpus rather than
an invented one: personal_agent's `DiaryTransformer` writes pipe-delimited
entries per line, not the YAML frontmatter the first version assumed, so
`occurred_start` never fired on real data until this was found. A related bug
found on the Pepys diary sent most chunks — those with no timestamp of their
own — to the document's full ten-year span instead of the entry they actually
belong to; both are fixed and pinned by regression tests against the real
corpus.

**Two-phase index build, and streaming corpus parsing.** Embedding and index
writing are now separate resumable passes with a JSONL cache between them, so
a failure writing the index no longer discards hours of embedding.
`parse_corpus(on_batch=...)` streams parsed nodes into SQLite instead of
buffering an entire corpus, for corpora too large to hold in memory. Upserts
commit in batches of 5000, bounding peak memory and avoiding one long-held
transaction.

**Snapshots are keyed on a release tag or timestamp, not a git tree hash.**
The tree hash was read before `git add` staged the snapshot, so it named a
tree that was never committed — across the fleet, only 63 of 605 snapshot keys
ever resolved. `snapshot save VERSION` now uses VERSION as the key; omit it
for a corpus snapshot and it takes a UTC timestamp instead. A follow-up fix
(caught before this release, not after) closes a second gap in the same area:
`save_snapshot` was silently dropping the key and its provenance fields on the
way to disk.

**One column list drives every node read**, and the store gained a
`metadata` column. Both close the same failure mode: a column reachable from
some queries and not others reads as "this node is undated" rather than
raising, which is how a missing column shipped silently before.

**`release.yml` now publishes to PyPI**, matching the rest of the fleet. The
old workflow built a wheel and created a GitHub Release but stopped there —
which is why 0.8.0 was tagged and released on GitHub in August and never
reached the index. This release is the first this repo has published through
CI.

## Upgrading

Rebuild your index. The new `metadata` column has no in-place migration —
MemoryKG indexes are built from their corpus, so an old database is replaced
rather than altered. Querying one before rebuilding fails loudly on the
missing column, which is the signal to rebuild.

Existing snapshots keep their keys and stay addressable. Anyone snapshotting
at a release should pass the tag explicitly going forward:
`capture(..., key="v0.9.0")`.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
