# Finding: name-based call resolution over-approximates `callers` / fan-in / centrality for shared method names

*Issue-ready writeup for **Flux-Frontiers/pycode_kg** (v0.19.3). Discovered while building
a SWE-bench retrieval benchmark + capability demo for PyCodeKG; see
`benchmarks/capabilities/` and `benchmarks/swebench/` in the memory_kg analysis branch.*

## Summary

PyCodeKG resolves Python **method/attribute calls by name** (no receiver-type
inference). When a method name is shared across classes (`get`, `update`, `__init__`,
`run`, …), a call `obj.get(...)` resolves to **every** definition named `get`. As a
result, `callers()`, fan-in, `centrality`, `bridge_centrality`, `framework_nodes`,
and dead-code detection **over-approximate** for common names. The graph already
records this as low confidence (`resolution_mode = "name_fallback_ambiguous"`), but the
consuming queries don't use that signal — so the over-approximation is invisible to
callers of the tools.

## Evidence (psf/requests @ base)

Top-5 functions by fan-in are five *different* `get` methods, all with the **identical**
count — a tell-tale of name collapse:

| function | module | fan-in |
|---|---|---:|
| `CaseInsensitiveDict.get` | `requests/structures.py` | 124 |
| `LookupDict.get` | `requests/structures.py` | 124 |
| `RequestsCookieJar.get` | `requests/cookies.py` | 124 |
| `Session.get` | `requests/sessions.py` | 124 |
| `get` | `requests/api.py` | 124 |

All 124 are the union of every `*.get(...)` call site in the repo (including stdlib
`dict.get`), attributed to all five definitions. By contrast a **uniquely-named**
symbol resolves correctly: `callers("httpbin")` returns 45 exact caller functions.

So the defect is scoped to **ambiguous names**; unique names are already exact.

## Root cause

1. `GraphStore.resolve_symbols()` links a call stub to definitions. It already
   classifies each link:
   - `exact_qualname` → **high** (matched dotted `module.qualname`)
   - `name_fallback` → **medium**
   - `name_fallback_ambiguous` → **low** (≥2 defs share the bare name)
   and stores `resolution_mode` / `confidence` in the `RESOLVES_TO` edge evidence.
2. **But the consumers ignore it.** `GraphStore.callers_of()` traverses
   `CALLS → sym: → RESOLVES_TO → def` and counts **every** resolved def regardless of
   confidence. Fan-in, `centrality`, `bridge_centrality`, `framework_nodes`, and the
   dead-code set are all derived from the same unfiltered traversal.

Perfect resolution is undecidable in Python (dynamic dispatch), so some
over-approximation is fundamental — but the current behavior discards a signal that is
**already computed**, and misses cheap, sound disambiguations.

## Impact

- `callers()` returns false-positive callers for any shared-name target.
- Fan-in / `centrality` / `bridge_centrality` rank shared-name methods (`get`,
  `__init__`, `update`) artificially high — they look like architectural hubs.
- Dead-code detection **under-reports** (a genuinely-dead `foo` looks "called" if any
  other class also defines `foo` and *that* one is called).
- Inflated `CALLS`/`RESOLVES_TO` edge counts skew any PageRank-style ranking.

## Proposed fixes (ranked by effort ÷ payoff)

1. **[low effort, high payoff] Make consumers honor the confidence already stored.**
   Add `min_confidence="medium"` (or `exclude_ambiguous=True`) to `callers_of()` and the
   fan-in/centrality/dead-code paths; default to dropping or down-weighting
   `name_fallback_ambiguous` edges. Surface it in the `callers()` MCP tool as
   `resolution_confidence` and `ambiguous: true/false` so agents can tell an exact
   answer from a guess. This alone removes the `get=124` artifact.
2. **[low effort] Scope `self.`/`cls.` calls to the enclosing class + MRO.** A call
   `self.get()` inside `CaseInsensitiveDict` should resolve to `CaseInsensitiveDict.get`
   (and base classes via `INHERITS`), not to all `get`. This is sound and covers a large
   fraction of intra-class calls.
3. **[medium] Lightweight local type inference for receivers.** Resolve `x.method()`
   when `x` is bound in-scope by `x = Foo()`, a parameter annotation `x: Foo`, or a
   return annotation. Upgrades `name_fallback_ambiguous` → `exact_qualname` for the
   common cases. Bound it to the current scope to keep it deterministic and cheap.
4. **[medium] Import-graph disambiguation.** For `mod.func()` where `mod` is an imported
   alias, restrict candidates to that module's `func` via the existing `IMPORTS` edges.
5. **[reporting] Confidence-weighted edges everywhere.** `analyze`, `viz`, and the
   centrality rankers gain an optional `min_confidence` so architectural reports stop
   treating ambiguous edges as ground truth.

## Reproduction

```bash
pip install pycode-kg
git clone https://github.com/psf/requests /tmp/requests
python benchmarks/capabilities/capability_demo.py --repo /tmp/requests
# → "Change blast-radius" table shows 5 distinct `get` methods, all fan-in == 124
```

## Suggested acceptance test

On a fixture with two classes `A.get` (called once) and `B.get` (called twice):
- `callers("A.get", min_confidence="medium")` returns exactly the 1 real caller.
- `A.get` is reported dead iff it truly has no scoped/typed caller.
- The `get=124`-style identical-fan-in collapse does not occur.

## Note

This does **not** undermine PyCodeKG's value proposition — uniquely-named symbols and
the aggregate structural views remain sound and are still strictly more than any
embedding or `grep` can produce. It is a precision bug in how an already-computed
confidence signal is (not) consumed, with a low-effort first fix.
