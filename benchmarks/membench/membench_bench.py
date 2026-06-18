#!/usr/bin/env python3
"""
MemoryKG × MemBench Benchmark
==============================

MemBench (ACL 2025): https://aclanthology.org/2025.findings-acl.989/
Data: https://github.com/import-myself/Membench

11 multi-turn conversation memory categories:
  simple, highlevel, knowledge_update, comparative, conditional,
  noisy, aggregative, highlevel_rec, lowlevel_rec, RecMultiSession, post_processing

Architecture:

    prepare  →  download JSON files, write one Markdown file per item,
                build ONE persistent MemoryKG over the entire corpus

    run      →  open the pre-built KG; per item, query with haystack_files
                restricted to that item's file; score via target-turn text matching

    all      →  prepare + run in one pass

Usage
-----

Step 1 — download data + build KG (once per topic/category set):

    python benchmarks/membench/membench_bench.py prepare
    python benchmarks/membench/membench_bench.py prepare --topic all --wipe

Step 2 — run the benchmark (reuses the built KG):

    python benchmarks/membench/membench_bench.py run
    python benchmarks/membench/membench_bench.py run --category highlevel --k 20 --hop 1

All-in-one:

    python benchmarks/membench/membench_bench.py all
    python benchmarks/membench/membench_bench.py all --topic movie --limit 200

Author: Eric G. Suchanek, PhD
Last Revision: 2026-04-25

License: Elastic 2.0
"""

from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ssl._create_default_https_context = ssl._create_unverified_context

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from memory_kg.index import SentenceTransformerEmbedder
from memory_kg.kg import MemoryKG
from memory_kg.memorykg import DEFAULT_MODEL
from memory_kg.store import DEFAULT_RELS

# =============================================================================
# PATHS & CONSTANTS
# =============================================================================

_BENCH_DIR = REPO_ROOT / "benchmarks" / "membench"
_DATA_DIR = _BENCH_DIR / "data"

_GITHUB_BASE = "https://raw.githubusercontent.com/import-myself/Membench/main/MemData/FirstAgent"

CATEGORY_FILES: dict[str, str] = {
    "simple": "simple.json",
    "highlevel": "highlevel.json",
    "knowledge_update": "knowledge_update.json",
    "comparative": "comparative.json",
    "conditional": "conditional.json",
    "noisy": "noisy.json",
    "aggregative": "aggregative.json",
    "highlevel_rec": "highlevel_rec.json",
    "lowlevel_rec": "lowlevel_rec.json",
    "RecMultiSession": "RecMultiSession.json",
    "post_processing": "post_processing.json",
}

ALL_TOPICS = ("movie", "food", "book")


def _corpus_dir(tag: str) -> Path:
    return _DATA_DIR / f"membench_corpus_{tag}"


def _kg_db(tag: str) -> Path:
    return _DATA_DIR / f".memorykg_{tag}" / "graph.sqlite"


def _kg_lancedb(tag: str) -> Path:
    return _DATA_DIR / f".memorykg_{tag}" / "lancedb"


def _cache_dir() -> Path:
    return _DATA_DIR / "cache"


def _corpus_tag(topic: str, categories: list[str]) -> str:
    """Short stable tag used to name corpus / KG directories."""
    cats = "all" if set(categories) == set(CATEGORY_FILES) else "_".join(sorted(categories))
    return f"{topic}_{cats}"


# =============================================================================
# DATA DOWNLOAD
# =============================================================================


def download_category_file(filename: str) -> dict | None:
    """Download one MemBench JSON file from GitHub, caching under _DATA_DIR/cache/."""
    cache_path = _cache_dir() / filename
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    if cache_path.exists():
        with open(cache_path) as fh:
            return json.load(fh)

    url = f"{_GITHUB_BASE}/{filename}"
    print(f"    Downloading: {filename}  ({url})")
    try:
        urllib.request.urlretrieve(url, cache_path)
        with open(cache_path) as fh:
            return json.load(fh)
    except (urllib.error.URLError, OSError) as exc:
        print(f"    Failed: {exc}")
        return None


