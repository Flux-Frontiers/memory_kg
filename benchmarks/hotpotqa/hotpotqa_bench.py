#!/usr/bin/env python3
"""
MemoryKG × HotpotQA Benchmark
=============================

Evaluates MemoryKG retrieval against HotpotQA (distractor setting) — a
**multi-hop** Wikipedia QA benchmark. Unlike MemoryKG's four conversational-memory
benchmarks (LongMemEval, LoCoMo, MemBench, ConvoMem), HotpotQA tests whether the
graph can *combine facts across documents*: each question requires reasoning over
two gold paragraphs hidden among eight distractors.

This is the benchmark that directly probes the claim in Abdullah Grewal's
"AI Agents Don't Need Vector Search Anymore" (2026): that single-shot top-k
retrieval is *brittle* on multi-hop queries because the second-hop passage is
often only weakly similar to the question. MemoryKG's answer is structural
expansion — a `MENTIONS_ENTITY` edge from the strongly-matching first-hop chunk
should surface the bridge paragraph that pure cosine similarity misses.

The head-to-head the article is about falls straight out of one flag:

    --hop 0   pure semantic top-k          (the flat RAG baseline the article defends)
    --hop 1   semantic seed + graph expansion (MemoryKG's structural recovery)

For each example (distractor setting, 10 paragraphs):
1. Write each paragraph as its own Markdown file (title as H1, sentences as body)
2. Build a fresh MemoryKG (heading chunks + entity linking for the bridge edges)
3. Query with the question
4. Measure paragraph-level recall_all@N — did we retrieve *both* gold paragraphs?
   recall_all is the real multi-hop metric: getting one hop is not enough.

Data: HotpotQA dev (distractor) — `hotpot_dev_distractor_v1.json` (~46 MB, 7,405 Q).
Pass a local path, or let the script download it to the cache on first run.

Usage:
    # Download (once) then run a 200-question sample, graph expansion on
    python benchmarks/hotpotqa/hotpotqa_bench.py --limit 200

    # Explicit local file
    python benchmarks/hotpotqa/hotpotqa_bench.py /path/to/hotpot_dev_distractor_v1.json

    # The article's head-to-head: flat top-k vs graph expansion
    python benchmarks/hotpotqa/hotpotqa_bench.py --limit 200 --hop 0   # flat baseline
    python benchmarks/hotpotqa/hotpotqa_bench.py --limit 200 --hop 1   # + graph
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
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

# Official mirror (CMU) — first choice; periodically returns 503.
HOTPOT_URL = "http://curtis.ml.cmu.edu/datasets/hotpot/hotpot_dev_distractor_v1.json"
# HuggingFace mirror (distractor validation split, parquet) — robust fallback.
HOTPOT_HF_PARQUET = (
    "https://huggingface.co/datasets/hotpotqa/hotpot_qa/resolve/main/"
    "distractor/validation-00000-of-00001.parquet"
)
CHUNK_KINDS = {"chunk", "document"}


# =============================================================================
# DATA LOADING
# =============================================================================


def ensure_dataset(path: str | None, cache_dir: str) -> Path:
    """Return a local path to the HotpotQA distractor dev JSON, downloading if needed."""
    if path:
        p = Path(path).expanduser()
        if not p.exists():
            raise FileNotFoundError(f"Dataset not found: {p}")
        return p

    os.makedirs(cache_dir, exist_ok=True)
    cache_path = Path(cache_dir) / "hotpot_dev_distractor_v1.json"
    if cache_path.exists():
        return cache_path

    print(f"  Downloading HotpotQA distractor dev (~46 MB) from {HOTPOT_URL} ...")
    try:
        urllib.request.urlretrieve(HOTPOT_URL, cache_path)
        print(f"  Saved to {cache_path}")
        return cache_path
    except Exception as e:  # noqa: BLE001
        print(f"  CMU mirror unavailable ({e}); falling back to HuggingFace parquet ...")

    try:
        _download_and_convert_hf(cache_path, cache_dir)
    except Exception as e:  # noqa: BLE001
        raise SystemExit(
            f"\n  Failed to download HotpotQA from both mirrors: {e}\n"
            f"  Download it manually from https://hotpotqa.github.io and pass the\n"
            f"  path as the first positional argument, e.g.:\n"
            f"    python benchmarks/hotpotqa/hotpotqa_bench.py /tmp/hotpot_dev_distractor_v1.json\n"
        ) from e
    print(f"  Saved to {cache_path}")
    return cache_path


def _download_and_convert_hf(cache_path: Path, cache_dir: str) -> None:
    """Download the HF parquet (columnar shape) and convert to original HotpotQA JSON.

    HF stores ``supporting_facts`` as ``{"title": [...], "sent_id": [...]}`` and
    ``context`` as ``{"title": [...], "sentences": [[...], ...]}``. The original
    distractor JSON uses ``[[title, sent_id], ...]`` and ``[[title, sentences], ...]``.
    """
    import pyarrow.parquet as pq  # local import: only needed for the fallback path

    parquet_path = Path(cache_dir) / "hotpot_validation.parquet"
    if not parquet_path.exists():
        urllib.request.urlretrieve(HOTPOT_HF_PARQUET, parquet_path)

    rows = pq.read_table(parquet_path).to_pylist()
    converted = []
    for r in rows:
        sf = r["supporting_facts"]
        ctx = r["context"]
        converted.append(
            {
                "_id": r.get("id", ""),
                "question": r["question"],
                "answer": r.get("answer", ""),
                "type": r.get("type", ""),
                "level": r.get("level", ""),
                "supporting_facts": list(zip(sf["title"], sf["sent_id"])),
                "context": list(zip(ctx["title"], ctx["sentences"])),
            }
        )
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(converted, f)


def load_examples(path: Path, limit: int) -> list[dict]:
    """Load up to ``limit`` HotpotQA examples."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data[:limit] if limit else data


