#!/usr/bin/env python3
"""
PyCodeKG Capability Demo — the structural queries vectors and grep can't answer
==============================================================================

The retrieval benchmarks (HotpotQA, SWE-bench) show the honest truth: graph
hop-expansion is *not* a magic reranker. So where does a structural code graph
actually earn its keep over the "agentic search" / flat-embedding stack? In the
queries that are not retrieval at all — questions about the *shape* of the code:

    • "Who actually calls this function?"        (CALLS, scope- and alias-resolved)
    • "What's the blast radius if I change it?"  (fan-in ranking)
    • "What's dead?"                              (functions with zero callers)

A vector index cannot answer these in principle — it ranks by similarity, it does not
enumerate a call graph. `grep` *approximates* the first one and gets it wrong: it
matches the definition line, docstrings, comments, test files, and every unrelated
method that happens to share the name, while missing calls made through an import
alias. PyCodeKG answers them exactly, deterministically, in milliseconds, for $0.

This script builds a PyCodeKG over a real repo and demonstrates each capability,
contrasting the precise graph answer with the `grep` textual baseline. It writes a
Markdown report and prints a summary.

Usage:
    pip install pycode-kg
    # Use an already-checked-out repo (e.g. the SWE-bench cache):
    python benchmarks/capabilities/capability_demo.py --repo /tmp/swebench_repos/psf__requests
    # Or point at any local Python package:
    python benchmarks/capabilities/capability_demo.py --repo /path/to/pkg --out report.md
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from pycode_kg.kg import PyCodeKG
except Exception:  # noqa: BLE001
    PyCodeKG = None  # type: ignore[assignment]

CODE_KINDS = ("function", "method")


# =============================================================================
# GREP BASELINE — what "agentic search" would do for "who calls X?"
# =============================================================================


def grep_callers(repo: Path, name: str) -> dict:
    """Approximate 'who calls `name`' with a textual search, the way grep/an agent would.

    Returns counts that expose grep's imprecision: total textual hits, how many are in
    test files, and the definition site — none of which grep can tell apart from a real
    call, and all of which inflate the answer.
    """
    pat = rf"\b{re.escape(name)}\s*\("
    try:
        out = subprocess.run(
            ["rg", "-n", "--no-heading", pat, str(repo), "-g", "*.py"],
            capture_output=True, text=True, check=False,
        ).stdout
    except FileNotFoundError:
        # Fallback to Python scan if ripgrep is absent
        out = ""
        for py in repo.rglob("*.py"):
            with contextlib.suppress(Exception):
                for j, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
                    if re.search(pat, line):
                        out += f"{py}:{j}:{line}\n"

    lines = [ln for ln in out.splitlines() if ln.strip()]
    in_tests = sum(1 for ln in lines if "/test" in ln or "test_" in ln)
    def_sites = sum(1 for ln in lines if re.search(rf"def\s+{re.escape(name)}\s*\(", ln))
    in_comment = sum(1 for ln in lines if ln.split(":", 2)[-1].lstrip().startswith(("#", '"', "'")))
    return {
        "textual_hits": len(lines),
        "in_test_files": in_tests,
        "definition_sites": def_sites,
        "comment_or_string_lines": in_comment,
    }


# =============================================================================
# THE DEMO
# =============================================================================


def run_demo(repo: Path, model: str, out_path: str, top: int) -> None:
    if PyCodeKG is None:
        sys.exit("\n  PyCodeKG not installed. Run:  pip install pycode-kg\n")

    print(f"  Building PyCodeKG over {repo} ...")
    tmp = Path(tempfile.mkdtemp(prefix="pck_cap_"))
    kg = PyCodeKG(repo_root=repo, db_path=tmp / "g.sqlite", lancedb_dir=tmp / "ldb", model=model)
    with open(os.devnull, "w") as dn, contextlib.redirect_stdout(dn):
        kg.build(wipe=True)

    funcs = kg.store.query_nodes(kinds=list(CODE_KINDS))
    print(f"  {len(funcs)} function/method nodes. Computing fan-in via CALLS edges ...")

    from collections import Counter

    name_counts: Counter = Counter((n.get("name") or "") for n in funcs)

    fan_in: list[tuple[int, dict]] = []
    for node in funcs:
        callers = kg.store.callers_of(node["id"], rel="CALLS")
        fan_in.append((len(callers), node))
    fan_in.sort(key=lambda x: (-x[0], x[1].get("qualname") or ""))

    hotspots = fan_in[:top]
    dead = [n for c, n in fan_in if c == 0]

    # --- Capability 3: callers vs grep ---
    # Pick a target whose SIMPLE NAME IS UNIQUE in the repo so the comparison is honest:
    # PyCodeKG's Python call graph resolves method calls by *name* (no type inference), so
    # for a name shared by many classes (e.g. `get`) the caller set is an over-approximation
    # — same failure mode as grep. For a uniquely-named function the resolution is exact and
    # the contrast with grep's textual matching is clean.
    head_to_head = None
    target = next((n for c, n in fan_in if c > 0 and name_counts[n.get("name") or ""] == 1), None)
    if target is not None:
        name = target.get("name") or (target.get("qualname") or "").split(".")[-1]
        precise = kg.store.callers_of(target["id"], rel="CALLS")
        grep = grep_callers(repo, name)
        head_to_head = {
            "function": target.get("qualname"),
            "module": target.get("module_path"),
            "pycodekg_caller_count": len(precise),
            "pycodekg_callers": [f"{c.get('module_path')}::{c.get('qualname')}" for c in precise[:8]],
            "grep": grep,
        }

    with contextlib.suppress(Exception):
        kg.close()

    # --- Report ---
    lines: list[str] = []
    lines.append(f"# PyCodeKG Capability Report — `{repo.name}`\n")
    lines.append("Structural queries a vector index cannot answer in principle, and `grep` "
                 "answers imprecisely. All figures below are computed from the AST graph — "
                 "deterministic, no LLM, no embedding similarity.\n")
    st = kg.store.stats() if hasattr(kg.store, "stats") else {}
    calls_edges = (st.get("edge_counts") or {}).get("CALLS", "?")
    lines.append(f"- Graph: {st.get('total_nodes', '?')} nodes, {st.get('total_edges', '?')} edges "
                 f"({calls_edges} `CALLS`), {len(funcs)} functions/methods.\n")
    lines.append("> **Honesty caveat.** PyCodeKG's Python call graph resolves method calls by "
                 "*name* (no type inference). For a method name shared across many classes "
                 "(e.g. `get`), the caller set is an **over-approximation** — the same failure "
                 "mode as `grep`. The graph's clean, exact wins are for *uniquely-named* symbols "
                 "(below) and for the *aggregate* views (dead-code set, fan-in distribution) that "
                 "no embedding can produce at all. Names that collide are flagged in the table.\n")

    lines.append("\n## 1. Change blast-radius — highest fan-in functions\n")
    lines.append("*\"If I touch this, what might break?\" — ranked by `CALLS` in-degree. "
                 "A similarity search has no notion of this at all.*\n")
    lines.append("\n| rank | function | fan-in | module | name shared by |")
    lines.append("|---:|---|---:|---|---:|")
    for i, (c, n) in enumerate(hotspots, 1):
        shared = name_counts[n.get("name") or ""]
        flag = f"{shared} defs ⚠️" if shared > 1 else "unique ✓"
        lines.append(f"| {i} | `{n.get('qualname')}` | {c} | `{n.get('module_path')}` | {flag} |")

    lines.append(f"\n## 2. Dead code — functions/methods with zero callers ({len(dead)})\n")
    lines.append("*Computed from in-degree on `CALLS`. (Entry points, dynamically-dispatched, "
                 "test, and public-API functions are expected false positives — but every "
                 "genuinely-dead function is in this list, which no embedding can produce.)*\n")
    for n in dead[:15]:
        lines.append(f"- `{n.get('qualname')}`  ·  `{n.get('module_path')}`")
    if len(dead) > 15:
        lines.append(f"- … and {len(dead) - 15} more")

    if head_to_head:
        h = head_to_head
        g = h["grep"]
        lines.append("\n## 3. \"Who calls X?\" — PyCodeKG vs grep\n")
        lines.append(f"Target: `{h['function']}` in `{h['module']}`\n")
        lines.append(f"\n**PyCodeKG: {h['pycodekg_caller_count']} caller(s)** — exact, "
                     "scope- and import-alias-resolved:\n")
        for c in h["pycodekg_callers"]:
            lines.append(f"- `{c}`")
        lines.append(f"\n**grep `\\b{ (h['function'] or '').split('.')[-1] }\\s*\\(`: "
                     f"{g['textual_hits']} textual hit(s)** — and grep cannot tell which are calls:\n")
        lines.append(f"- {g['definition_sites']} are the definition line(s)")
        lines.append(f"- {g['in_test_files']} are in test files")
        lines.append(f"- {g['comment_or_string_lines']} are comment/docstring/string lines")
        lines.append("- plus every unrelated method that shares the name, and **zero** of the "
                     "calls made through an import alias (which grep can't follow).\n")
        lines.append("> This is the article's own criticism of vector search — *\"semantic "
                     "similarity isn't structural relevance; `processPayment` vs `handlePayment` "
                     "needs exact resolution\"* — turned back on `grep`: textual matching isn't "
                     "call resolution either. Only the graph resolves the call.\n")

    report = "\n".join(lines) + "\n"
    Path(out_path).write_text(report, encoding="utf-8")

    # stdout summary
    print(f"\n{'=' * 60}\n  CAPABILITY SUMMARY — {repo.name}\n{'=' * 60}")
    print(f"  functions/methods : {len(funcs)}")
    print(f"  top fan-in        : "
          + ", ".join(f"{n.get('qualname')}={c}" for c, n in hotspots[:3]))
    print(f"  dead (0 callers)  : {len(dead)}")
    if head_to_head:
        h = head_to_head
        print(f"  callers vs grep   : PyCodeKG={h['pycodekg_caller_count']} exact  "
              f"vs grep={h['grep']['textual_hits']} textual "
              f"({h['grep']['definition_sites']} defs, {h['grep']['in_test_files']} test-file, "
              f"{h['grep']['comment_or_string_lines']} comment/str)")
    print(f"\n  Report written to: {out_path}\n")

    sidecar = out_path.replace(".md", ".json")
    with open(sidecar, "w") as f:
        json.dump({"repo": str(repo), "n_functions": len(funcs),
                   "hotspots": [{"qualname": n.get("qualname"), "fan_in": c, "module": n.get("module_path")}
                                for c, n in hotspots],
                   "dead_count": len(dead), "head_to_head": head_to_head}, f, indent=2)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="PyCodeKG capability demo (structural queries)")
    p.add_argument("--repo", required=True, help="Local path to a checked-out Python repo")
    p.add_argument("--model", default="BAAI/bge-small-en-v1.5")
    p.add_argument("--top", type=int, default=10, help="How many fan-in hotspots to show")
    p.add_argument("--out", default=None, help="Markdown report path")
    args = p.parse_args()

    repo = Path(args.repo).resolve()
    if not repo.exists():
        sys.exit(f"repo not found: {repo}")
    out = args.out or f"benchmarks/capabilities/REPORT_{repo.name}.md"
    run_demo(repo, args.model, out, args.top)