# =============================================================================
# DATA LOADING
# =============================================================================


def load_membench(
    categories: list[str],
    topic: str,
    limit_per_cat: int,
) -> list[dict]:
    """
    Download (if needed) and load MemBench items.

    :param categories: List of category names to include.
    :param topic: Topic filter — one of 'movie', 'food', 'book', or '' for all.
    :param limit_per_cat: Max items per category (0 = unlimited).
    :return: Flat list of item dicts.
    """
    all_items: list[dict] = []

    for cat in categories:
        fname = CATEGORY_FILES.get(cat)
        if not fname:
            continue
        data = download_category_file(fname)
        if data is None:
            print(f"  Skipping {cat} — download failed")
            continue

        cat_items: list[dict] = []
        for t, topic_items in data.items():
            if topic and t not in (topic, "roles", "events"):
                continue
            for item in topic_items:
                turns = item.get("message_list", [])
                qa = item.get("QA", {})
                if not turns or not qa:
                    continue
                cat_items.append(
                    {
                        "category": cat,
                        "topic": t,
                        "tid": item.get("tid", 0),
                        "turns": turns,
                        "question": qa.get("question", ""),
                        "choices": qa.get("choices", {}),
                        "ground_truth": qa.get("ground_truth", ""),
                        "answer_text": qa.get("answer", ""),
                        "target_step_ids": qa.get("target_step_id", []),
                    }
                )

        if limit_per_cat > 0:
            cat_items = cat_items[:limit_per_cat]

        all_items.extend(cat_items)
        print(f"  {cat}: {len(cat_items)} items")

    return all_items


# =============================================================================
# CORPUS FORMATTING
# =============================================================================


def _normalise_sessions(message_list: list) -> list[list[dict]]:
    """Return list-of-sessions regardless of whether message_list is flat or nested."""
    if message_list and isinstance(message_list[0], dict):
        return [message_list]
    return [s for s in message_list if isinstance(s, list)]


def _format_turns_markdown(message_list: list) -> str:
    """Render MemBench turns as heading-chunked Markdown for MemoryKG."""
    sessions = _normalise_sessions(message_list)
    lines: list[str] = []
    global_idx = 0

    for s_idx, session in enumerate(sessions):
        lines.append(f"# Session {s_idx + 1}")
        lines.append("")
        for turn in session:
            if not isinstance(turn, dict):
                continue
            global_idx += 1
            lines.append(f"## Turn {global_idx}")
            lines.append("")
            time_val = (turn.get("time") or "").strip()
            place_val = (turn.get("place") or "").strip()
            if time_val:
                lines.append(f"Time: {time_val}")
            if place_val:
                lines.append(f"Place: {place_val}")
            if time_val or place_val:
                lines.append("")
            user = (turn.get("user") or turn.get("user_message") or "").strip()
            asst = (turn.get("assistant") or turn.get("assistant_message") or "").strip()
            if user:
                lines.append(f"User: {user}")
                lines.append("")
            if asst:
                lines.append(f"Assistant: {asst}")
                lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _item_filename(category: str, topic: str, idx: int) -> str:
    """Stable corpus filename for a MemBench item."""
    safe_topic = re.sub(r"[^a-zA-Z0-9_-]", "_", topic)
    return f"{category}__{safe_topic}__{idx:06d}.md"


def write_corpus(
    items: list[dict],
    corpus_dir: Path,
    force: bool = False,
) -> list[str]:
    """
    Write one Markdown file per item into corpus_dir.

    :return: List of filenames (corpus-relative) in item order.
    """
    corpus_dir.mkdir(parents=True, exist_ok=True)
    existing = {p.name for p in corpus_dir.glob("*.md")}

    written = skipped = 0
    filenames: list[str] = []

    for i, item in enumerate(items):
        fname = _item_filename(item["category"], item["topic"], i)
        filenames.append(fname)
        if force or fname not in existing:
            (corpus_dir / fname).write_text(_format_turns_markdown(item["turns"]), encoding="utf-8")
            written += 1
        else:
            skipped += 1

    print(f"  Corpus: {len(items)} files ({written} written, {skipped} reused) → {corpus_dir}")
    return filenames