# =============================================================================
# CORPUS FORMATTING
# =============================================================================


def _safe_filename(title: str, idx: int) -> str:
    """Deterministic, collision-resistant filename for a paragraph title."""
    slug = re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_")[:60] or "para"
    return f"{idx:02d}_{slug}.md"


def write_example_corpus(example: dict, corpus_dir: Path) -> dict[str, str]:
    """Write each context paragraph as a Markdown file.

    :return: mapping of ``file_path`` (filename) -> paragraph title, so retrieved
        nodes can be traced back to their source paragraph.
    """
    corpus_dir.mkdir(parents=True, exist_ok=True)
    file_to_title: dict[str, str] = {}
    for idx, (title, sentences) in enumerate(example.get("context", [])):
        fname = _safe_filename(title, idx)
        body = "".join(sentences).strip()
        md = f"# {title}\n\n{body}\n"
        (corpus_dir / fname).write_text(md, encoding="utf-8")
        file_to_title[fname] = title
    return file_to_title


# =============================================================================
# RETRIEVAL
# =============================================================================


def _retrieved_titles_in_order(result, file_to_title: dict[str, str]) -> list[str]:
    """Ordered, de-duplicated list of paragraph titles for retrieved chunk nodes."""
    ordered: list[str] = []
    seen: set[str] = set()
    for node in result.nodes:
        if node.get("kind") not in CHUNK_KINDS:
            continue
        fp = node.get("file_path") or ""
        title = file_to_title.get(Path(fp).name) or node.get("title")
        if title and title not in seen:
            seen.add(title)
            ordered.append(title)
    return ordered


def retrieve_for_example(
    example: dict,
    embedder: SentenceTransformerEmbedder,
    top_k: int,
    hop: int,
    rels: tuple[str, ...],
    enable_entities: bool,
) -> dict:
    """Build a per-example MemoryKG, query it, and score multi-hop recall."""
    gold_titles = {sf[0] for sf in example.get("supporting_facts", [])}
    n_gold = len(gold_titles)

    tmpdir = Path(tempfile.mkdtemp(prefix="memorykg_hotpot_"))
    corpus_dir = tmpdir / "corpus"
    kg_dir = tmpdir / ".memorykg"

    try:
        file_to_title = write_example_corpus(example, corpus_dir)

        kg = MemoryKG(
            corpus_root=corpus_dir,
            db_path=kg_dir / "graph.sqlite",
            lancedb_dir=kg_dir / "lancedb",
            chunk_strategy="heading",
            enable_topics=False,
            enable_entities=enable_entities,
            enable_keywords=enable_entities,
            emit_cooccur=enable_entities,
            embedder=embedder,
        )
        with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
            kg.build(wipe=True, batch_size=512, discover_similar=False, n_workers=1)

        result = kg.query(example["question"], k=top_k, hop=hop, rels=rels)
        ordered = _retrieved_titles_in_order(result, file_to_title)

        # recall_all@N — did we retrieve EVERY gold paragraph within the top-N chunks?
        recall_all = {n: float(gold_titles.issubset(set(ordered[:n]))) for n in (2, 5, 10)}
        # paragraph recall@10 — fraction of gold paragraphs anywhere in retrieval
        found = len(gold_titles & set(ordered[:10]))
        para_recall = found / n_gold if n_gold else 1.0

        return {
            "question": example.get("question", ""),
            "answer": example.get("answer", ""),
            "type": example.get("type", ""),
            "level": example.get("level", ""),
            "n_gold": n_gold,
            "para_recall@10": para_recall,
            "recall_all@2": recall_all[2],
            "recall_all@5": recall_all[5],
            "recall_all@10": recall_all[10],
            "retrieved_order": ordered[:10],
            "gold": sorted(gold_titles),
        }
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# =============================================================================
# BENCHMARK RUNNER
# =============================================================================


