#!/usr/bin/env python3
"""
MemoryKG × LoCoMo Benchmark
============================

Evaluates MemoryKG retrieval against the LoCoMo benchmark.
10 conversations, ~200 QA pairs across 5 categories.

Architecture:

    prepare  →  one persistent corpus + one MemoryKG build per granularity
    run      →  per-conversation queries against the pre-built KG

Every session (or dialog turn, for ``--granularity dialog``) from all 10
conversations is written once as ``<sample_id>__session_N.md`` (or
``<sample_id>__D<N>-<M>.md``) under the corpus directory.  The KG is built
once over the entire corpus.  At query time, ``haystack_files`` restricts
seeding to the current conversation's files — apples-to-apples with a
per-conversation flat search.

Post-retrieval reranking:
    * Temporal boost  — for Temporal / Temporal-inference categories.
    * Ollama reranker — optional, via ``--ollama``.

Usage
-----

Step 1 — prepare corpus + build the KG (one time per granularity):

    python benchmarks/locomobench/locomo_bench_memkg.py prepare /path/to/locomo10.json
    python benchmarks/locomobench/locomo_bench_memkg.py prepare /path/to/locomo10.json \\
        --granularity dialog --wipe --workers 8

Step 2 — run the benchmark (many times — KG is reused):

    python benchmarks/locomobench/locomo_bench_memkg.py run /path/to/locomo10.json
    python benchmarks/locomobench/locomo_bench_memkg.py run /path/to/locomo10.json \\
        --granularity dialog --k 50 --hop 2

All-in-one:

    python benchmarks/locomobench/locomo_bench_memkg.py all /path/to/locomo10.json

Author: Eric G. Suchanek, PhD

License: Elastic 2.0
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from memory_kg.index import SentenceTransformerEmbedder
from memory_kg.kg import MemoryKG
from memory_kg.memorykg import DEFAULT_MODEL
from memory_kg.store import DEFAULT_RELS

# =============================================================================
# PATHS
# =============================================================================

_BENCH_DIR = REPO_ROOT / "benchmarks" / "locomobench"
_DATA_DIR = _BENCH_DIR / "data"


_LOCOMO_URL = "https://raw.githubusercontent.com/snap-research/locomo/main/data/locomo10.json"


def download_dataset(dest: Path) -> None:
    """Download locomo10.json from the snap-research GitHub repo."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  Downloading LoCoMo dataset → {dest}")
    print(f"    Source: {_LOCOMO_URL}")
    urllib.request.urlretrieve(_LOCOMO_URL, dest)
    print(f"  Downloaded: {dest.stat().st_size / 1_048_576:.1f} MB")


def _corpus_dir(granularity: str) -> Path:
    return _DATA_DIR / f"locomo_corpus_{granularity}"


def _kg_db(granularity: str) -> Path:
    return _DATA_DIR / f".memorykg_{granularity}" / "graph.sqlite"


def _kg_vectors(granularity: str) -> Path:
    return _DATA_DIR / f".memorykg_{granularity}" / "vectors.sqlite"


# =============================================================================
# CATEGORIES
# =============================================================================

CATEGORIES = {
    1: "Single-hop",
    2: "Temporal",
    3: "Temporal-inference",
    4: "Open-domain",
    5: "Adversarial",
}

TEMPORAL_CATEGORIES = {2, 3}

# =============================================================================
# CORPUS PREPARATION
# =============================================================================


def _session_filename(sample_id: str, session_num: int) -> str:
    return f"{sample_id}__session_{session_num}.md"


def _dialog_filename(sample_id: str, dia_id: str) -> str:
    """Convert dia_id like 'D3:7' → safe filename 'D3-7'."""
    safe = dia_id.replace(":", "-")
    return f"{sample_id}__{safe}.md"