# =============================================================================
# KG BUILD
# =============================================================================


def build_kg(
    corpus_dir: Path,
    db_path: Path,
    lancedb_dir: Path,
    *,
    wipe: bool = True,
    model: str | None = None,
    batch_size: int = 512,
    n_workers: int = 8,
    embedder: SentenceTransformerEmbedder | None = None,
) -> None:
    """Build a persistent MemoryKG from the corpus directory."""
    print(f"  Building MemoryKG ({'wipe' if wipe else 'incremental'})...")
    print(f"    corpus:  {corpus_dir}")
    print(f"    sqlite:  {db_path}")
    print(f"    lancedb: {lancedb_dir}")
    print(f"    model:   {model or DEFAULT_MODEL}")
    print(f"    workers: {n_workers}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    lancedb_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    kg = MemoryKG(
        corpus_root=corpus_dir,
        db_path=db_path,
        lancedb_dir=lancedb_dir,
        chunk_strategy="heading",
        enable_topics=False,
        enable_entities=False,
        enable_keywords=False,
        emit_cooccur=False,
        model=model or DEFAULT_MODEL,
        embedder=embedder,
    )
    try:
        stats = kg.build(
            wipe=wipe,
            batch_size=batch_size,
            discover_similar=False,
            n_workers=n_workers,
        )
    finally:
        kg.close()
    dt = time.time() - t0

    print(
        f"  Built in {dt:.1f}s → "
        f"{stats.total_nodes} nodes, {stats.total_edges} edges, "
        f"{stats.indexed_rows} indexed rows"
    )


# =============================================================================
# TARGET EVIDENCE EXTRACTION
# =============================================================================


def _build_turn_index(
    message_list: list,
) -> tuple[dict[int, tuple[str, str]], dict[int, tuple[str, str]]]:
    """Build (sid_map, global_map) mapping turn id → (user_text, asst_text)."""
    sessions = _normalise_sessions(message_list)
    sid_map: dict[int, tuple[str, str]] = {}
    global_map: dict[int, tuple[str, str]] = {}
    global_idx = 0

    for session in sessions:
        for turn in session:
            if not isinstance(turn, dict):
                continue
            user = (turn.get("user") or turn.get("user_message") or "").strip()
            asst = (turn.get("assistant") or turn.get("assistant_message") or "").strip()
            sid = turn.get("sid", turn.get("mid"))
            if sid is not None:
                key = int(sid) if isinstance(sid, (int | float)) else sid
                sid_map[key] = (user, asst)
            global_map[global_idx] = (user, asst)
            global_idx += 1

    return sid_map, global_map


def _get_target_evidence(item: dict) -> list[tuple[str, str]]:
    """
    Return one (user_text, asst_text) pair per target turn.

    Tries target_step_id's first element as an sid, then as a global index.
    """
    sid_map, global_map = _build_turn_index(item["turns"])
    evidence: list[tuple[str, str]] = []

    for step in item.get("target_step_ids", []):
        if not (isinstance(step, list) and len(step) >= 1):
            continue
        sid = step[0]
        pair = sid_map.get(sid) or global_map.get(sid)
        if pair:
            evidence.append(pair)

    return evidence


# =============================================================================
# SCORING
# =============================================================================


