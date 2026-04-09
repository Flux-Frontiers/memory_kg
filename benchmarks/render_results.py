#!/usr/bin/env python3
"""
MemoryKG Benchmark Report Renderer
====================================

Reads one or more LongMemEval JSONL result files produced by
``longmemeval_memkg.py run`` and generates:

  - A Markdown summary (``BENCHMARKS_MEMKG.md`` by default)
  - An optional PDF report (requires ``matplotlib``)

Each JSONL row has the shape emitted by ``cmd_run``::

    {
      "question_id": str,
      "question_type": str,
      "question": str,
      "answer": str | None,
      "retrieved": [{"session_id": str, "rank": int, "via_node_id": str|null}, …],
      "metrics": {
          "recall_any@1": float, "ndcg_any@1": float,
          "recall_any@3": float, "ndcg_any@3": float,
          …  # up to @50
      }
    }

Usage
-----

Single run::

    python benchmarks/render_results.py benchmarks/results_heading_minilm.jsonl

Multiple runs (comparison table)::

    python benchmarks/render_results.py results_a.jsonl results_b.jsonl --labels "MiniLM,BGE"

Custom output::

    python benchmarks/render_results.py results.jsonl --out benchmarks/BENCHMARKS_MEMKG.md --pdf

Author: Eric G. Suchanek, PhD
Last Revision: 2026-04-08
License: Elastic 2.0
"""

from __future__ import annotations

import argparse
import json
import platform
import socket
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Repo / provenance helpers
# ---------------------------------------------------------------------------

MACHINE_DESCRIPTION = "Apple M5 Max MacBook Pro, 64 GB RAM, 2 TB SSD"
REPO_ROOT = Path(__file__).resolve().parent.parent

_KS = [1, 3, 5, 10, 30, 50]


def _git_info(repo_root: Path = REPO_ROOT):
    """Return (short_hash, branch, commit_date, commit_msg) or placeholders."""
    try:

        def _run(cmd):
            return (
                subprocess.check_output(cmd, cwd=repo_root, stderr=subprocess.DEVNULL)
                .decode()
                .strip()
            )

        short_hash = _run(["git", "rev-parse", "--short", "HEAD"])
        branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        commit_date = _run(["git", "log", "-1", "--format=%ai"])
        commit_msg = _run(["git", "log", "-1", "--format=%s"])
        return short_hash, branch, commit_date, commit_msg
    except Exception:
        return "unknown", "unknown", "unknown", "unknown"


# ---------------------------------------------------------------------------
# Data loading + aggregation
# ---------------------------------------------------------------------------


def _load(jsonl_path: Path) -> list[dict]:
    with open(jsonl_path) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _load_meta(jsonl_path: Path) -> dict:
    """Return the _meta header row from a JSONL file, or {} if absent."""
    with open(jsonl_path) as fh:
        for line in fh:
            if line.strip():
                row = json.loads(line)
                if row.get("_meta"):
                    return row
                break
    return {}


def _result_rows(rows: list[dict]) -> list[dict]:
    """Strip _meta header rows from a loaded list."""
    return [r for r in rows if not r.get("_meta")]


def _aggregate(rows: list[dict]) -> dict:
    """Return a single-run aggregate dict."""
    n = len(rows)
    agg: dict[str, float] = {}
    for k in _KS:
        ra = sum(r["metrics"].get(f"recall_any@{k}", 0.0) for r in rows) / n
        nd = sum(r["metrics"].get(f"ndcg_any@{k}", 0.0) for r in rows) / n
        agg[f"recall_any@{k}"] = ra
        agg[f"ndcg_any@{k}"] = nd
    return agg


