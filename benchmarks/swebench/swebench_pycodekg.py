#!/usr/bin/env python3
"""
PyCodeKG × SWE-bench — File-Localization Retrieval Benchmark
============================================================

The benchmark that meets *"AI Agents Don't Need Vector Search Anymore"* (Grewal,
2026) on its own ground: **code retrieval**. SWE-bench gives a real GitHub issue
(``problem_statement``) and a gold patch; the retrieval task is *"which file(s) must
be edited to fix this?"* — exactly the file-localization step Agentless and Moatless
isolate. This is where the article claims flat embeddings fail (they "miss imports
and call graphs") and where PyCodeKG's typed AST graph (`CALLS`/`IMPORTS`/`INHERITS`/
`CONTAINS`/`RESOLVES_TO`) should earn its keep.

For each SWE-bench instance:
1. Check out the instance's repo at ``base_commit`` (cached per repo)
2. Build a PyCodeKG over the working tree (AST graph + LanceDB index)
3. Query with the natural-language ``problem_statement``
4. Rank the retrieved nodes' source files and score **file-localization** against the
   files the gold patch actually modifies.

Metrics (LLM-free, deterministic):
  - file_recall@k        — at least one gold file in the top-k retrieved files
  - file_recall_all@k    — every gold file in the top-k (the hard, honest metric)
  - MRR                  — 1 / rank of the first gold file

The article's head-to-head is the same one flag as the HotpotQA harness:
  --hop 0   pure semantic top-k  (the flat baseline the article defends)
  --hop 1   semantic seed + AST graph expansion  (PyCodeKG's structural recovery)

NOTE — this drives PyCodeKG (``pip install pycode-kg`` / the ``pycode_kg`` repo),
which is a *sibling* package, not a dependency of memory_kg. Run it in an env where
``pycode_kg`` is importable. Building a KG per repo and cloning real repos is heavy;
default ``--limit`` is small. Use ``--dataset lite|verified`` (HF parquet, cached).

Usage:
    pip install pycode-kg
    python benchmarks/swebench/swebench_pycodekg.py --dataset lite --limit 20 --hop 1
    python benchmarks/swebench/swebench_pycodekg.py --dataset lite --limit 20 --hop 0  # baseline
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import ssl
import subprocess
import sys
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ssl._create_default_https_context = ssl._create_unverified_context

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# PyCodeKG is a sibling package, optional at import time so --help / dataset prep work
# without it installed. The retrieval step requires it.
try:
    from pycode_kg.kg import PyCodeKG
    from pycode_kg.store import DEFAULT_RELS

    HAVE_PYCODEKG = True
except Exception:  # noqa: BLE001
    PyCodeKG = None  # type: ignore[assignment]
    DEFAULT_RELS = ("CALLS", "IMPORTS", "INHERITS", "CONTAINS")  # type: ignore[assignment]
    HAVE_PYCODEKG = False

DATASETS = {
    "lite": "https://huggingface.co/datasets/princeton-nlp/SWE-bench_Lite/resolve/main/"
    "data/test-00000-of-00001.parquet",
    "verified": "https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified/resolve/main/"
    "data/test-00000-of-00001.parquet",
}
CODE_KINDS = {"module", "class", "function", "method"}


# =============================================================================
# DATA LOADING
# =============================================================================


def load_instances(dataset: str, limit: int, cache_dir: str, repo: str | None = None) -> list[dict]:
    """Download (once) and load SWE-bench instances from the HF parquet."""
    import urllib.request

    import pyarrow.parquet as pq

    os.makedirs(cache_dir, exist_ok=True)
    parquet_path = Path(cache_dir) / f"swebench_{dataset}.parquet"
    if not parquet_path.exists():
        url = DATASETS[dataset]
        print(f"  Downloading SWE-bench {dataset} from {url} ...")
        urllib.request.urlretrieve(url, parquet_path)

    cols = ["instance_id", "repo", "base_commit", "problem_statement", "patch"]
    rows = pq.read_table(parquet_path, columns=cols).to_pylist()
    if repo:
        wanted = {x.strip() for x in repo.split(",") if x.strip()}
        rows = [r for r in rows if r["repo"] in wanted or any(w in r["instance_id"] for w in wanted)]
    return rows[:limit] if limit else rows


def gold_files_from_patch(patch: str) -> set[str]:
    """Extract the set of repo-relative file paths the gold patch modifies."""
    files: set[str] = set()
    for m in re.finditer(r"^\+\+\+ b/(.+)$", patch or "", flags=re.MULTILINE):
        path = m.group(1).strip()
        if path and path != "/dev/null":
            files.add(path)
    # Fallback: diff --git header (handles pure deletions where +++ is /dev/null)
    for m in re.finditer(r"^diff --git a/(.+?) b/(.+)$", patch or "", flags=re.MULTILINE):
        files.add(m.group(2).strip())
    return files


def gold_lines_from_patch(patch: str) -> dict[str, set[int]]:
    """Map each modified file to the *base-commit* (old-side) line numbers it touches.

    The KG is built at ``base_commit`` (pre-fix), so symbol localization must compare
    against old-side line numbers. For each hunk ``@@ -old,_ +new,_ @@`` we walk the
    body: context lines advance the old pointer, ``-`` lines are recorded (modified),
    and ``+`` lines record the current old pointer (the insertion site within the
    enclosing base symbol). This yields the base lines whose enclosing function/method/
    class the patch edits.
    """
    files: dict[str, set[int]] = defaultdict(set)
    cur: str | None = None
    old = 0
    for line in (patch or "").splitlines():
        if line.startswith("+++ b/"):
            cur = line[6:].strip()
            cur = None if cur == "/dev/null" else cur
        elif line.startswith("---") or line.startswith("diff --git") or line.startswith("index "):
            continue
        elif line.startswith("@@"):
            m = re.search(r"-(\d+)", line)
            old = int(m.group(1)) if m else 0
        elif cur is not None and line:
            if line.startswith("-"):
                files[cur].add(old)
                old += 1
            elif line.startswith("+"):
                files[cur].add(old)
            elif line.startswith(" "):
                old += 1
    return files


# =============================================================================
# REPO CHECKOUT
# =============================================================================


def ensure_repo_at(repo: str, base_commit: str, repos_cache: Path) -> Path | None:
    """Clone ``repo`` (cached) and hard-checkout ``base_commit``. Returns the worktree."""
    repo_dir = repos_cache / repo.replace("/", "__")
    try:
        if not (repo_dir / ".git").exists():
            repo_dir.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "clone", "--quiet", f"https://github.com/{repo}.git", str(repo_dir)],
                check=True,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
        subprocess.run(["git", "-C", str(repo_dir), "fetch", "--quiet", "--all"], check=False)
        subprocess.run(
            ["git", "-C", str(repo_dir), "checkout", "--quiet", "--force", base_commit],
            check=True,
        )
        subprocess.run(["git", "-C", str(repo_dir), "clean", "-qfdx"], check=False)
        return repo_dir
    except subprocess.CalledProcessError as e:
        print(f"    checkout failed for {repo}@{base_commit[:8]}: {e}")
        return None


# =============================================================================
# RETRIEVAL
# =============================================================================


def _ranked_files(result, limit: int) -> list[str]:
    """Ordered, de-duplicated repo-relative file paths from retrieved code nodes.

    PyCodeKG stores each node's repo-relative source path in ``module_path``
    (e.g. ``src/pkg/store.py``); see ``find_definition_at`` in its MCP server.
    """
    ordered: list[str] = []
    seen: set[str] = set()
    for node in result.nodes:
        if node.get("kind") not in CODE_KINDS:
            continue
        path = node.get("module_path") or node.get("file_path") or node.get("file")
        if not path:
            continue
        path = str(path).lstrip("./")
        if path not in seen:
            seen.add(path)
            ordered.append(path)
        if len(ordered) >= limit:
            break
    return ordered


def _symbol_first_rank(result, gold_lines: dict[str, set[int]], limit: int = 50) -> int | None:
    """Rank (1-based) of the first retrieved code node whose span overlaps a gold edit.

    A node hits if it is a function/method/class in a gold file whose
    ``[lineno, end_lineno]`` span contains any base-commit line the patch touches.
    This is *symbol*-level localization — strictly harder than file-level and the
    regime where call-graph expansion (``CALLS``) can actually help.
    """
    rank = 0
    for node in result.nodes:
        if node.get("kind") not in {"function", "method", "class"}:
            continue
        rank += 1
        if rank > limit:
            break
        path = str(node.get("module_path") or "").lstrip("./")
        touched = gold_lines.get(path)
        if not touched:
            continue
        lo, hi = node.get("lineno"), node.get("end_lineno")
        if lo is None:
            continue
        hi = hi if hi is not None else lo
        if any(lo <= ln <= hi for ln in touched):
            return rank
    return None


def _score(inst: dict, gold: set[str], gold_lines: dict[str, set[int]], result) -> dict:
    """Score one query result for file- AND symbol-level localization."""
    ranked = _ranked_files(result, limit=50)
    rank_of_first = next((i + 1 for i, f in enumerate(ranked) if f in gold), None)
    sym_rank = _symbol_first_rank(result, gold_lines)

    def recall_any(k: int) -> float:
        return float(bool(gold & set(ranked[:k])))

    def recall_all(k: int) -> float:
        return float(gold and gold.issubset(set(ranked[:k])))

    def sym_recall(k: int) -> float:
        return float(sym_rank is not None and sym_rank <= k)

    return {
        "instance_id": inst["instance_id"],
        "repo": inst["repo"],
        "n_gold": len(gold),
        "gold": sorted(gold),
        "ranked_top10": ranked[:10],
        "recall@1": recall_any(1),
        "recall@5": recall_any(5),
        "recall@10": recall_any(10),
        "recall@20": recall_any(20),
        "recall_all@10": recall_all(10),
        "recall_all@20": recall_all(20),
        "mrr": 1.0 / rank_of_first if rank_of_first else 0.0,
        "sym_recall@5": sym_recall(5),
        "sym_recall@10": sym_recall(10),
        "sym_recall@20": sym_recall(20),
        "sym_mrr": 1.0 / sym_rank if sym_rank else 0.0,
    }


def retrieve_for_instance(
    inst: dict,
    repo_dir: Path,
    tmp_kg: Path,
    top_k: int,
    hops: tuple[int, ...],
    rels: tuple[str, ...],
    model: str,
) -> dict[int, dict]:
    """Build the PyCodeKG once, then query at each hop and score — same graph for all.

    Building dominates cost and is hop-independent, so comparing hop 0 vs hop 1 on the
    *identical* built graph is both ~2x faster and methodologically cleaner.
    """
    gold = gold_files_from_patch(inst["patch"])
    gold_lines = gold_lines_from_patch(inst["patch"])

    kg = PyCodeKG(
        repo_root=repo_dir,
        db_path=tmp_kg / "graph.sqlite",
        lancedb_dir=tmp_kg / "lancedb",
        model=model,
    )
    with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
        kg.build(wipe=True)

    out: dict[int, dict] = {}
    for hop in hops:
        result = kg.query(inst["problem_statement"], k=top_k, hop=hop, rels=rels)
        out[hop] = _score(inst, gold, gold_lines, result)
    with contextlib.suppress(Exception):
        kg.close()
    return out


# =============================================================================
# BENCHMARK RUNNER
# =============================================================================

METRICS = [
    "recall@1", "recall@5", "recall@10", "recall@20", "recall_all@10", "recall_all@20", "mrr",
    "sym_recall@5", "sym_recall@10", "sym_recall@20", "sym_mrr",
]


def run_benchmark(args) -> None:
    hops = tuple(int(h) for h in str(args.hop).split(",") if h.strip() != "")

    print(f"\n{'=' * 60}")
    print("  PyCodeKG × SWE-bench — file-localization retrieval")
    print(f"{'=' * 60}")
    print(f"  Dataset:  {args.dataset}")
    print(f"  Limit:    {args.limit}")
    print(f"  Top-k:    {args.k}")
    print(f"  Hops:     {', '.join(map(str, hops))}  (0=flat top-k, 1=AST graph expansion)")
    print(f"  Model:    {args.model}")
    print(f"{'-' * 60}")

    if not HAVE_PYCODEKG:
        sys.exit(
            "\n  PyCodeKG is not importable. Install the sibling package first:\n"
            "    pip install pycode-kg\n"
            "  (or run this harness inside the pycode_kg repo's virtualenv).\n"
        )

    instances = load_instances(args.dataset, args.limit, args.cache_dir, repo=args.repo)
    print(f"  Loaded {len(instances)} instances.\n")

    repos_cache = Path(args.repos_cache)
    rels = tuple(r.strip() for r in args.rels.split(",")) if args.rels else DEFAULT_RELS

    agg: dict[int, dict[str, list[float]]] = {h: defaultdict(list) for h in hops}
    results_log: list[dict] = []
    start = datetime.now()

    for i, inst in enumerate(instances):
        repo_dir = ensure_repo_at(inst["repo"], inst["base_commit"], repos_cache)
        if repo_dir is None:
            continue
        tmp_kg = Path(tempfile.mkdtemp(prefix="pck_swe_"))
        try:
            per_hop = retrieve_for_instance(inst, repo_dir, tmp_kg, args.k, hops, rels, args.model)
        except Exception as e:  # noqa: BLE001
            print(f"    [{inst['instance_id']}] retrieval error: {e}")
            continue
        finally:
            import shutil

            shutil.rmtree(tmp_kg, ignore_errors=True)

        for h in hops:
            for m in METRICS:
                agg[h][m].append(per_hop[h][m])
        results_log.append({"instance_id": inst["instance_id"], "repo": inst["repo"],
                            "by_hop": per_hop})
        cells = "  ".join(f"hop{h} R@10={per_hop[h]['recall@10']:.0f} MRR={per_hop[h]['mrr']:.2f}"
                          for h in hops)
        print(f"  [{i + 1:3}/{len(instances)}] {inst['instance_id']:<28} {cells}")

    elapsed = (datetime.now() - start).total_seconds()
    n = len(results_log)
    if not n:
        print("\n  No instances scored.")
        return

    print(f"\n{'=' * 60}")
    print(f"  RESULTS — PyCodeKG (top-{args.k})   n={n}   {elapsed:.0f}s ({elapsed / n:.0f}s/inst)")
    print(f"{'=' * 60}")
    header = "  " + f"{'metric':16}" + "".join(f"hop{h:<10}" for h in hops)
    print(header)
    for m in METRICS:
        row = "  " + f"{m:16}" + "".join(f"{sum(agg[h][m]) / n:<13.3f}" for h in hops)
        print(row)
    if len(hops) > 1:
        h0, h1 = hops[0], hops[1]
        d = lambda m: (sum(agg[h1][m]) - sum(agg[h0][m])) / n  # noqa: E731
        print(f"\n  Δ(hop{h1}-hop{h0})  file recall@10 = {d('recall@10'):+.3f}  file MRR = {d('mrr'):+.3f}")
        print(f"  Δ(hop{h1}-hop{h0})  symbol recall@10 = {d('sym_recall@10'):+.3f}  "
              f"symbol MRR = {d('sym_mrr'):+.3f}   <- where CALLS expansion should matter")
    print(f"\n{'=' * 60}\n")

    if args.out:
        summary = {f"hop{h}": {m: sum(agg[h][m]) / n for m in METRICS} for h in hops}
        with open(args.out, "w") as f:
            json.dump(
                {"config": {"dataset": args.dataset, "hops": list(hops), "k": args.k, "n": n,
                            "model": args.model}, "summary": summary, "results": results_log},
                f, indent=2)
        print(f"  Results saved to: {args.out}")


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="PyCodeKG × SWE-bench file-localization benchmark")
    p.add_argument("--dataset", choices=list(DATASETS), default="lite", help="SWE-bench split")
    p.add_argument("--limit", type=int, default=20, help="Number of instances (default: 20)")
    p.add_argument("--repo", default=None,
                   help="Filter to one repo (e.g. pallets/flask) or instance-id substring")
    p.add_argument("--k", type=int, default=10, help="Top-k semantic seeds (default: 10)")
    p.add_argument("--hop", default="1",
                   help="Graph hops: 0=flat, 1=+AST graph. Comma-list builds once, queries each "
                        "(e.g. --hop 0,1 for the head-to-head). Default: 1")
    p.add_argument("--rels", default=None, help="Comma-separated edge types (default: PyCodeKG)")
    p.add_argument("--model", default="BAAI/bge-small-en-v1.5", help="Embedding model")
    p.add_argument("--repos-cache", default="/tmp/swebench_repos", help="Cloned-repo cache dir")
    p.add_argument("--cache-dir", default="/tmp/swebench_cache", help="Dataset cache dir")
    p.add_argument("--out", default=None, help="Output JSON file")
    args = p.parse_args()

    if not args.out:
        args.out = (f"benchmarks/swebench/results_swebench_{args.dataset}"
                    f"_hop{str(args.hop).replace(',', '-')}"
                    f"_{datetime.now().strftime('%Y%m%d_%H%M')}.json")
    run_benchmark(args)