def score_item(
    item: dict,
    kg: MemoryKG,
    filename: str,
    *,
    k: int,
    hop: int,
    rels: tuple[str, ...],
    max_nodes: int,
    use_haystack: bool = True,
    denoise: bool = False,
) -> tuple[float, dict]:
    """
    Query MemoryKG for one item and compute recall.

    :param use_haystack: If True, restrict LanceDB seeding to the item's own file.
    :param denoise: If True, strip distractor preamble from the question before
        seeding (helps the ``noisy`` category; safe no-op elsewhere).
    :return: (recall, details_dict)
    """
    question = item["question"]
    evidence_turns = _get_target_evidence(item)

    if not evidence_turns:
        return 1.0, {"error": "no target evidence found"}

    haystack = frozenset({filename}) if use_haystack else None
    result = kg.query(
        question,
        k=k,
        hop=hop,
        rels=rels,
        max_nodes=max_nodes,
        haystack_files=haystack,
        denoise=denoise,
    )

    found = 0
    for user_text, asst_text in evidence_turns:
        u = user_text.lower()
        a = asst_text.lower()
        for node in result.nodes:
            node_text = (node.get("text") or "").strip().lower()
            if u and node_text and (u in node_text or node_text in u):
                found += 1
                break
            if a and node_text and (a in node_text or node_text in a):
                found += 1
                break

    recall = found / len(evidence_turns)
    return recall, {
        "retrieved_nodes": result.returned_nodes,
        "evidence_turns": len(evidence_turns),
        "found": found,
    }


# =============================================================================
# MARKDOWN REPORT
# =============================================================================


def _write_markdown(
    path: Path,
    meta: dict,
    per_category: dict,
    all_recall: list[float],
    elapsed: float,
    total_items: int,
) -> None:
    """Write a Markdown summary of a completed benchmark run."""
    import subprocess

    def _git(cmd: list[str]) -> str:
        try:
            return (
                subprocess.check_output(cmd, cwd=REPO_ROOT, stderr=subprocess.DEVNULL)
                .decode()
                .strip()
            )
        except Exception:
            return "unknown"

    git_hash = _git(["git", "rev-parse", "--short", "HEAD"])
    git_branch = _git(["git", "rev-parse", "--abbrev-ref", "HEAD"])

    perfect = sum(1 for r in all_recall if r >= 1.0)
    partial = sum(1 for r in all_recall if 0 < r < 1.0)
    zero = sum(1 for r in all_recall if r == 0.0)
    n = max(len(all_recall), 1)

    lines: list[str] = [
        "# MemoryKG × MemBench Benchmark Results",
        "",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"**Commit:** `{git_hash}` ({git_branch})  ",
        f"**Topic:** {meta['topic']}  ",
        f"**k (seeds):** {meta['k']}  **hop:** {meta['hop']}  ",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Items | {total_items} |",
        f"| Avg Recall | **{meta['avg_recall']:.3f}** |",
        f"| Perfect (1.0) | {perfect} ({perfect / n * 100:.1f}%) |",
        f"| Partial (0–1) | {partial} ({partial / n * 100:.1f}%) |",
        f"| Zero (0.0) | {zero} ({zero / n * 100:.1f}%) |",
        f"| Elapsed | {elapsed:.1f}s ({elapsed / max(total_items, 1):.2f}s/item) |",
        "",
        "## Per-Category Recall",
        "",
        "| Category | Recall | n |",
        "|----------|-------:|--:|",
    ]

    for cat in sorted(per_category.keys()):
        vals = per_category[cat]
        avg = sum(vals) / len(vals)
        lines.append(f"| {cat} | {avg:.3f} | {len(vals)} |")

    lines += ["", "---", "*Generated by `membench_bench.py`*", ""]
    path.write_text("\n".join(lines))


# =============================================================================
# SUBCOMMANDS
# =============================================================================