def _per_type(rows: list[dict]) -> dict[str, dict[str, float]]:
    """Per-question-type aggregate for recall_any@5, @10 and ndcg_any@10."""
    buckets: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        buckets[r["question_type"]].append(r)
    result = {}
    for qtype, group in sorted(buckets.items()):
        n = len(group)
        result[qtype] = {
            "n": n,
            "recall_any@5": sum(g["metrics"].get("recall_any@5", 0) for g in group) / n,
            "recall_any@10": sum(g["metrics"].get("recall_any@10", 0) for g in group) / n,
            "ndcg_any@10": sum(g["metrics"].get("ndcg_any@10", 0) for g in group) / n,
        }
    return result


def _misses(rows: list[dict], at_k: int = 10) -> list[str]:
    return [r["question_id"] for r in rows if r["metrics"].get(f"recall_any@{at_k}", 0.0) == 0.0]


def _label_from_path(path: Path) -> str:
    """Derive a short display label from a results file name."""
    stem = path.stem
    # strip leading 'results_'
    if stem.startswith("results_"):
        stem = stem[len("results_") :]
    return stem


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def _md_header(
    lines: list[str],
    label: str,
    path: Path,
    git_info: tuple,
    n: int,
    meta: dict | None = None,
) -> None:
    short_hash, branch, commit_date, commit_msg = git_info
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines.append("# MemoryKG × LongMemEval — Benchmark Report")
    lines.append("")
    lines.append(f"**Run label:** `{label}`  ")
    lines.append(f"**Results file:** `{path.name}`  ")
    lines.append(f"**Questions evaluated:** {n}  ")
    lines.append(f"**Generated:** {generated}  ")
    if meta:
        elapsed = meta.get("elapsed_s")
        s_per_q = meta.get("s_per_question")
        if elapsed is not None:
            lines.append(f"**Run time:** {elapsed:.1f}s ({s_per_q:.2f}s per question)  ")
    lines.append(f"**Machine:** {MACHINE_DESCRIPTION}  ")
    lines.append(f"**Repository:** memory_kg @ `{short_hash}` ({branch})  ")
    lines.append(f"**Commit:** {commit_date} — {commit_msg}  ")
    lines.append(f"**Python:** {platform.python_version()}  |  **Host:** {socket.gethostname()}  ")
    lines.append("")
    lines.append("---")
    lines.append("")


def _md_aggregate_table(lines: list[str], agg: dict, n: int) -> None:
    lines.append("## Session-Level Retrieval Metrics\n")
    lines.append("| k | Recall@k | NDCG@k |")
    lines.append("|--:|--:|--:|")
    for k in _KS:
        ra = agg[f"recall_any@{k}"]
        nd = agg[f"ndcg_any@{k}"]
        lines.append(f"| {k:2} | {ra:.3f} | {nd:.3f} |")
    lines.append("")


def _md_per_type(lines: list[str], pt: dict[str, dict]) -> None:
    lines.append("## Per-Type Breakdown\n")
    lines.append("| Question Type | n | Recall@5 | Recall@10 | NDCG@10 |")
    lines.append("|---|--:|--:|--:|--:|")
    for qtype, vals in sorted(pt.items()):
        lines.append(
            f"| {qtype} | {vals['n']} "
            f"| {vals['recall_any@5']:.3f} "
            f"| {vals['recall_any@10']:.3f} "
            f"| {vals['ndcg_any@10']:.3f} |"
        )
    lines.append("")


def _md_misses(lines: list[str], miss_ids: list[str], total: int) -> None:
    lines.append("## Misses @ k=10\n")
    lines.append(
        f"**{len(miss_ids)} / {total}** questions had zero sessions retrieved in top-10.\n"
    )
    if miss_ids:
        lines.append("<details>")
        lines.append(f"<summary>Show all {len(miss_ids)} missed question IDs</summary>\n")
        lines.append("```")
        for qid in miss_ids:
            lines.append(qid)
        lines.append("```")
        lines.append("</details>")
    lines.append("")


