# PyCodeKG Capability Demo — structural queries vectors & grep can't answer

The retrieval benchmarks in this repo (HotpotQA, SWE-bench) make an honest negative
point: graph **hop-expansion is not a magic reranker**. So this directory answers the
follow-up question — *where does a structural code graph actually beat the agentic /
flat-embedding stack?* Answer: in the queries that aren't retrieval at all, the ones
about the **shape** of the code.

| Question | Vector search | `grep` (agentic search) | PyCodeKG |
|---|---|---|---|
| "Who calls this function?" | ❌ can't — ranks by similarity, doesn't enumerate a call graph | ⚠️ textual guess — matches the def line, docstrings, tests, same-named methods; **misses alias-imported calls** | ✅ exact, scope- & `RESOLVES_TO`-alias-resolved |
| "What's the blast radius of a change?" | ❌ no notion of fan-in | ❌ would need to grep + read every hit | ✅ fan-in ranking from `CALLS` in-degree |
| "What's dead code?" | ❌ | ⚠️ unreliable (can't prove zero calls) | ✅ functions with zero `CALLS` in-degree |

These are deterministic, $0/query, no-LLM, no-embedding answers — exactly the
"structure vectors miss" the article (*"AI Agents Don't Need Vector Search Anymore"*,
2026) says matters, expressed as typed edges rather than a similarity score.

## Run it

```bash
pip install pycode-kg
export PYCODEKG_DEVICE=cpu

# Point at any checked-out Python repo (e.g. the SWE-bench cache):
python benchmarks/capabilities/capability_demo.py --repo /tmp/swebench_repos/psf__requests
```

Output: a Markdown report (`REPORT_<repo>.md`) plus a JSON sidecar, covering
(1) highest-fan-in functions, (2) dead-code candidates, and (3) a head-to-head on
*"who calls X?"* — PyCodeKG's exact, alias-resolved caller set vs the raw textual
hit-count `grep` returns (broken down into definition lines, test-file hits, and
comment/string lines that `grep` cannot distinguish from real calls).

See `REPORT_psf__requests.md` for a committed example.