def cmd_prepare(args: argparse.Namespace) -> None:
    categories = _resolve_categories(args)
    topic = args.topic if args.topic != "all" else ""
    tag = _corpus_tag(args.topic, categories)
    corpus_dir = _corpus_dir(tag)
    db_path = _kg_db(tag)
    lancedb_dir = _kg_lancedb(tag)

    print("=" * 60)
    print("  MemoryKG × MemBench — PREPARE")
    print("=" * 60)
    print(f"  Topic:       {args.topic}")
    print(f"  Categories:  {len(categories)}")
    print(f"  Limit/cat:   {args.limit}")
    print(f"  Corpus tag:  {tag}")
    print("-" * 60)
    print("\n  Loading data...\n")

    items = load_membench(categories, topic, args.limit)
    if not items:
        sys.exit("  No items found — check --category and --topic.")

    print(f"\n  Total items: {len(items)}")
    write_corpus(items, corpus_dir, force=args.wipe)

    embedder = SentenceTransformerEmbedder(args.model or DEFAULT_MODEL)
    build_kg(
        corpus_dir,
        db_path,
        lancedb_dir,
        wipe=args.wipe,
        model=args.model,
        batch_size=args.batch,
        n_workers=args.workers,
        embedder=embedder,
    )

    print("\n  Ready. Run with:")
    print(
        f"    python {Path(__file__).resolve().relative_to(REPO_ROOT)} run "
        f"--topic {args.topic} --limit {args.limit}"
    )