def _md_key_findings(lines: list[str], agg: dict, pt: dict[str, dict]) -> None:
    lines.append("## Key Findings\n")

    r50 = agg["recall_any@50"]
    r10 = agg["recall_any@10"]
    r5 = agg["recall_any@5"]
    r1 = agg["recall_any@1"]

    lines.append(f"- **Top-1 recall:** {r1:.1%} — immediate precision of the semantic seed")
    lines.append(f"- **Top-5 recall:** {r5:.1%}")
    lines.append(f"- **Top-10 recall:** {r10:.1%}")
    lines.append(f"- **Top-50 recall (coverage ceiling):** {r50:.1%}")
    lines.append("")

    # Easiest / hardest types by R@10
    ranked_types = sorted(pt.items(), key=lambda x: x[1]["recall_any@10"])
    hardest = ranked_types[:2]
    easiest = ranked_types[-2:]

    lines.append("**Hardest question types (by Recall@10):**")
    for qtype, vals in hardest:
        lines.append(f"- `{qtype}`: {vals['recall_any@10']:.1%}")
    lines.append("")
    lines.append("**Easiest question types (by Recall@10):**")
    for qtype, vals in easiest:
        lines.append(f"- `{qtype}`: {vals['recall_any@10']:.1%}")
    lines.append("")


def write_markdown(
    rows: list[dict],
    label: str,
    path: Path,
    out_path: Path,
    git_info: tuple,
    meta: dict | None = None,
) -> Path:
    """Render a single-run Markdown report and write it to ``out_path``."""
    result_rows = _result_rows(rows)
    n = len(result_rows)
    agg = _aggregate(result_rows)
    pt = _per_type(result_rows)
    miss_ids = _misses(result_rows)

    lines: list[str] = []
    _md_header(lines, label, path, git_info, n, meta=meta)
    _md_aggregate_table(lines, agg, n)
    _md_per_type(lines, pt)
    _md_key_findings(lines, agg, pt)
    _md_misses(lines, miss_ids, n)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n")
    return out_path


# ---------------------------------------------------------------------------
# Comparison Markdown (multi-run)
# ---------------------------------------------------------------------------


def write_comparison_markdown(
    runs: list[tuple[str, list[dict]]],
    out_path: Path,
    git_info: tuple,
) -> Path:
    """Write a multi-run comparison report."""
    short_hash, branch, commit_date, commit_msg = git_info
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines: list[str] = []
    lines.append("# MemoryKG × LongMemEval — Multi-Run Comparison")
    lines.append("")
    lines.append(f"**Generated:** {generated}  ")
    lines.append(f"**Repository:** memory_kg @ `{short_hash}` ({branch})  ")
    lines.append(f"**Machine:** {MACHINE_DESCRIPTION}  ")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Aggregate metrics comparison table
    lines.append("## Recall@k Comparison\n")
    header = "| k | " + " | ".join(label for label, _ in runs) + " |"
    sep = "|--:|" + "|".join("--:" for _ in runs) + "|"
    lines.append(header)
    lines.append(sep)
    result_runs = [(label, _result_rows(rows)) for label, rows in runs]
    aggs = [(label, _aggregate(rrows)) for label, rrows in result_runs]
    for k in _KS:
        row = f"| {k:2} | " + " | ".join(f"{agg[f'recall_any@{k}']:.3f}" for _, agg in aggs) + " |"
        lines.append(row)
    lines.append("")

    lines.append("## NDCG@k Comparison\n")
    lines.append(header)
    lines.append(sep)
    for k in _KS:
        row = f"| {k:2} | " + " | ".join(f"{agg[f'ndcg_any@{k}']:.3f}" for _, agg in aggs) + " |"
        lines.append(row)
    lines.append("")

    # Per-type for each run
    for (label, rrows), (_, agg) in zip(result_runs, aggs):
        n = len(rrows)
        pt = _per_type(rrows)
        miss_ids = _misses(rrows)
        meta = next((r for r in runs if r[0] == label), (None, []))[1]
        meta_row = next((r for r in meta if isinstance(r, dict) and r.get("_meta")), {})

        lines.append("---\n")
        run_time = (
            f" — {meta_row['elapsed_s']:.1f}s ({meta_row['s_per_question']:.2f}s/q)"
            if meta_row.get("elapsed_s") is not None
            else ""
        )
        lines.append(f"## Run: `{label}` (n={n}{run_time})\n")
        _md_aggregate_table(lines, agg, n)
        _md_per_type(lines, pt)
        _md_key_findings(lines, agg, pt)
        _md_misses(lines, miss_ids, n)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n")
    return out_path