def _format_session_md(sample_id: str, session_num: int, date: str, dialogs: list[dict]) -> str:
    """Render a LoCoMo session as a Markdown document with one heading per turn."""
    lines: list[str] = [
        f"# session_{session_num}",
        "",
        f"**Conversation:** {sample_id}  ",
        f"**Date:** {date}",
        "",
    ]
    for d in dialogs:
        dia_id = d.get("dia_id", f"D{session_num}:?")
        speaker = d.get("speaker", "?")
        text = d.get("text", "")
        lines.append(f"## {dia_id}")
        lines.append("")
        lines.append(f'{speaker} said, "{text}"')
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _format_dialog_md(sample_id: str, session_num: int, date: str, d: dict) -> str:
    """Render a single LoCoMo dialog turn as a Markdown document."""
    dia_id = d.get("dia_id", f"D{session_num}:?")
    speaker = d.get("speaker", "?")
    text = d.get("text", "")
    lines: list[str] = [
        f"# {dia_id}",
        "",
        f"**Conversation:** {sample_id}  ",
        f"**Session:** {session_num}  ",
        f"**Speaker:** {speaker}  ",
        f"**Date:** {date}",
        "",
        f'{speaker} said, "{text}"',
        "",
    ]
    return "\n".join(lines).rstrip() + "\n"


def write_corpus(
    data_file: Path,
    corpus_dir: Path,
    granularity: str,
    force: bool = False,
) -> dict[str, list[str]]:
    """Write LoCoMo corpus files; return mapping sample_id → list of filenames."""
    with open(data_file) as fh:
        data = json.load(fh)

    corpus_dir.mkdir(parents=True, exist_ok=True)
    existing = {p.name for p in corpus_dir.glob("*.md")}

    written = skipped = 0
    sample_files: dict[str, list[str]] = {}

    for sample in data:
        sample_id = sample.get("sample_id", "unknown")
        conversation = sample["conversation"]
        files: list[str] = []

        session_num = 1
        while True:
            sess_key = f"session_{session_num}"
            date_key = f"session_{session_num}_date_time"
            if sess_key not in conversation:
                break
            dialogs = conversation[sess_key]
            date = conversation.get(date_key, "")

            if granularity == "session":
                fname = _session_filename(sample_id, session_num)
                files.append(fname)
                if force or fname not in existing:
                    (corpus_dir / fname).write_text(
                        _format_session_md(sample_id, session_num, date, dialogs)
                    )
                    written += 1
                    existing.add(fname)
                else:
                    skipped += 1
            else:  # dialog
                for d in dialogs:
                    dia_id = d.get("dia_id", f"D{session_num}:?")
                    fname = _dialog_filename(sample_id, dia_id)
                    files.append(fname)
                    if force or fname not in existing:
                        (corpus_dir / fname).write_text(
                            _format_dialog_md(sample_id, session_num, date, d)
                        )
                        written += 1
                        existing.add(fname)
                    else:
                        skipped += 1

            session_num += 1

        sample_files[sample_id] = files

    total = written + skipped
    print(f"  Corpus: {total} files ({written} written, {skipped} reused) → {corpus_dir}")
    return sample_files