def cmd_run(args: argparse.Namespace) -> None:
    categories = _resolve_categories(args)
    topic = args.topic if args.topic != "all" else ""
    tag = _corpus_tag(args.topic, categories)
    corpus_dir = _corpus_dir(tag)
    db_path = _kg_db(tag)
    lancedb_dir = _kg_lancedb(tag)

    if not db_path.exists() or not lancedb_dir.exists():
        sys.exit(
            f"ERROR: MemoryKG index not found for tag '{tag}'.\n"
            f"  Run prepare first:\n"
            f"    python {Path(__file__).resolve().relative_to(REPO_ROOT)} prepare "
            f"--topic {args.topic} --limit {args.limit}"
        )

    rels_str = (
        args.rels or "CONTAINS,NEXT,REFERENCES,SIMILAR_TO,HAS_TOPIC,MENTIONS_ENTITY,HAS_KEYWORD"
    )
    rels = tuple(r.strip() for r in rels_str.split(",") if r.strip()) or DEFAULT_RELS

    print("=" * 60)
    print("  MemoryKG × MemBench — RUN")
    print("=" * 60)
    print(f"  Topic:       {args.topic}")
    print(f"  Categories:  {len(categories)}")
    print(f"  Limit/cat:   {args.limit}")
    print(f"  k (seeds):   {args.k}")
    print(f"  hop:         {args.hop}")
    print(f"  max_nodes:   {args.max_nodes}")
    print(f"  rels:        {rels_str}")
    print("-" * 60)
    print("\n  Loading data...\n")

    items = load_membench(categories, topic, args.limit)
    if not items:
        sys.exit("  No items found.")

    print(f"\n  Total items: {len(items)}")
    print("  Generating corpus filenames...")
    filenames = [_item_filename(item["category"], item["topic"], i) for i, item in enumerate(items)]

    turn_counts = [_count_turns(item["turns"]) for item in items]
    trivial = sum(1 for n in turn_counts if n <= args.k)
    print(
        f"  Turn-count range: min={min(turn_counts)}  max={max(turn_counts)}  "
        f"median={sorted(turn_counts)[len(turn_counts) // 2]}"
    )
    print(
        f"  Items with N≤k ({args.k} turns, trivially perfect): "
        f"{trivial}/{len(items)} ({trivial / len(items) * 100:.1f}%)"
    )
    use_haystack = not getattr(args, "no_haystack", False)
    print(f"  Haystack scoping: {'ON' if use_haystack else 'OFF (ablation)'}")
    print("  Opening MemoryKG...")
    embedder = SentenceTransformerEmbedder(args.model or DEFAULT_MODEL)
    kg = MemoryKG(
        corpus_root=corpus_dir,
        db_path=db_path,
        lancedb_dir=lancedb_dir,
        model=args.model or DEFAULT_MODEL,
        embedder=embedder,
    )

    all_recall: list[float] = []
    per_category: dict[str, list[float]] = defaultdict(list)
    results_log: list[dict] = []
    start = datetime.now()

    try:
        for i, (item, fname) in enumerate(zip(items, filenames)):
            t0 = time.time()
            recall, details = score_item(
                item,
                kg,
                fname,
                k=args.k,
                hop=args.hop,
                rels=rels,
                max_nodes=args.max_nodes,
                use_haystack=use_haystack,
                denoise=getattr(args, "denoise", False),
            )
            t_q = time.time() - t0

            all_recall.append(recall)
            per_category[item["category"]].append(recall)

            results_log.append(
                {
                    "category": item["category"],
                    "topic": item["topic"],
                    "tid": item["tid"],
                    "question": item["question"],
                    "ground_truth": item["ground_truth"],
                    "answer_text": item["answer_text"],
                    "recall": recall,
                    "t_query_s": round(t_q, 3),
                    "details": details,
                }
            )

            status = "HIT" if recall >= 1.0 else ("part" if recall > 0 else "miss")
            if (i + 1) % 50 == 0 or i == len(items) - 1:
                avg = sum(all_recall) / len(all_recall)
                print(f"  [{i + 1:4}/{len(items)}] avg_recall={avg:.3f}  last={status}")

    finally:
        kg.close()

    elapsed = (datetime.now() - start).total_seconds()
    avg_recall = sum(all_recall) / len(all_recall) if all_recall else 0.0

    print(f"\n{'=' * 60}")
    print(f"  RESULTS — MemoryKG on MemBench (k={args.k}, hop={args.hop})")
    print(f"{'=' * 60}")
    print(f"  Time:        {elapsed:.1f}s ({elapsed / max(len(items), 1):.2f}s/item)")
    print(f"  Items:       {len(items)}")
    print(f"  Avg Recall:  {avg_recall:.3f}")

    print("\n  PER-CATEGORY RECALL:")
    for cat in sorted(per_category.keys()):
        vals = per_category[cat]
        avg = sum(vals) / len(vals)
        perfect = sum(1 for v in vals if v >= 1.0)
        print(f"    {cat:22} R={avg:.3f}  perfect={perfect}/{len(vals)}")

    perfect_total = sum(1 for r in all_recall if r >= 1.0)
    partial_total = sum(1 for r in all_recall if 0 < r < 1.0)
    zero_total = sum(1 for r in all_recall if r == 0.0)
    print("\n  RECALL DISTRIBUTION:")
    print(
        f"    Perfect (1.0): {perfect_total:4}  ({perfect_total / max(len(all_recall), 1) * 100:.1f}%)"
    )
    print(
        f"    Partial (0-1): {partial_total:4}  ({partial_total / max(len(all_recall), 1) * 100:.1f}%)"
    )
    print(f"    Zero (0.0):    {zero_total:4}  ({zero_total / max(len(all_recall), 1) * 100:.1f}%)")
    print(f"\n{'=' * 60}\n")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    if args.out:
        out_path = Path(args.out)
    else:
        results_dir = _BENCH_DIR / "results"
        cat_tag = f"_{args.category}" if args.category != "all" else "_all"
        out_path = (
            results_dir
            / f"membench_memkg_{args.topic}{cat_tag}_k{args.k}_hop{args.hop}_{timestamp}.jsonl"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)

    meta = {
        "_meta": True,
        "elapsed_s": round(elapsed, 1),
        "n_items": len(items),
        "s_per_item": round(elapsed / max(len(items), 1), 2),
        "topic": args.topic,
        "k": args.k,
        "hop": args.hop,
        "avg_recall": round(avg_recall, 4),
        "per_category": {cat: round(sum(v) / len(v), 4) for cat, v in sorted(per_category.items())},
    }

    with open(out_path, "w") as fh:
        fh.write(json.dumps(meta) + "\n")
        for row in results_log:
            fh.write(json.dumps(row) + "\n")
    print(f"  Results: {out_path}")

    md_path = out_path.with_suffix(".md")
    _write_markdown(md_path, meta, per_category, all_recall, elapsed, len(items))
    print(f"  Report:  {md_path}")