def run_benchmark(
    dataset_path: Path,
    limit: int,
    top_k: int,
    hop: int,
    rels: tuple[str, ...],
    enable_entities: bool,
    out_file: str | None,
    model: str,
) -> None:
    """Run the HotpotQA multi-hop retrieval benchmark."""
    print(f"\n{'=' * 60}")
    print("  MemoryKG × HotpotQA Benchmark (distractor, multi-hop)")
    print(f"{'=' * 60}")
    print(f"  Dataset:   {dataset_path}")
    print(f"  Limit:     {limit}")
    print(f"  Top-k:     {top_k}")
    print(f"  Hop:       {hop}   ({'flat top-k' if hop == 0 else 'graph expansion'})")
    print(f"  Entities:  {enable_entities}")
    print(f"  Model:     {model}")
    print(f"{'─' * 60}")

    examples = load_examples(dataset_path, limit)
    print(f"  Loaded {len(examples)} examples.")
    print("  Initialising shared embedder...")
    embedder = SentenceTransformerEmbedder(model)
    print("  Embedder ready.\n")

    agg: dict[str, list[float]] = defaultdict(list)
    by_type: dict[str, list[float]] = defaultdict(list)  # recall_all@5 by question type
    by_level: dict[str, list[float]] = defaultdict(list)
    results_log: list[dict] = []
    start_time = datetime.now()

    for i, example in enumerate(examples):
        r = retrieve_for_example(example, embedder, top_k, hop, rels, enable_entities)
        for key in ("para_recall@10", "recall_all@2", "recall_all@5", "recall_all@10"):
            agg[key].append(r[key])
        by_type[r["type"] or "unknown"].append(r["recall_all@5"])
        by_level[r["level"] or "unknown"].append(r["recall_all@5"])
        results_log.append(r)

        if (i + 1) % 25 == 0 or i == len(examples) - 1:
            ra5 = sum(agg["recall_all@5"]) / len(agg["recall_all@5"])
            print(f"  [{i + 1:4}/{len(examples)}]  recall_all@5={ra5:.3f}")

    elapsed = (datetime.now() - start_time).total_seconds()
    n = len(examples)

    print(f"\n{'=' * 60}")
    print(f"  RESULTS — MemoryKG (top-{top_k}, hop={hop})")
    print(f"{'=' * 60}")
    print(f"  Time:           {elapsed:.1f}s ({elapsed / max(n, 1):.2f}s per question)")
    print(f"  Questions:      {n}")
    print(f"  Para Recall@10: {sum(agg['para_recall@10']) / n:.3f}   (per-paragraph)")
    print(f"  Recall_all@2:   {sum(agg['recall_all@2']) / n:.3f}   (both hops in top-2)")
    print(f"  Recall_all@5:   {sum(agg['recall_all@5']) / n:.3f}   (both hops in top-5)")
    print(f"  Recall_all@10:  {sum(agg['recall_all@10']) / n:.3f}   (both hops in top-10)")

    print("\n  RECALL_ALL@5 BY QUESTION TYPE:")
    for t in sorted(by_type):
        vals = by_type[t]
        print(f"    {t:14} {sum(vals) / len(vals):.3f}  (n={len(vals)})")

    print("\n  RECALL_ALL@5 BY DIFFICULTY:")
    for lvl in sorted(by_level):
        vals = by_level[lvl]
        print(f"    {lvl:14} {sum(vals) / len(vals):.3f}  (n={len(vals)})")
    print(f"\n{'=' * 60}\n")

    if out_file:
        summary = {k: sum(v) / n for k, v in agg.items()}
        with open(out_file, "w") as f:
            json.dump({"config": {"hop": hop, "k": top_k, "n": n, "model": model},
                       "summary": summary, "results": results_log}, f, indent=2)
        print(f"  Results saved to: {out_file}")


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MemoryKG × HotpotQA Benchmark")
    parser.add_argument("dataset", nargs="?", default=None,
                        help="Path to hotpot_dev_distractor_v1.json (downloads if omitted)")
    parser.add_argument("--limit", type=int, default=200, help="Number of questions (default: 200)")
    parser.add_argument("--k", type=int, default=10, help="Top-k semantic seeds (default: 10)")
    parser.add_argument("--hop", type=int, default=1,
                        help="Graph expansion hops: 0=flat top-k, 1=+graph (default: 1)")
    parser.add_argument("--rels", default=None,
                        help="Comma-separated edge types to expand (default: MemoryKG defaults)")
    parser.add_argument("--no-entities", action="store_true",
                        help="Disable entity/keyword linking (removes bridge edges for hop>0)")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Sentence-transformer model (default: {DEFAULT_MODEL})")
    parser.add_argument("--cache-dir", default="/tmp/hotpotqa_cache", help="Cache directory")
    parser.add_argument("--out", default=None, help="Output JSON file")
    args = parser.parse_args()

    rels = tuple(r.strip() for r in args.rels.split(",") if r.strip()) if args.rels else DEFAULT_RELS

    if not args.out:
        args.out = (
            f"benchmarks/hotpotqa/results_hotpot_top{args.k}_hop{args.hop}"
            f"_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        )

    dataset_path = ensure_dataset(args.dataset, args.cache_dir)
    run_benchmark(
        dataset_path,
        args.limit,
        args.k,
        args.hop,
        rels,
        not args.no_entities,
        args.out,
        args.model,
    )