# ---------------------------------------------------------------------------
# PDF rendering (optional — requires matplotlib)
# ---------------------------------------------------------------------------


def _write_pdf(
    rows: list[dict],
    label: str,
    path: Path,
    out_path: Path,
    git_info: tuple,
) -> Path | None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_pdf import PdfPages
    except ImportError:
        print("  matplotlib not available — skipping PDF")
        return None

    short_hash, branch, commit_date, commit_msg = git_info
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    n = len(rows)
    agg = _aggregate(rows)
    pt = _per_type(rows)
    miss_ids = _misses(rows)

    MONO = "DejaVu Sans Mono"
    SERIF = "DejaVu Sans"

    def new_fig():
        fig = plt.figure(figsize=(8.5, 11))
        fig.patch.set_facecolor("#FAFAFA")
        return fig

    def header_bar(fig, title, subtitle=""):
        ax = fig.add_axes([0, 0.93, 1, 0.07])
        ax.set_axis_off()
        ax.set_facecolor("#1a3a5c")
        ax.text(
            0.5,
            0.65,
            title,
            ha="center",
            va="center",
            fontsize=16,
            fontweight="bold",
            color="white",
            transform=ax.transAxes,
            fontfamily=SERIF,
        )
        if subtitle:
            ax.text(
                0.5,
                0.15,
                subtitle,
                ha="center",
                va="center",
                fontsize=8.5,
                color="#add8e6",
                transform=ax.transAxes,
                fontfamily=SERIF,
            )

    def text_block(fig, text_lines, y_start=0.88, x=0.07, fontsize=8.5, dy=0.022):
        for line in text_lines:
            bold = line.startswith("##")
            clean = line.lstrip("# ").lstrip("**").rstrip("**")
            fs = fontsize + (2 if bold else 0)
            fw = "bold" if bold else "normal"
            col = "#1a3a5c" if bold else "#222222"
            fig.text(
                x,
                y_start,
                clean,
                fontsize=fs,
                fontweight=fw,
                color=col,
                fontfamily=MONO if not bold else SERIF,
                va="top",
            )
            y_start -= dy
            if y_start < 0.04:
                break
        return y_start

    pdf_path = out_path.with_suffix(".pdf")

    with PdfPages(pdf_path) as pdf:
        # Page 1 — Executive Summary
        fig = new_fig()
        header_bar(fig, "MemoryKG × LongMemEval Benchmark", f"Run: {label}  |  {generated}")

        r1, r5, r10, r50 = (agg[f"recall_any@{k}"] for k in [1, 5, 10, 50])
        nd10 = agg["ndcg_any@10"]

        summary = [
            "## Executive Summary",
            "",
            f"Results file      :  {path.name}",
            f"Questions         :  {n}",
            "Retrieval engine  :  MemoryKG (semantic seed + graph expansion)",
            "No inference      :  pure graph retrieval, no LLM rerank",
            "",
            "## Headline Metrics",
            "",
            f"  Recall@1         :  {r1:.3f}  ({r1:.1%})",
            f"  Recall@5         :  {r5:.3f}  ({r5:.1%})",
            f"  Recall@10        :  {r10:.3f}  ({r10:.1%})",
            f"  Recall@50        :  {r50:.3f}  ({r50:.1%})",
            f"  NDCG@10          :  {nd10:.3f}",
            "",
            f"  Misses@10        :  {len(miss_ids)} / {n}  ({len(miss_ids) / n:.1%})",
            "",
            "## Provenance",
            "",
            f"  memory_kg @ {short_hash}  ({branch})",
            f"  Commit : {commit_date}",
            f"  Msg    : {commit_msg}",
            "",
            f"  Python : {platform.python_version()}",
            f"  Host   : {socket.gethostname()}",
            f"  HW     : {MACHINE_DESCRIPTION}",
        ]
        text_block(fig, summary, y_start=0.89)
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        # Page 2 — Metrics table + per-type
        fig = new_fig()
        header_bar(fig, "Retrieval Metrics", f"{label}  |  n={n}")

        tbl = ["## Session-Level Recall & NDCG", ""]
        tbl.append(f"  {'k':>4}  {'Recall@k':>10}  {'NDCG@k':>10}")
        tbl.append(f"  {'-' * 30}")
        for k in _KS:
            ra = agg[f"recall_any@{k}"]
            nd = agg[f"ndcg_any@{k}"]
            tbl.append(f"  {k:>4}  {ra:>10.3f}  {nd:>10.3f}")
        tbl += ["", "## Per Question-Type  (Recall@5 / @10 / NDCG@10)", ""]
        tbl.append(f"  {'Type':<35}  {'n':>5}  {'R@5':>6}  {'R@10':>6}  {'NDCG@10':>8}")
        tbl.append(f"  {'-' * 70}")
        for qtype, vals in sorted(pt.items()):
            tbl.append(
                f"  {qtype:<35}  {vals['n']:>5}  "
                f"{vals['recall_any@5']:>6.3f}  "
                f"{vals['recall_any@10']:>6.3f}  "
                f"{vals['ndcg_any@10']:>8.3f}"
            )

        text_block(fig, tbl, y_start=0.89, fontsize=8.2)
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        # Page 3 — Recall@k bar chart
        fig = new_fig()
        header_bar(fig, "Recall@k  (per question type)", label)
        ax = fig.add_axes([0.07, 0.08, 0.88, 0.80])

        import numpy as np

        plot_ks = [1, 5, 10, 30, 50]
        qtypes_sorted = sorted(pt.keys())
        colors = plt.cm.tab10(np.linspace(0, 1, len(qtypes_sorted)))
        x = np.arange(len(plot_ks))
        width = 0.8 / max(len(qtypes_sorted), 1)

        for i, qtype in enumerate(qtypes_sorted):
            vals = [pt[qtype].get(f"recall_any@{k}", 0) for k in plot_ks]
            offset = (i - len(qtypes_sorted) / 2 + 0.5) * width
            ax.bar(x + offset, vals, width * 0.9, label=qtype, color=colors[i], alpha=0.85)

        # Overall recall line
        overall = [agg[f"recall_any@{k}"] for k in plot_ks]
        ax.plot(x, overall, "k--o", linewidth=2, markersize=6, label="Overall", zorder=5)

        ax.set_xticks(x)
        ax.set_xticklabels([f"@{k}" for k in plot_ks])
        ax.set_ylim(0, 1.05)
        ax.set_ylabel("Recall (any)")
        ax.set_title(f"Recall@k by Question Type  —  {label}", fontsize=11)
        ax.legend(loc="lower right", fontsize=7)
        ax.grid(axis="y", alpha=0.3)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        # Page 4 — Miss analysis
        fig = new_fig()
        header_bar(fig, "Miss Analysis  (@k=10)", label)

        miss_lines = [
            "## Questions with zero sessions in top-10",
            "",
            f"  Total misses  :  {len(miss_ids)} / {n}  ({len(miss_ids) / n:.1%})",
            f"  Coverage      :  {(n - len(miss_ids)) / n:.1%} of questions have ≥ 1 correct session in top-10",
            "",
        ]
        if miss_ids:
            miss_lines.append("## Missed Question IDs")
            miss_lines.append("")
            for qid in miss_ids[:60]:
                miss_lines.append(f"  {qid}")
            if len(miss_ids) > 60:
                miss_lines.append(f"  … {len(miss_ids) - 60} more")
        else:
            miss_lines.append("  No misses at k=10 — perfect recall!")

        text_block(fig, miss_lines, y_start=0.89, fontsize=8.2)

        fig.text(
            0.5,
            0.015,
            f"memory_kg @ {short_hash}  |  {generated}  |  {MACHINE_DESCRIPTION}",
            ha="center",
            fontsize=7,
            color="#888888",
            fontfamily=MONO,
        )
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        d = pdf.infodict()
        d["Title"] = f"MemoryKG LongMemEval Benchmark — {label}"
        d["Author"] = "Eric G. Suchanek, PhD"
        d["Subject"] = "MemoryKG retrieval benchmark against LongMemEval"
        d["Keywords"] = "memory, knowledge graph, retrieval, LongMemEval, benchmark"
        d["Creator"] = f"memory_kg render_results @ {short_hash}"

    return pdf_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render MemoryKG LongMemEval benchmark results to Markdown (+ optional PDF)"
    )
    parser.add_argument(
        "jsonl",
        nargs="+",
        help="One or more JSONL result files produced by longmemeval_memkg.py run",
    )
    parser.add_argument(
        "--labels",
        default=None,
        help="Comma-separated display labels for each run (defaults to stem of file name)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help=(
            "Output Markdown path. Defaults to benchmarks/BENCHMARKS_MEMKG.md "
            "(single run) or benchmarks/BENCHMARKS_COMPARISON.md (multi-run)."
        ),
    )
    parser.add_argument(
        "--pdf",
        action="store_true",
        help="Also generate a PDF report alongside the Markdown (requires matplotlib)",
    )
    args = parser.parse_args()

    paths = [Path(p).resolve() for p in args.jsonl]
    for p in paths:
        if not p.exists():
            sys.exit(f"ERROR: file not found: {p}")

    labels: list[str] = []
    if args.labels:
        labels = [lbl.strip() for lbl in args.labels.split(",")]
        if len(labels) != len(paths):
            sys.exit(f"ERROR: --labels has {len(labels)} entries but {len(paths)} files were given")
    else:
        labels = [_label_from_path(p) for p in paths]

    git_info = _git_info()
    bench_dir = REPO_ROOT / "benchmarks"

    if len(paths) == 1:
        path = paths[0]
        label = labels[0]
        out_md = Path(args.out) if args.out else bench_dir / "BENCHMARKS_MEMKG.md"

        rows = _load(path)
        meta = _load_meta(path)
        print(f"  Loaded {len(rows)} results from {path.name}")

        md_path = write_markdown(rows, label, path, out_md, git_info, meta=meta)
        print(f"  Markdown : {md_path}")

        if args.pdf:
            pdf_path = _write_pdf(rows, label, path, out_md, git_info)
            if pdf_path:
                print(f"  PDF      : {pdf_path}")

    else:
        out_md = Path(args.out) if args.out else bench_dir / "BENCHMARKS_COMPARISON.md"
        runs: list[tuple[str, list[dict]]] = []
        for label, path in zip(labels, paths):
            rows = _load(path)
            print(f"  Loaded {len(rows)} results from {path.name}  (label={label})")
            runs.append((label, rows))

        md_path = write_comparison_markdown(runs, out_md, git_info)
        print(f"  Markdown : {md_path}")

        if args.pdf:
            for label, rows in runs:
                pdf_out = out_md.with_name(f"BENCHMARKS_{label}.md")
                pdf_path = _write_pdf(rows, label, paths[labels.index(label)], pdf_out, git_info)
                if pdf_path:
                    print(f"  PDF ({label}): {pdf_path}")


if __name__ == "__main__":
    main()