def cmd_all(args: argparse.Namespace) -> None:
    cmd_prepare(args)
    print()
    cmd_run(args)


# =============================================================================
# CLI HELPERS
# =============================================================================


def _count_turns(message_list: list) -> int:
    """Return the total number of turns across all sessions."""
    sessions = _normalise_sessions(message_list)
    return sum(1 for s in sessions for t in s if isinstance(t, dict))


def _resolve_categories(args: argparse.Namespace) -> list[str]:
    if args.category == "all":
        return list(CATEGORY_FILES.keys())
    return [args.category]


def _add_shared_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--topic",
        default="movie",
        choices=list(ALL_TOPICS) + ["all"],
        help="Topic filter: movie, food, book, or all (default: movie)",
    )
    p.add_argument(
        "--category",
        default="all",
        choices=list(CATEGORY_FILES.keys()) + ["all"],
        help="Category to include (default: all)",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Max items per category (0 = unlimited, default: 100)",
    )


def _add_prepare_args(p: argparse.ArgumentParser) -> None:
    _add_shared_args(p)
    p.add_argument("--wipe", action="store_true", help="Rewrite corpus and rebuild KG from scratch")
    p.add_argument("--model", default=None, help="Override sentence-transformer model")
    p.add_argument("--batch", type=int, default=512, help="Embedding batch size (default: 512)")
    p.add_argument("--workers", type=int, default=8, help="Parallel embedding workers (default: 8)")


def _add_run_args(p: argparse.ArgumentParser) -> None:
    _add_shared_args(p)
    p.add_argument(
        "--k", type=int, default=10, help="Semantic seed count before graph expansion (default: 10)"
    )
    p.add_argument("--hop", type=int, default=1, help="Graph expansion hops (default: 1)")
    p.add_argument(
        "--max-nodes",
        type=int,
        default=50,
        help="Max nodes returned by MemoryKG.query (default: 50)",
    )
    p.add_argument(
        "--rels",
        default=None,
        help="Comma-separated edge types (default: CONTAINS,NEXT,REFERENCES,...)",
    )
    p.add_argument("--model", default=None, help="Override sentence-transformer model")
    p.add_argument("--out", default=None, help="Output JSONL file path")
    p.add_argument(
        "--no-haystack",
        action="store_true",
        help="Ablation: disable per-item file scoping (global search across all items)",
    )
    p.add_argument(
        "--denoise",
        action="store_true",
        help="Strip distractor preamble from queries before seeding (helps 'noisy'; no-op elsewhere)",
    )


# =============================================================================
# MAIN
# =============================================================================


def main() -> None:
    parser = argparse.ArgumentParser(description="MemoryKG × MemBench Benchmark")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_prep = sub.add_parser("prepare", help="Download data + build persistent MemoryKG")
    _add_prepare_args(p_prep)
    p_prep.set_defaults(func=cmd_prepare)

    p_run = sub.add_parser("run", help="Query the pre-built KG and score recall")
    _add_run_args(p_run)
    p_run.set_defaults(func=cmd_run)

    p_all = sub.add_parser("all", help="prepare + run in one pass")
    _add_prepare_args(p_all)
    p_all.add_argument("--k", type=int, default=10)
    p_all.add_argument("--hop", type=int, default=1)
    p_all.add_argument("--max-nodes", type=int, default=50)
    p_all.add_argument("--rels", default=None)
    p_all.add_argument("--out", default=None)
    p_all.add_argument("--no-haystack", action="store_true")
    p_all.add_argument("--denoise", action="store_true")
    p_all.set_defaults(func=cmd_all)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