def build_kg(
    corpus_dir: Path,
    db_path: Path,
    vectors_path: Path,
    *,
    wipe: bool = True,
    model: str | None = None,
    chunk_strategy: str = "heading",
    batch_size: int = 1024,
    discover_similar: bool = False,
    n_workers: int = 8,
    embedder: SentenceTransformerEmbedder | None = None,
) -> None:
    """Build a persistent MemoryKG from the corpus directory."""
    print(f"  Building MemoryKG ({'wipe' if wipe else 'incremental'})...")
    print(f"    corpus:  {corpus_dir}")
    print(f"    sqlite:  {db_path}")
    print(f"    vectors: {vectors_path}")
    print(f"    model:   {model or DEFAULT_MODEL}")
    print(f"    chunk:   {chunk_strategy}")
    print(f"    workers: {n_workers}")
    print(f"    similar: {'yes' if discover_similar else 'no'}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    vectors_path.parent.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    kg = MemoryKG(
        corpus_root=corpus_dir,
        db_path=db_path,
        vectors_path=vectors_path,
        model=model or DEFAULT_MODEL,
        chunk_strategy=chunk_strategy,
        n_workers=n_workers,
        embedder=embedder,
    )
    try:
        stats = kg.build(
            wipe=wipe,
            batch_size=batch_size,
            discover_similar=discover_similar,
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
# RETRIEVAL HELPERS
# =============================================================================


@dataclass
class RetrievalHit:
    """One retrieved session or dialog unit."""

    unit_id: str
    rank: int
    via_node_id: str | None


def _session_id_from_file(file_path: str | None, sample_id: str) -> str | None:
    """Extract 'session_N' from a corpus-relative path like '<sample_id>__session_N.md'."""
    if not file_path:
        return None
    stem = Path(file_path).stem
    prefix = f"{sample_id}__"
    if stem.startswith(prefix):
        return stem[len(prefix) :]
    return None


def _dialog_id_from_file(file_path: str | None, sample_id: str) -> str | None:
    """Extract 'D<N>:<M>' from a corpus-relative path like '<sample_id>__D<N>-<M>.md'."""
    if not file_path:
        return None
    stem = Path(file_path).stem
    prefix = f"{sample_id}__"
    if stem.startswith(prefix):
        safe = stem[len(prefix) :]
        # Convert 'D3-7' back to 'D3:7'
        return re.sub(r"^(D\d+)-(\d+)$", r"\1:\2", safe)
    return None


def evidence_to_session_ids(evidence: list[str]) -> set[str]:
    """Map dialog-level evidence IDs like 'D3:7' → session IDs like 'session_3'."""
    sessions: set[str] = set()
    for eid in evidence:
        m = re.match(r"D(\d+):", eid)
        if m:
            sessions.add(f"session_{m.group(1)}")
    return sessions


def compute_recall(retrieved_ids: list[str], evidence_ids: set[str]) -> float:
    if not evidence_ids:
        return 1.0
    found = sum(1 for eid in evidence_ids if eid in retrieved_ids)
    return found / len(evidence_ids)


def query_units(
    kg: MemoryKG,
    question: str,
    sample_id: str,
    granularity: str,
    haystack_files: frozenset[str],
    *,
    k: int,
    hop: int,
    rels: tuple[str, ...],
    max_nodes: int,
    seed_kinds: tuple[str, ...] | None = None,
) -> list[RetrievalHit]:
    """Query MemoryKG and collapse node results to session or dialog-level hits."""
    result = kg.query(
        question,
        k=k,
        hop=hop,
        rels=rels,
        max_nodes=max_nodes,
        seed_kinds=seed_kinds,
        haystack_files=haystack_files,
    )

    id_extractor = _session_id_from_file if granularity == "session" else _dialog_id_from_file

    best: dict[str, RetrievalHit] = {}
    for rank, node in enumerate(result.nodes):
        unit_id = id_extractor(node.get("file_path"), sample_id)
        if unit_id is None:
            continue
        if unit_id not in best or rank < best[unit_id].rank:
            best[unit_id] = RetrievalHit(
                unit_id=unit_id,
                rank=rank,
                via_node_id=node.get("id"),
            )

    return sorted(best.values(), key=lambda h: h.rank)


# =============================================================================
# RERANKERS
# =============================================================================

_TEMPORAL_PATTERNS: list[tuple[re.Pattern, int, int]] = [
    (re.compile(r"(\d+)\s+days?\s+ago", re.I), 0, 3),
    (re.compile(r"a\s+couple\s+of\s+days?\s+ago", re.I), 2, 3),
    (re.compile(r"a\s+week\s+ago", re.I), 7, 5),
    (re.compile(r"(\d+)\s+weeks?\s+ago", re.I), 0, 7),
    (re.compile(r"last\s+week", re.I), 7, 5),
    (re.compile(r"a\s+month\s+ago", re.I), 30, 10),
    (re.compile(r"(\d+)\s+months?\s+ago", re.I), 0, 14),
    (re.compile(r"last\s+month", re.I), 30, 10),
    (re.compile(r"recently", re.I), 14, 14),
]


def _parse_time_offset(question: str) -> tuple[int, int] | None:
    for pat, offset, window in _TEMPORAL_PATTERNS:
        m = pat.search(question)
        if m:
            if offset == 0 and m.lastindex:
                n = int(m.group(1))
                if "month" in m.group(0).lower():
                    return n * 30, 14
                elif "week" in m.group(0).lower():
                    return n * 7, 7
                else:
                    return n, 3
            return offset, window
    return None


def _temporal_rerank(
    hits: list[RetrievalHit],
    question: str,
    session_dates: dict[str, str],
    reference_date: str | None,
    max_boost: float = 0.40,
) -> list[RetrievalHit]:
    """Boost hits whose date is close to the temporal reference in the question."""
    if not reference_date or not session_dates:
        return hits
    parsed = _parse_time_offset(question)
    if parsed is None:
        return hits

    offset_days, window_days = parsed
    try:
        ref = datetime.strptime(reference_date[:10], "%Y-%m-%d")
    except ValueError:
        return hits
    target = ref - timedelta(days=offset_days)

    scored: list[tuple[float, RetrievalHit]] = []
    for h in hits:
        dist = float(h.rank)
        date_str = session_dates.get(h.unit_id)
        if date_str:
            try:
                s_date = datetime.strptime(date_str[:10], "%Y-%m-%d")
                days_diff = abs((s_date - target).days)
                boost = max(0.0, max_boost * (1.0 - days_diff / max(window_days, 1)))
                dist *= 1.0 - boost
            except ValueError:
                pass
        scored.append((dist, h))

    scored.sort(key=lambda x: x[0])
    return [h for _, h in scored]


def _ollama_rerank(
    hits: list[RetrievalHit],
    question: str,
    unit_texts: dict[str, str],
    *,
    top_n: int = 20,
    model: str = "qwen3:4b-instruct",
    ollama_url: str = "http://localhost:11434",
) -> list[RetrievalHit]:
    """Use a local Ollama model to rerank the top-N candidates."""
    candidates = hits[:top_n]
    rest = hits[top_n:]
    if not candidates:
        return hits

    snippets = []
    for i, h in enumerate(candidates):
        text = (unit_texts.get(h.unit_id) or "")[:400].replace("\n", " ")
        snippets.append(f"Session {i + 1}: {text}")

    prompt = (
        f"Question: {question}\n\n"
        f"Which session is most likely to contain the answer? "
        f"Reply with ONLY a number between 1 and {len(candidates)}.\n\n"
        + "\n\n".join(snippets)
        + "\n\nMost relevant session number:"
    )

    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    req = urllib.request.Request(
        f"{ollama_url}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
        raw = result.get("response", "").strip()
        m = re.search(r"\d+", raw)
        if m:
            pick = int(m.group()) - 1
            if 0 <= pick < len(candidates):
                reranked = [candidates[pick]] + [h for j, h in enumerate(candidates) if j != pick]
                return reranked + rest
    except (urllib.error.URLError, OSError, KeyError, ValueError):
        pass
    return hits


# =============================================================================
# MARKDOWN REPORT
# =============================================================================


def _write_markdown(
    path: Path,
    meta: dict,
    per_category: dict,
    all_recall: list[float],
    elapsed: float,
    total_qa: int,
) -> None:
    """Write a Markdown summary of a completed benchmark run."""
    import subprocess

    def _git(cmd):
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
    gran = meta["granularity"]

    lines: list[str] = [
        "# MemoryKG × LoCoMo Benchmark Results",
        "",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"**Commit:** `{git_hash}` ({git_branch})  ",
        f"**Granularity:** {gran}  ",
        f"**k (seeds):** {meta['k']}  **hop:** {meta['hop']}  ",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Questions | {total_qa} |",
        f"| Avg Recall | **{meta['avg_recall']:.3f}** |",
        f"| Perfect (1.0) | {perfect} ({perfect / n * 100:.1f}%) |",
        f"| Partial (0–1) | {partial} ({partial / n * 100:.1f}%) |",
        f"| Zero (0.0) | {zero} ({zero / n * 100:.1f}%) |",
        f"| Elapsed | {elapsed:.1f}s ({elapsed / max(total_qa, 1):.2f}s/q) |",
        "",
        "## Per-Category Recall",
        "",
        "| Category | Recall | n |",
        "|----------|-------:|--:|",
    ]

    for cat in sorted(per_category.keys()):
        vals = per_category[cat]
        avg = sum(vals) / len(vals)
        name = CATEGORIES.get(cat, f"Cat-{cat}")
        lines.append(f"| {name} | {avg:.3f} | {len(vals)} |")

    lines += ["", "---", "*Generated by `locomo_bench_memkg.py`*", ""]
    path.write_text("\n".join(lines))


# =============================================================================
# SUBCOMMANDS
# =============================================================================


def cmd_prepare(args: argparse.Namespace) -> None:
    data_file = Path(args.data_file).resolve()
    if not data_file.exists():
        if args.download:
            download_dataset(data_file)
        else:
            sys.exit(
                f"ERROR: data file not found: {data_file}\n"
                f"  Download it with:\n"
                f"    python {Path(__file__).resolve().relative_to(REPO_ROOT)} prepare {args.data_file} --download\n"
                f"  Or manually:\n"
                f"    curl -fsSL -o {data_file} '{_LOCOMO_URL}'"
            )

    granularity = args.granularity
    corpus_dir = _corpus_dir(granularity)
    db_path = _kg_db(granularity)
    vectors_path = _kg_vectors(granularity)

    print("=" * 60)
    print("  MemoryKG × LoCoMo — PREPARE")
    print("=" * 60)
    print(f"  Source:      {data_file}")
    print(f"  Granularity: {granularity}")

    write_corpus(data_file, corpus_dir, granularity, force=args.wipe)

    embedder = None
    if args.model:
        embedder = SentenceTransformerEmbedder(args.model)

    build_kg(
        corpus_dir,
        db_path,
        vectors_path,
        wipe=args.wipe,
        model=args.model,
        chunk_strategy=args.chunk_strategy,
        batch_size=args.batch,
        discover_similar=args.similar,
        n_workers=args.workers,
        embedder=embedder,
    )
    print("  Ready. Run with:")
    print(
        f"    python {Path(__file__).resolve().relative_to(REPO_ROOT)} run {data_file} --granularity {granularity}"
    )


def cmd_run(args: argparse.Namespace) -> None:
    data_file = Path(args.data_file).resolve()
    if not data_file.exists():
        sys.exit(f"ERROR: data file not found: {data_file}")

    granularity = args.granularity
    corpus_dir = _corpus_dir(granularity)
    db_path = _kg_db(granularity)
    vectors_path = _kg_vectors(granularity)

    if not db_path.exists() or not vectors_path.exists():
        sys.exit(
            f"ERROR: MemoryKG index not found for granularity '{granularity}'. Run prepare first:\n"
            f"  python {Path(__file__).resolve().relative_to(REPO_ROOT)} prepare {data_file} --granularity {granularity}"
        )

    with open(data_file) as fh:
        data = json.load(fh)

    if args.limit > 0:
        data = data[: args.limit]

    rels_str = (
        args.rels or "CONTAINS,NEXT,REFERENCES,SIMILAR_TO,HAS_TOPIC,MENTIONS_ENTITY,HAS_KEYWORD"
    )
    rels = tuple(r.strip() for r in rels_str.split(",") if r.strip()) or DEFAULT_RELS

    print("=" * 60)
    print("  MemoryKG × LoCoMo — RUN")
    print("=" * 60)
    print(f"  Data:        {data_file.name}")
    print(f"  Conversations: {len(data)}")
    print(f"  Granularity: {granularity}")
    print(f"  k (seeds):   {args.k}")
    print(f"  hop:         {args.hop}")
    print(f"  max_nodes:   {args.max_nodes}")
    print(f"  rels:        {rels_str}")
    print("-" * 60)

    embedder = SentenceTransformerEmbedder(args.model or DEFAULT_MODEL)

    kg = MemoryKG(
        corpus_root=corpus_dir,
        db_path=db_path,
        vectors_path=vectors_path,
        model=args.model or DEFAULT_MODEL,
        embedder=embedder,
    )

    all_recall: list[float] = []
    per_category: dict[int, list[float]] = defaultdict(list)
    results_log: list[dict] = []
    total_qa = 0
    start = datetime.now()

    try:
        for conv_idx, sample in enumerate(data):
            sample_id = sample.get("sample_id", f"conv-{conv_idx}")
            conversation = sample["conversation"]
            qa_pairs = sample["qa"]

            # Collect session metadata for this conversation
            session_num = 1
            haystack_fnames: list[str] = []
            session_dates: dict[str, str] = {}

            while True:
                sess_key = f"session_{session_num}"
                date_key = f"session_{session_num}_date_time"
                if sess_key not in conversation:
                    break
                date = conversation.get(date_key, "")
                session_dates[f"session_{session_num}"] = date

                if granularity == "session":
                    haystack_fnames.append(_session_filename(sample_id, session_num))
                else:
                    for d in conversation[sess_key]:
                        dia_id = d.get("dia_id", f"D{session_num}:?")
                        haystack_fnames.append(_dialog_filename(sample_id, dia_id))
                        # For temporal rerank, map dialog unit_id → session date
                        session_dates[dia_id] = date

                session_num += 1

            haystack_files = frozenset(haystack_fnames)

            print(
                f"  [{conv_idx + 1}/{len(data)}] {sample_id}: "
                f"{session_num - 1} sessions, {len(haystack_fnames)} files, "
                f"{len(qa_pairs)} questions"
            )

            for qa in qa_pairs:
                question = qa["question"]
                category = qa.get("category", 0)
                evidence = qa.get("evidence", [])

                t0 = time.time()
                hits = query_units(
                    kg,
                    question,
                    sample_id,
                    granularity,
                    haystack_files,
                    k=args.k,
                    hop=args.hop,
                    rels=rels,
                    max_nodes=args.max_nodes,
                    seed_kinds=tuple(args.seed_kinds.split(",")) if args.seed_kinds else None,
                )
                t_q = time.time() - t0

                # Temporal rerank for categories 2 & 3
                if category in TEMPORAL_CATEGORIES:
                    # Use last session date as rough reference
                    last_date = session_dates.get(f"session_{session_num - 1}", "")
                    hits = _temporal_rerank(hits, question, session_dates, last_date)

                # Optional Ollama rerank — supply unit text from corpus files
                if args.ollama:
                    unit_texts: dict[str, str] = {}
                    for h in hits[: args.ollama_top_n]:
                        if granularity == "session":
                            fname = corpus_dir / _session_filename(
                                sample_id, int(h.unit_id.split("_")[-1])
                            )
                        else:
                            safe = h.unit_id.replace(":", "-")
                            fname = corpus_dir / f"{sample_id}__{safe}.md"
                        try:
                            unit_texts[h.unit_id] = fname.read_text()
                        except OSError:
                            pass
                    hits = _ollama_rerank(
                        hits,
                        question,
                        unit_texts,
                        top_n=args.ollama_top_n,
                        model=args.ollama_model,
                        ollama_url=args.ollama_url,
                    )

                retrieved_ids = [h.unit_id for h in hits]

                if granularity == "session":
                    evidence_ids = evidence_to_session_ids(evidence)
                else:
                    evidence_ids = set(evidence)

                recall = compute_recall(retrieved_ids, evidence_ids)
                all_recall.append(recall)
                per_category[category].append(recall)
                total_qa += 1

                results_log.append(
                    {
                        "sample_id": sample_id,
                        "question": question,
                        "answer": qa.get("answer", qa.get("adversarial_answer", "")),
                        "category": category,
                        "evidence": evidence,
                        "retrieved_ids": retrieved_ids[: args.k],
                        "recall": recall,
                        "t_query_s": round(t_q, 3),
                    }
                )

    finally:
        kg.close()

    elapsed = (datetime.now() - start).total_seconds()
    avg_recall = sum(all_recall) / len(all_recall) if all_recall else 0.0

    print(f"\n{'=' * 60}")
    print(f"  RESULTS — MemoryKG ({granularity}, k={args.k}, hop={args.hop})")
    print(f"{'=' * 60}")
    print(f"  Time:        {elapsed:.1f}s ({elapsed / max(total_qa, 1):.2f}s per question)")
    print(f"  Questions:   {total_qa}")
    print(f"  Avg Recall:  {avg_recall:.3f}")

    print("\n  PER-CATEGORY RECALL:")
    for cat in sorted(per_category.keys()):
        vals = per_category[cat]
        avg = sum(vals) / len(vals)
        name = CATEGORIES.get(cat, f"Cat-{cat}")
        print(f"    {name:25} R={avg:.3f}  (n={len(vals)})")

    perfect = sum(1 for r in all_recall if r >= 1.0)
    partial = sum(1 for r in all_recall if 0 < r < 1.0)
    zero = sum(1 for r in all_recall if r == 0.0)
    print("\n  RECALL DISTRIBUTION:")
    print(f"    Perfect (1.0): {perfect:4}  ({perfect / max(len(all_recall), 1) * 100:.1f}%)")
    print(f"    Partial (0-1): {partial:4}  ({partial / max(len(all_recall), 1) * 100:.1f}%)")
    print(f"    Zero (0.0):    {zero:4}  ({zero / max(len(all_recall), 1) * 100:.1f}%)")
    print(f"\n{'=' * 60}\n")

    # Auto-generate output path if not specified
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    if args.out:
        out_path = Path(args.out)
    else:
        results_dir = _BENCH_DIR / "results"
        out_path = (
            results_dir / f"locomo_memkg_{granularity}_k{args.k}_hop{args.hop}_{timestamp}.jsonl"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)

    meta = {
        "_meta": True,
        "elapsed_s": round(elapsed, 1),
        "n_questions": total_qa,
        "s_per_question": round(elapsed / max(total_qa, 1), 2),
        "granularity": granularity,
        "k": args.k,
        "hop": args.hop,
        "avg_recall": round(avg_recall, 4),
        "per_category": {
            CATEGORIES.get(cat, f"Cat-{cat}"): round(sum(v) / len(v), 4)
            for cat, v in sorted(per_category.items())
        },
    }

    with open(out_path, "w") as fh:
        fh.write(json.dumps(meta) + "\n")
        for row in results_log:
            fh.write(json.dumps(row) + "\n")
    print(f"  Results: {out_path}")

    md_path = out_path.with_suffix(".md")
    _write_markdown(md_path, meta, per_category, all_recall, elapsed, total_qa)
    print(f"  Report:  {md_path}")


def cmd_all(args: argparse.Namespace) -> None:
    cmd_prepare(args)
    print()
    cmd_run(args)


# =============================================================================
# CLI
# =============================================================================


def _add_shared_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("data_file", help="Path to locomo10.json")
    p.add_argument(
        "--granularity",
        choices=["session", "dialog"],
        default="session",
        help="Corpus granularity: session (one file per session) or dialog (one file per turn). Default: session.",
    )


def _add_run_args(p: argparse.ArgumentParser) -> None:
    _add_shared_args(p)
    p.add_argument("--limit", type=int, default=0, help="Limit to N conversations (0 = all)")
    p.add_argument(
        "--k",
        type=int,
        default=50,
        help="Semantic seed count (sqlite-vec top-K before graph expansion). Default: 50.",
    )
    p.add_argument(
        "--hop",
        type=int,
        default=1,
        help="Graph expansion hops. Default: 1.",
    )
    p.add_argument(
        "--max-nodes",
        type=int,
        default=500,
        help="Cap on ranked nodes from MemoryKG.query. Default: 500.",
    )
    p.add_argument(
        "--rels",
        default=None,
        help="Comma-separated edge types. Default: CONTAINS,NEXT,REFERENCES,SIMILAR_TO,HAS_TOPIC,MENTIONS_ENTITY,HAS_KEYWORD",
    )
    p.add_argument("--model", default=None, help="Override sentence-transformer model")
    p.add_argument("--out", default=None, help="Output JSONL file path")
    p.add_argument(
        "--seed-kinds",
        default=None,
        help="Restrict seeding to these node kinds (e.g. 'document'). Default: all.",
    )
    p.add_argument("--ollama", action="store_true", help="Enable Ollama LLM reranker")
    p.add_argument("--ollama-model", default="qwen3:4b-instruct", help="Ollama model name")
    p.add_argument("--ollama-url", default="http://localhost:11434", help="Ollama server URL")
    p.add_argument("--ollama-top-n", type=int, default=20, help="Candidates shown to reranker")


def _add_prepare_args(p: argparse.ArgumentParser) -> None:
    _add_shared_args(p)
    p.add_argument(
        "--wipe", action="store_true", help="Rewrite corpus files and rebuild from scratch"
    )
    p.add_argument("--model", default=None, help="Override sentence-transformer model")
    p.add_argument(
        "--chunk-strategy",
        default="heading",
        choices=["semantic", "fixed", "sentence_group", "heading"],
        help="Chunking strategy. Default: heading (one chunk per Markdown section).",
    )
    p.add_argument("--batch", type=int, default=1024, help="Embedding batch size. Default: 1024.")
    p.add_argument(
        "--similar",
        action="store_true",
        help="Enable SIMILAR_TO edge discovery (slow; off by default).",
    )
    p.add_argument("--workers", type=int, default=8, help="Parallel embedding workers. Default: 8.")
    p.add_argument(
        "--download",
        action="store_true",
        help="Download locomo10.json from GitHub if the data file does not exist.",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="MemoryKG × LoCoMo Benchmark")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_prep = sub.add_parser("prepare", help="Write corpus + build persistent MemoryKG")
    _add_prepare_args(p_prep)
    p_prep.set_defaults(func=cmd_prepare)

    p_run = sub.add_parser("run", help="Query the pre-built MemoryKG and score results")
    _add_run_args(p_run)
    p_run.set_defaults(func=cmd_run)

    p_all = sub.add_parser("all", help="prepare + run in one invocation")
    _add_prepare_args(p_all)
    # run args (excluding data_file / granularity already added by prepare)
    p_all.add_argument("--limit", type=int, default=0)
    p_all.add_argument("--k", type=int, default=50)
    p_all.add_argument("--hop", type=int, default=1)
    p_all.add_argument("--max-nodes", type=int, default=500)
    p_all.add_argument("--rels", default=None)
    p_all.add_argument("--out", default=None)
    p_all.add_argument("--seed-kinds", default=None)
    p_all.add_argument("--ollama", action="store_true")
    p_all.add_argument("--ollama-model", default="qwen3:4b-instruct")
    p_all.add_argument("--ollama-url", default="http://localhost:11434")
    p_all.add_argument("--ollama-top-n", type=int, default=20)
    p_all.set_defaults(func=cmd_all)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
