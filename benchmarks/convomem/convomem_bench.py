#!/usr/bin/env python3
"""
MemoryKG × ConvoMem Benchmark
==============================

Evaluates MemoryKG retrieval against the ConvoMem benchmark.
75,336 QA pairs across 6 evidence categories.

For each evidence item:
1. Write all conversations to a temp corpus directory (one .md per conversation)
2. Build a fresh MemoryKG (heading chunks, shared embedder)
3. Query with the question
4. Check if any retrieved node text contains the evidence messages

Since ConvoMem has 75K items across many files, we sample a subset for benchmarking.
Downloads evidence files from HuggingFace on first run.

Usage:
    python benchmarks/convomem/convomem_bench.py                          # sample 100 items
    python benchmarks/convomem/convomem_bench.py --limit 500              # sample 500 items
    python benchmarks/convomem/convomem_bench.py --category user_evidence  # one category only
    python benchmarks/convomem/convomem_bench.py --k 20                   # wider retrieval
    python benchmarks/convomem/convomem_bench.py --hop 0                  # pure semantic only
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import ssl
import sys
import tempfile
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Bypass SSL for restricted environments
ssl._create_default_https_context = ssl._create_unverified_context

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from memory_kg.index import SentenceTransformerEmbedder
from memory_kg.kg import MemoryKG
from memory_kg.memorykg import DEFAULT_MODEL
from memory_kg.store import DEFAULT_RELS

HF_BASE = "https://huggingface.co/datasets/Salesforce/ConvoMem/resolve/main/core_benchmark/evidence_questions"

CATEGORIES = {
    "user_evidence": "User Facts",
    "assistant_facts_evidence": "Assistant Facts",
    "changing_evidence": "Changing Facts",
    "abstention_evidence": "Abstention",
    "preference_evidence": "Preferences",
    "implicit_connection_evidence": "Implicit Connections",
}

#: Full-size item counts per (tier, category), as published in
#: ``BENCHMARKS_CONVOMEM.md``. A category absent from a tier's map genuinely does
#: not exist upstream at that evidence depth -- tier 3 has no Preferences, and
#: tier 4 has only User/Assistant/Changing Facts.
#:
#: This manifest exists because the corpus is fetched over the network at run
#: time and ``discover_files`` returns ``[]`` on *any* failure. Without it, a rate
#: limit or timeout on a category that really does exist silently drops that
#: category, and the reported recall becomes an average over a smaller,
#: differently-composed set -- indistinguishable in the output from the benign
#: case of a category that was never there. Dropping tier-1 Preferences (R=0.960,
#: below the tier mean) would move the headline *up*.
TIER_ITEM_COUNTS: dict[int, dict[str, int]] = {
    1: {
        "user_evidence": 100,
        "assistant_facts_evidence": 100,
        "abstention_evidence": 100,
        "preference_evidence": 100,
        "implicit_connection_evidence": 100,
    },
    2: {
        "user_evidence": 100,
        "assistant_facts_evidence": 100,
        "changing_evidence": 100,
        "abstention_evidence": 100,
        "preference_evidence": 97,
        "implicit_connection_evidence": 100,
    },
    3: {
        "user_evidence": 100,
        "assistant_facts_evidence": 100,
        "changing_evidence": 100,
        "abstention_evidence": 100,
        "implicit_connection_evidence": 100,
    },
    4: {
        "user_evidence": 100,
        "assistant_facts_evidence": 100,
        "changing_evidence": 100,
    },
}


# =============================================================================
# DATA LOADING
# =============================================================================


def download_evidence_file(category, subpath, cache_dir):
    """Download a single evidence file from HuggingFace."""
    url = f"{HF_BASE}/{category}/{subpath}"
    cache_path = os.path.join(cache_dir, category, subpath.replace("/", "_"))
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)

    if os.path.exists(cache_path):
        with open(cache_path) as f:
            return json.load(f)

    print(f"    Downloading: {category}/{subpath}...")
    try:
        urllib.request.urlretrieve(url, cache_path)
        with open(cache_path) as f:
            return json.load(f)
    except Exception as e:
        print(f"    Failed to download {url}: {e}")
        return None


def discover_files(category, cache_dir, tier: int = 1):
    """Discover available files for a category via HuggingFace API."""
    tier_dir = f"{tier}_evidence"
    api_url = (
        f"https://huggingface.co/api/datasets/Salesforce/ConvoMem/tree/main"
        f"/core_benchmark/evidence_questions/{category}/{tier_dir}"
    )
    cache_path = os.path.join(cache_dir, f"{category}_tier{tier}_filelist.json")

    if os.path.exists(cache_path):
        with open(cache_path) as f:
            return json.load(f)

    try:
        req = urllib.request.Request(api_url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            files = json.loads(resp.read())
            paths = [
                f["path"].split(f"{category}/")[1] for f in files if f["path"].endswith(".json")
            ]
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, "w") as f:
                json.dump(paths, f)
            return paths
    except Exception as e:
        print(f"    Failed to list files for {category} tier {tier}: {e}")
        return []


def expected_counts(categories, limit, tier: int) -> dict[str, int]:
    """Return the item count each *category* must yield at *tier*, given *limit*.

    Categories that genuinely do not exist at this tier are omitted, so callers
    can tell "absent upstream" apart from "failed to fetch".

    :param categories: Category keys requested by the caller.
    :param limit: Per-category cap from the CLI.
    :param tier: Evidence tier (1-4).
    :return: Mapping of category key to required item count.
    """
    known = TIER_ITEM_COUNTS.get(tier, {})
    return {c: min(limit, known[c]) for c in categories if c in known}


def load_evidence_items(categories, limit, cache_dir, tier: int = 1):
    """Load evidence items from specified categories.

    Verifies the loaded set against :data:`TIER_ITEM_COUNTS` and raises rather
    than quietly averaging recall over whatever happened to download. See that
    constant for why.

    :raises RuntimeError: If a category that exists at this tier yields no files,
        or if any category returns fewer items than the tier manifest requires.
    """
    expected = expected_counts(categories, limit, tier)
    all_items = []
    loaded: dict[str, int] = {}

    for category in categories:
        files = discover_files(category, cache_dir, tier=tier)
        if not files:
            if category in expected:
                raise RuntimeError(
                    f"{CATEGORIES.get(category, category)} ({category}) exists at tier {tier} "
                    f"but no files could be listed — expected {expected[category]} items. "
                    "This is a fetch failure, not an empty category; the corpus is downloaded "
                    "from HuggingFace at run time. Retry, or check network access. Refusing to "
                    "report recall over an incomplete set."
                )
            print(f"  Skipping {category} — not present at tier {tier}")
            continue

        items_for_cat = []
        for fpath in files:
            if len(items_for_cat) >= limit:
                break
            data = download_evidence_file(category, fpath, cache_dir)
            if data and "evidence_items" in data:
                for item in data["evidence_items"]:
                    item["_category_key"] = category
                    items_for_cat.append(item)

        got = items_for_cat[:limit]
        all_items.extend(got)
        loaded[category] = len(got)
        print(f"  {CATEGORIES.get(category, category)}: {len(got)} items loaded")

    # Guard both directions. A short count shrinks the recall denominator; an
    # unexpected category grows it. Either way the reported number is no longer
    # over the set the published figures describe.
    mismatch = {c: (loaded.get(c, 0), n) for c, n in expected.items() if loaded.get(c, 0) != n}
    mismatch.update({c: (n, 0) for c, n in loaded.items() if c not in expected})
    if mismatch:
        detail = ", ".join(f"{c}: got {g}, expected {e}" for c, (g, e) in sorted(mismatch.items()))
        raise RuntimeError(
            f"tier {tier} item counts do not match the manifest ({detail}). "
            "This changes the recall denominator; refusing to report a number over a "
            "set that is not the one the published figures describe. If the upstream "
            "dataset genuinely changed, update TIER_ITEM_COUNTS deliberately."
        )

    return all_items


# =============================================================================
# CORPUS FORMATTING
# =============================================================================


def _format_conversation_markdown(conv_idx: int, messages: list[dict]) -> str:
    """Render a ConvoMem conversation as a Markdown document."""
    lines: list[str] = [f"# Conversation {conv_idx}", ""]
    for msg in messages:
        speaker = msg.get("speaker", "speaker").capitalize()
        text = (msg.get("text") or "").strip()
        if not text:
            continue
        lines.append(f"## {speaker}")
        lines.append("")
        lines.append(text)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_item_corpus(item: dict, corpus_dir: Path) -> None:
    """Write all conversations for one evidence item as Markdown files."""
    corpus_dir.mkdir(parents=True, exist_ok=True)
    for conv_idx, conv in enumerate(item.get("conversations", [])):
        messages = conv.get("messages", [])
        if not messages:
            continue
        md = _format_conversation_markdown(conv_idx, messages)
        (corpus_dir / f"conv_{conv_idx:04d}.md").write_text(md, encoding="utf-8")


# =============================================================================
# RETRIEVAL
# =============================================================================


def retrieve_for_item(
    item: dict,
    embedder: SentenceTransformerEmbedder,
    top_k: int = 10,
    hop: int = 1,
    rels: tuple[str, ...] = DEFAULT_RELS,
) -> tuple[float, dict]:
    """
    Build a per-item MemoryKG, query it, and return recall.

    :return: (recall, details_dict)
    """
    question = item["question"]
    evidence_messages = item.get("message_evidences", [])
    evidence_texts = {e["text"].strip().lower() for e in evidence_messages}

    # Count total messages so we know if corpus is empty
    total_msgs = sum(len(conv.get("messages", [])) for conv in item.get("conversations", []))
    if total_msgs == 0:
        return 1.0, {"error": "empty corpus"}

    tmpdir = Path(tempfile.mkdtemp(prefix="memorykg_convomem_"))
    corpus_dir = tmpdir / "corpus"
    kg_dir = tmpdir / ".memorykg"

    try:
        write_item_corpus(item, corpus_dir)

        kg = MemoryKG(
            corpus_root=corpus_dir,
            db_path=kg_dir / "graph.sqlite",
            vectors_path=kg_dir / "vectors.sqlite",
            chunk_strategy="heading",
            enable_topics=False,
            enable_entities=False,
            enable_keywords=False,
            emit_cooccur=False,
            embedder=embedder,
        )
        with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
            kg.build(wipe=True, batch_size=512, discover_similar=False, n_workers=1)

        result = kg.query(question, k=top_k, hop=hop, rels=rels)

        found = 0
        for ev_text in evidence_texts:
            for node in result.nodes:
                node_text = (node.get("text") or "").strip().lower()
                if node_text and (ev_text in node_text or node_text in ev_text):
                    found += 1
                    break

        recall = found / len(evidence_texts) if evidence_texts else 1.0
        return recall, {
            "retrieved_nodes": result.returned_nodes,
            "evidence_count": len(evidence_texts),
            "found": found,
        }

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# =============================================================================
# BENCHMARK RUNNER
# =============================================================================


def run_benchmark(
    categories: list[str],
    limit_per_cat: int,
    top_k: int,
    hop: int,
    rels: tuple[str, ...],
    cache_dir: str,
    out_file: str | None,
    model: str,
    tier: int = 1,
) -> None:
    """Run the ConvoMem retrieval benchmark."""

    print(f"\n{'=' * 60}")
    print("  MemoryKG × ConvoMem Benchmark")
    print(f"{'=' * 60}")
    print(f"  Categories:  {len(categories)}")
    print(f"  Limit/cat:   {limit_per_cat}")
    print(f"  Tier:        {tier}_evidence")
    print(f"  Top-k:       {top_k}")
    print(f"  Hop:         {hop}")
    print(f"  Model:       {model}")
    print(f"{'─' * 60}")
    print("\n  Loading data from HuggingFace...\n")

    items = load_evidence_items(categories, limit_per_cat, cache_dir, tier=tier)

    print(f"\n  Total items: {len(items)}")
    print(f"{'─' * 60}")
    print("  Initialising shared embedder...")
    embedder = SentenceTransformerEmbedder(model)
    print("  Embedder ready.\n")

    all_recall: list[float] = []
    per_category: dict[str, list[float]] = defaultdict(list)
    results_log: list[dict] = []
    start_time = datetime.now()

    for i, item in enumerate(items):
        question = item["question"]
        answer = item.get("answer", "")
        cat_key = item.get("_category_key", "unknown")

        recall, details = retrieve_for_item(item, embedder, top_k=top_k, hop=hop, rels=rels)
        all_recall.append(recall)
        per_category[cat_key].append(recall)

        results_log.append(
            {
                "question": question,
                "answer": answer,
                "category": cat_key,
                "recall": recall,
                "details": details,
            }
        )

        status = "HIT" if recall >= 1.0 else ("part" if recall > 0 else "miss")
        if (i + 1) % 10 == 0 or i == len(items) - 1:
            avg = sum(all_recall) / len(all_recall)
            print(f"  [{i + 1:4}/{len(items)}] avg_recall={avg:.3f}  last={status}")

    elapsed = (datetime.now() - start_time).total_seconds()
    avg_recall = sum(all_recall) / len(all_recall) if all_recall else 0

    print(f"\n{'=' * 60}")
    print(f"  RESULTS — MemoryKG (top-{top_k}, hop={hop})")
    print(f"{'=' * 60}")
    print(f"  Time:        {elapsed:.1f}s ({elapsed / max(len(items), 1):.2f}s per item)")
    print(f"  Items:       {len(items)}")
    print(f"  Avg Recall:  {avg_recall:.3f}")

    print("\n  PER-CATEGORY RECALL:")
    for cat_key in sorted(per_category.keys()):
        vals = per_category[cat_key]
        avg = sum(vals) / len(vals)
        name = CATEGORIES.get(cat_key, cat_key)
        perfect = sum(1 for v in vals if v >= 1.0)
        print(f"    {name:25} R={avg:.3f}  perfect={perfect}/{len(vals)}")

    if not all_recall:
        print("\n  No items evaluated.")
        return
    perfect_total = sum(1 for r in all_recall if r >= 1.0)
    zero_total = sum(1 for r in all_recall if r == 0)
    print("\n  DISTRIBUTION:")
    print(f"    Perfect (1.0):  {perfect_total:4} ({perfect_total / len(all_recall) * 100:.1f}%)")
    print(f"    Zero (0.0):     {zero_total:4} ({zero_total / len(all_recall) * 100:.1f}%)")

    print(f"\n{'=' * 60}\n")

    if out_file:
        with open(out_file, "w") as f:
            json.dump(results_log, f, indent=2)
        print(f"  Results saved to: {out_file}")


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MemoryKG × ConvoMem Benchmark")
    parser.add_argument("--limit", type=int, default=100, help="Items per category (default: 100)")
    parser.add_argument("--k", type=int, default=10, help="Top-k semantic seeds (default: 10)")
    parser.add_argument("--hop", type=int, default=1, help="Graph expansion hops (default: 1)")
    parser.add_argument(
        "--rels",
        default=None,
        help="Comma-separated edge types to expand (default: MemoryKG defaults)",
    )
    parser.add_argument(
        "--category",
        choices=list(CATEGORIES.keys()) + ["all"],
        default="all",
        help="Category to test (default: all)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Sentence-transformer model (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--tier",
        type=int,
        default=1,
        help="Evidence tier (1–6; changing_evidence starts at 2; default: 1)",
    )
    parser.add_argument("--cache-dir", default="/tmp/convomem_cache", help="Cache directory")
    parser.add_argument("--out", default=None, help="Output JSON file")
    args = parser.parse_args()

    if args.category == "all":
        categories = list(CATEGORIES.keys())
    else:
        categories = [args.category]

    if args.rels:
        rels = tuple(r.strip() for r in args.rels.split(",") if r.strip())
    else:
        rels = DEFAULT_RELS

    if not args.out:
        args.out = (
            f"benchmarks/convomem/results_convomem_tier{args.tier}_top{args.k}_hop{args.hop}"
            f"_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        )

    run_benchmark(
        categories,
        args.limit,
        args.k,
        args.hop,
        rels,
        args.cache_dir,
        args.out,
        args.model,
        tier=args.tier,
    )
