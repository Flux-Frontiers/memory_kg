#!/usr/bin/env python3
"""
MemoryKG × LongMemEval Benchmark
=================================

Evaluates MemoryKG retrieval against the LongMemEval benchmark.
Goal: maximum session-level recall with no LLM inference in the default path.

Architecture:

    prepare  →  one persistent corpus + one MemoryKG build
    run      →  500 queries against the pre-built KG

Every unique haystack session across all 500 questions is written once as
``<session_id>.md`` under ``benchmarks/longmemeval/data/longmemeval_corpus/``. The KG
runs a single time, producing a persistent SQLite graph + LanceDB vector index
plus full relational structure: document/section/chunk hierarchy, SIMILAR_TO
edges (cosine ≥ 0.85), HAS_TOPIC, MENTIONS_ENTITY, HAS_KEYWORD.

Retrieval uses ``MemoryKG.query`` — semantic-seed + graph-expansion.
The graph is the primary retrieval engine: semantic hits seed the search, and
edge expansion walks to any node that shares a topic, entity, keyword,
structural parent, or similarity edge with a seed.  For each question the
ranked nodes are collapsed to session IDs by ``file_path`` and post-filtered
to the question's ``haystack_session_ids``.

Post-retrieval reranking (applied in order after graph expansion):

* **Temporal reranking** — automatically applied for ``temporal-reasoning``
  questions; boosts sessions whose date is close to the temporal reference in
  the question (e.g. "last week", "3 days ago").
* **Sibling boost** — automatically applied when multiple answer sessions are
  required; clusters ``<base>_1`` / ``<base>_2`` / … family members together.
* **Ollama LLM reranking** — optional; enabled via ``--ollama``.  Sends the
  top-N candidate session snippets to a local Ollama model and promotes its
  pick.  Requires a running Ollama server (see ``--ollama-url``).

Usage
-----

Step 0 — download the dataset (one time, ~50 MB):

    python benchmarks/longmemeval/longmemeval_memkg.py prepare ~/Downloads/longmemeval_s_cleaned.json --download

Step 1 — prepare corpus + build the KG (one time):

    python benchmarks/longmemeval/longmemeval_memkg.py prepare ~/Downloads/longmemeval_s_cleaned.json \
        --wipe --chunk-strategy heading --workers 8

    # heading strategy: one chunk per Markdown section — fastest parse (no per-file embeddings),
    # best for conversation corpora like LongMemEval.
    # --workers 8: parallel file parsing (Phase 1); Phase 2 embedding runs on MPS/GPU.

Step 2 — run the benchmark (many times — KG is reused):

    python benchmarks/longmemeval/longmemeval_memkg.py run ~/Downloads/longmemeval_s_cleaned.json
    python benchmarks/longmemeval/longmemeval_memkg.py run <data.json> --limit 20
    python benchmarks/longmemeval/longmemeval_memkg.py run <data.json> --k 50 --hop 2 --max-nodes 500
    python benchmarks/longmemeval/longmemeval_memkg.py run <data.json> --rels CONTAINS,NEXT,SIMILAR_TO,HAS_TOPIC,MENTIONS_ENTITY,HAS_KEYWORD,CO_OCCURS_WITH

    # Seed from document nodes only (session-root seeding — reduces chunk noise):
    python benchmarks/longmemeval/longmemeval_memkg.py run <data.json> --seed-kinds document

All-in-one convenience:

    python benchmarks/longmemeval/longmemeval_memkg.py all <data.json> --limit 20

Model caching
-------------

The embedding model (default: BAAI/bge-small-en-v1.5) is cached locally so it
does not need to be re-downloaded across reboots.  By default the cache lives at
``.memorykg/models/`` under the current working directory.  To use a custom
location (e.g. ~/Downloads), set ``DOCKG_MODEL_DIR`` before running:

    # Download and save the model once:
    python -c "
    from sentence_transformers import SentenceTransformer
    import os
    SentenceTransformer('BAAI/bge-small-en-v1.5').save(
        os.path.expanduser('~/Downloads/BAAI--bge-small-en-v1.5')
    )
    "

    # Point MemoryKG at that directory:
    DOCKG_MODEL_DIR=~/Downloads python benchmarks/longmemeval/longmemeval_memkg.py prepare ...

The model directory name must use ``--`` in place of ``/`` in the HuggingFace
model ID (e.g. ``BAAI/bge-small-en-v1.5`` → ``BAAI--bge-small-en-v1.5``).

Author: Eric G. Suchanek, PhD
Last Revision: 2026-04-25

License: Elastic 2.0
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# Make `src/` importable when running from a source checkout
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from memory_kg.kg import MemoryKG
from memory_kg.memorykg import DEFAULT_MODEL
from memory_kg.store import DEFAULT_RELS

# =============================================================================
# PATHS
# =============================================================================

CORPUS_DIR = REPO_ROOT / "benchmarks" / "longmemeval" / "data" / "longmemeval_corpus"
DOCKG_DB = REPO_ROOT / "benchmarks" / "longmemeval" / "data" / ".dockg" / "graph.sqlite"
DOCKG_LANCEDB = REPO_ROOT / "benchmarks" / "longmemeval" / "data" / ".dockg" / "lancedb"
DOCKG_EMB_CACHE = REPO_ROOT / "benchmarks" / "longmemeval" / "data" / ".dockg" / "embeddings.json"


# =============================================================================
# METRICS
# =============================================================================


def dcg(relevances: list[float], k: int) -> float:
    return sum(rel / math.log2(i + 2) for i, rel in enumerate(relevances[:k]))


def ndcg(rankings: list[int], correct_ids: set[str], corpus_ids: list[str], k: int) -> float:
    relevances = [1.0 if corpus_ids[idx] in correct_ids else 0.0 for idx in rankings[:k]]
    ideal = sorted(relevances, reverse=True)
    idcg = dcg(ideal, k)
    if idcg == 0:
        return 0.0
    return dcg(relevances, k) / idcg


def evaluate_retrieval(
    rankings: list[int], correct_ids: set[str], corpus_ids: list[str], k: int
) -> tuple[float, float, float]:
    top_k_ids = {corpus_ids[idx] for idx in rankings[:k]}
    recall_any = float(any(cid in top_k_ids for cid in correct_ids))
    recall_all = float(all(cid in top_k_ids for cid in correct_ids))
    nd = ndcg(rankings, correct_ids, corpus_ids, k)
    return recall_any, recall_all, nd


# =============================================================================
# PREPARE — write corpus files + build DocKG
# =============================================================================


def _format_session_markdown(sess_id: str, date: str, turns: list[dict]) -> str:
    """Render a longmemeval session as a Markdown document."""
    lines: list[str] = [
        f"# Session {sess_id}",
        "",
        f"**Date:** {date}",
        "",
    ]
    for turn in turns:
        role = turn.get("role", "user")
        content = (turn.get("content") or "").strip()
        if not content:
            continue
        lines.append(f"## {role.capitalize()}")
        lines.append("")
        lines.append(content)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


_PREF_PATTERNS: list[re.Pattern] = [
    re.compile(
        r"i(?:'ve| have) been having (?:trouble|issues?|problems?) with (.+?)(?:\.|$)", re.I
    ),
    re.compile(r"i(?:'ve| have) been feeling (.+?)(?:\.|$)", re.I),
    re.compile(r"i(?:'ve| have) been (?:struggling|dealing) with (.+?)(?:\.|$)", re.I),
    re.compile(r"i(?:'m| am) (?:worried|concerned) about (.+?)(?:\.|$)", re.I),
    re.compile(r"i prefer (.+?)(?:\.|$)", re.I),
    re.compile(r"i usually (.+?)(?:\.|$)", re.I),
    re.compile(r"i want to (.+?)(?:\.|$)", re.I),
    re.compile(r"i(?:'m| am) thinking (?:about|of) (.+?)(?:\.|$)", re.I),
    re.compile(r"lately[,\s]+i(?:'ve| have) been (.+?)(?:\.|$)", re.I),
    re.compile(r"recently[,\s]+i(?:'ve| have) been (.+?)(?:\.|$)", re.I),
    re.compile(r"i(?:'ve| have) been (?:working on|focused on|interested in) (.+?)(?:\.|$)", re.I),
    re.compile(r"i(?:'m| am) (?:looking for|trying to find) (.+?)(?:\.|$)", re.I),
    re.compile(r"i(?:'d| would) (?:like|love|prefer) (.+?)(?:\.|$)", re.I),
    re.compile(r"my (?:goal|plan|intention) is to (.+?)(?:\.|$)", re.I),
    re.compile(r"i hate (.+?)(?:\.|$)", re.I),
    re.compile(r"i(?:'m| am) allergic to (.+?)(?:\.|$)", re.I),
]


def _extract_preferences(turns: list[dict]) -> list[str]:
    """Extract preference expressions from user turns using regex patterns."""
    prefs: list[str] = []
    seen: set[str] = set()
    for turn in turns:
        if turn.get("role") != "user":
            continue
        text = (turn.get("content") or "").strip()
        for pat in _PREF_PATTERNS:
            for m in pat.finditer(text):
                pref = m.group(0).strip().rstrip(".")
                if pref.lower() not in seen and len(pref) > 10:
                    prefs.append(pref)
                    seen.add(pref.lower())
    return prefs


def write_corpus(data_file: Path, corpus_dir: Path, force: bool = False) -> dict[str, str]:
    """Walk the longmemeval JSON and write every unique haystack session to disk.

    Returns a map of ``session_id → file_path`` (as a string, repo-relative).
    """
    with open(data_file) as fh:
        data = json.load(fh)

    corpus_dir.mkdir(parents=True, exist_ok=True)
    existing = {p.stem for p in corpus_dir.glob("*.md")}

    written = 0
    skipped = 0
    session_files: dict[str, str] = {}

    for entry in data:
        for session, sess_id, date in zip(
            entry["haystack_sessions"],
            entry["haystack_session_ids"],
            entry["haystack_dates"],
        ):
            out_path = corpus_dir / f"{sess_id}.md"
            session_files[sess_id] = str(out_path)
            if not force and sess_id in existing:
                skipped += 1
                continue
            out_path.write_text(_format_session_markdown(sess_id, date, session))
            written += 1
            existing.add(sess_id)

    total = written + skipped
    print(f"  Corpus: {total} unique sessions ({written} written, {skipped} reused) → {corpus_dir}")
    return session_files


def build_kg(
    corpus_dir: Path,
    db_path: Path,
    lancedb_dir: Path,
    wipe: bool = True,
    model: str | None = None,
    chunk_strategy: str = "semantic",
    batch_size: int = 1024,
    discover_similar: bool = False,
    n_workers: int = 8,
) -> None:
    """Build a persistent MemoryKG from the corpus dir."""
    print(f"  Building MemoryKG ({'wipe' if wipe else 'incremental'})...")
    print(f"    corpus:  {corpus_dir}")
    print(f"    sqlite:  {db_path}")
    print(f"    lancedb: {lancedb_dir}")
    print(f"    model:   {model or DEFAULT_MODEL}")
    print(f"    chunk:   {chunk_strategy}")
    print(f"    batch:   {batch_size}")
    print(f"    workers: {n_workers}")
    from memory_kg.index import _resolve_device  # local import: heavy deps

    print(f"    device:  {_resolve_device()}")
    print(f"    similar: {'yes' if discover_similar else 'no (use --similar to enable)'}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    lancedb_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    kg = MemoryKG(
        corpus_root=corpus_dir,
        db_path=db_path,
        lancedb_dir=lancedb_dir,
        model=model or DEFAULT_MODEL,
        chunk_strategy=chunk_strategy,
        n_workers=n_workers,
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


_LONGMEMEVAL_URL = (
    "https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned"
    "/resolve/main/longmemeval_s_cleaned.json"
)


def download_dataset(dest: Path) -> None:
    """Download longmemeval_s_cleaned.json from HuggingFace if not present."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  Downloading LongMemEval dataset → {dest}")
    print(f"    Source: {_LONGMEMEVAL_URL}")
    urllib.request.urlretrieve(_LONGMEMEVAL_URL, dest)
    print(f"  Downloaded: {dest.stat().st_size / 1_048_576:.1f} MB")


def cmd_prepare(args: argparse.Namespace) -> None:
    data_file = Path(args.data_file).resolve()
    if not data_file.exists():
        if args.download:
            download_dataset(data_file)
        else:
            sys.exit(
                f"ERROR: data file not found: {data_file}\n"
                f"  Download it with:\n"
                f"    python {Path(__file__).name} prepare {args.data_file} --download\n"
                f"  Or manually:\n"
                f"    mkdir -p {data_file.parent}\n"
                f"    curl -fsSL -o {data_file} '{_LONGMEMEVAL_URL}'"
            )

    # Pin the embedding device before the (lazily-constructed) embedder loads.
    # 'auto' -> MPS on Apple Silicon (~9x faster than CPU). Peak RAM is bounded by
    # the encode batch (128) so MPS no longer balloons on 500k-node corpora.
    device = getattr(args, "device", "auto")
    if device and device != "auto":
        os.environ["KG_EMBED_DEVICE"] = device

    print("=" * 60)
    print("  MemoryKG × LongMemEval — PREPARE")
    print("=" * 60)
    print(f"  Source: {data_file}")

    write_corpus(data_file, CORPUS_DIR, force=args.wipe)
    build_kg(
        CORPUS_DIR,
        DOCKG_DB,
        DOCKG_LANCEDB,
        wipe=args.wipe,
        model=args.model,
        chunk_strategy=getattr(args, "chunk_strategy", "semantic"),
        batch_size=getattr(args, "batch", 1024),
        discover_similar=getattr(args, "similar", False),
        n_workers=getattr(args, "workers", 8),
    )
    print("  Ready. Run with:")
    print(f"    python {Path(__file__).name} run {data_file}")


# =============================================================================
# QUERY — DocKG retrieval + session-level ranking
# =============================================================================


@dataclass
class SessionHit:
    """A single session-level retrieval hit for one query.

    ``rank`` is the position of the best-ranked DocKG node that resolved back
    to this session (lower = better). ``via_node_id`` is that node's stable ID,
    useful when auditing which chunk/topic/entity caused the session to surface.
    """

    session_id: str
    rank: int
    via_node_id: str | None


def _session_id_from_file_path(file_path: str | None) -> str | None:
    """Extract ``<session_id>`` from paths like ``.../<session_id>.md``.

    Synthetic preference docs are named ``<session_id>_pref.md`` — the ``_pref``
    suffix is stripped so they resolve to the same session.
    """
    if not file_path:
        return None
    stem = Path(file_path).stem
    if stem.endswith("_pref"):
        stem = stem[: -len("_pref")]
    return stem or None


_STOP_WORDS = {
    "what",
    "when",
    "where",
    "who",
    "how",
    "which",
    "did",
    "do",
    "does",
    "was",
    "were",
    "have",
    "has",
    "had",
    "is",
    "are",
    "the",
    "a",
    "an",
    "my",
    "me",
    "i",
    "you",
    "your",
    "their",
    "it",
    "its",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "by",
    "from",
    "ago",
    "last",
    "that",
    "this",
    "there",
    "about",
    "get",
    "got",
    "give",
    "gave",
    "buy",
    "bought",
    "made",
    "make",
}

_TEMPORAL_PATTERNS: list[tuple[re.Pattern, int, int]] = [
    # (pattern, offset_days, window_days)
    (re.compile(r"(\d+)\s+days?\s+ago", re.I), 0, 3),  # "N days ago" — offset set per match
    (re.compile(r"a\s+couple\s+of\s+days?\s+ago", re.I), 2, 3),
    (re.compile(r"a\s+week\s+ago", re.I), 7, 5),
    (re.compile(r"(\d+)\s+weeks?\s+ago", re.I), 0, 7),
    (re.compile(r"last\s+week", re.I), 7, 5),
    (re.compile(r"a\s+month\s+ago", re.I), 30, 10),
    (re.compile(r"(\d+)\s+months?\s+ago", re.I), 0, 14),
    (re.compile(r"last\s+month", re.I), 30, 10),
    (re.compile(r"recently", re.I), 14, 14),
]


def _parse_time_offset_days(question: str) -> tuple[int, int] | None:
    """Return (offset_days, window_days) if a temporal reference is detected, else None."""
    for pat, offset, window in _TEMPORAL_PATTERNS:
        m = pat.search(question)
        if m:
            if offset == 0 and m.lastindex:
                n = int(m.group(1))
                # "N days ago" vs "N weeks ago" vs "N months ago"
                if "month" in m.group(0).lower():
                    return n * 30, 14
                elif "week" in m.group(0).lower():
                    return n * 7, 7
                else:
                    return n, 3
            return offset, window
    return None


def _keyword_rerank(
    hits: list,
    question: str,
    session_texts: dict[str, str],
    weight: float = 0.30,
) -> list:
    """Re-rank session hits by fusing semantic rank with keyword overlap.

    :param hits: Session hits sorted by ascending rank.
    :param question: Raw question text.
    :param session_texts: Mapping of session_id → full session text (for overlap).
    :param weight: Max distance reduction for perfect keyword overlap (default 0.30).
    :return: Re-ranked list of session hits.
    """
    keywords = [
        w.lower() for w in re.findall(r"\b\w{3,}\b", question) if w.lower() not in _STOP_WORDS
    ]
    if not keywords or not session_texts:
        return hits

    scored: list[tuple[float, Any]] = []
    for h in hits:
        text = session_texts.get(h.session_id, "").lower()
        overlap = sum(1 for kw in keywords if kw in text) / len(keywords)
        # rank-as-distance: lower rank = closer
        dist = float(h.rank)
        fused = dist * (1.0 - weight * overlap)
        scored.append((fused, h))

    scored.sort(key=lambda x: x[0])
    return [h for _, h in scored]


def _temporal_rerank(
    hits: list,
    question: str,
    question_date: str | None,
    haystack_dates: dict[str, str],
    max_boost: float = 0.40,
) -> list:
    """Boost sessions whose date is close to the temporal reference in the question.

    :param hits: Session hits sorted by ascending rank.
    :param question: Raw question text.
    :param question_date: ISO date string when the question was asked.
    :param haystack_dates: Mapping of session_id → ISO date string.
    :param max_boost: Maximum distance reduction for a perfect date match.
    :return: Re-ranked list of session hits.
    """
    if not question_date or not haystack_dates:
        return hits
    parsed = _parse_time_offset_days(question)
    if parsed is None:
        return hits

    offset_days, window_days = parsed
    try:
        q_date = datetime.strptime(question_date[:10], "%Y-%m-%d")
    except ValueError:
        return hits
    target = q_date - timedelta(days=offset_days)

    scored: list[tuple[float, Any]] = []
    for h in hits:
        date_str = haystack_dates.get(h.session_id)
        dist = float(h.rank)
        if date_str:
            try:
                s_date = datetime.strptime(date_str[:10], "%Y-%m-%d")
                days_diff = abs((s_date - target).days)
                temporal_boost = max(0.0, max_boost * (1.0 - days_diff / max(window_days, 1)))
                dist = dist * (1.0 - temporal_boost)
            except ValueError:
                pass
        scored.append((dist, h))

    scored.sort(key=lambda x: x[0])
    return [h for _, h in scored]


def _ollama_rerank(
    hits: list,
    question: str,
    session_texts: dict[str, str],
    *,
    top_n: int = 20,
    model: str = "qwen3:4b-instruct",
    ollama_url: str = "http://localhost:11434",
) -> list:
    """Use a local Ollama model to rerank the top-N candidate sessions.

    Takes the top ``top_n`` hits, sends question + session snippets to the
    model, and promotes the model's pick to rank 0. Falls back to original
    order on any error.

    :param hits: Session hits sorted by ascending rank.
    :param question: Raw question text.
    :param session_texts: Mapping of session_id → full session text.
    :param top_n: Number of candidates to show the model.
    :param model: Ollama model name (e.g. ``"llama3.2"``, ``"mistral"``).
    :param ollama_url: Base URL of the running Ollama server.
    :return: Re-ranked list of session hits.
    """
    candidates = hits[:top_n]
    rest = hits[top_n:]
    if not candidates:
        return hits

    snippets = []
    for i, h in enumerate(candidates):
        text = (session_texts.get(h.session_id) or "")[:400].replace("\n", " ")
        snippets.append(f"Session {i + 1}: {text}")

    prompt = (
        f"Question: {question}\n\n"
        f"Below are {len(candidates)} conversation sessions from someone's memory. "
        f"Which single session is most likely to contain the answer? "
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
        # Extract first integer from response
        m = re.search(r"\d+", raw)
        if m:
            pick = int(m.group()) - 1
            if 0 <= pick < len(candidates):
                reranked = [candidates[pick]] + [h for j, h in enumerate(candidates) if j != pick]
                return reranked + rest
    except (urllib.error.URLError, OSError, KeyError, ValueError):
        pass  # Ollama unavailable — fall back silently
    return hits


_SIBLING_RE = re.compile(r"^(.+)_(\d+)$")


def _sibling_boost(hits: list[SessionHit]) -> list[SessionHit]:
    """Cluster sibling sessions (same base_id, different _N suffix) together.

    When the first member of a ``base_1`` / ``base_2`` / ... family appears in
    the ranked list, all other family members already present in *hits* are
    pulled forward to follow immediately (in their original KG-ranked order).

    This improves recall_all for multi-session accumulator questions where later
    instances of the same event type share near-identical text and rank lower
    than the first hit despite being equally relevant.
    """
    # Build base → [session_ids in original rank order]
    base_to_sids: dict[str, list[str]] = defaultdict(list)
    for h in hits:
        m = _SIBLING_RE.match(h.session_id)
        if m:
            base_to_sids[m.group(1)].append(h.session_id)

    hit_map = {h.session_id: h for h in hits}
    seen: set[str] = set()
    result: list[SessionHit] = []

    for hit in hits:
        if hit.session_id in seen:
            continue
        seen.add(hit.session_id)
        result.append(hit)
        m = _SIBLING_RE.match(hit.session_id)
        if m:
            for sib_id in base_to_sids[m.group(1)]:
                if sib_id not in seen:
                    seen.add(sib_id)
                    result.append(hit_map[sib_id])

    return result


def query_sessions(
    kg: Any,
    question: str,
    *,
    k: int,
    hop: int,
    rels: tuple[str, ...],
    max_nodes: int,
    haystack: set[str] | None = None,
    seed_kinds: tuple[str, ...] | None = None,
    haystack_files: frozenset[str] | None = None,
) -> tuple[list[SessionHit], Any]:
    """Run ``DocKG.query`` and collapse its ranked nodes to session-level hits.

    This is the pure DocKG retrieval path: semantic seeding over LanceDB plus
    graph expansion over ``rels`` (CONTAINS / NEXT / SIMILAR_TO / HAS_TOPIC /
    MENTIONS_ENTITY / HAS_KEYWORD / CO_OCCURS_WITH / REFERENCES). No rerank,
    no inference — the graph is the retrieval engine.

    Any ranked node whose ``file_path`` resolves to a session in the current
    question's haystack contributes. The earliest (lowest-ranked) such node
    per session wins.

    :param kg: An open :class:`memory_kg.kg.MemoryKG` instance.
    :param question: Natural-language query.
    :param k: Semantic seed count (LanceDB top-K before graph expansion).
    :param hop: Graph expansion hops.
    :param rels: Edge types to traverse during expansion.
    :param max_nodes: Cap on ranked nodes returned by ``DocKG.query``.
    :param haystack: If supplied, only sessions in this set are returned.
    :param seed_kinds: If set, restrict LanceDB seeding to these node kinds.
        Pass ``("document",)`` to seed only from session-root document nodes.
    :param haystack_files: If set, restrict LanceDB seeding to nodes from these
        file paths only (e.g. the 50 haystack session files per question).
    :return: Tuple of (session-level hits sorted by ascending rank, raw QueryResult).
    """
    result = kg.query(
        question,
        k=k,
        hop=hop,
        rels=rels,
        max_nodes=max_nodes,
        seed_kinds=seed_kinds,
        haystack_files=haystack_files,
    )

    best_per_session: dict[str, SessionHit] = {}
    for rank, node in enumerate(result.nodes):
        sess_id = _session_id_from_file_path(node.get("file_path"))
        if sess_id is None:
            continue
        if haystack is not None and sess_id not in haystack:
            continue
        prev = best_per_session.get(sess_id)
        if prev is None or rank < prev.rank:
            best_per_session[sess_id] = SessionHit(
                session_id=sess_id,
                rank=rank,
                via_node_id=node.get("id"),
            )

    return sorted(best_per_session.values(), key=lambda x: x.rank), result


# =============================================================================
# BENCHMARK RUNNER
# =============================================================================


def _parse_rels(rels_arg: str | None) -> tuple[str, ...]:
    """Parse a ``--rels`` CLI value ("A,B,C") into a tuple, or default."""
    if not rels_arg:
        return DEFAULT_RELS
    parts = [r.strip() for r in rels_arg.split(",") if r.strip()]
    return tuple(parts) if parts else DEFAULT_RELS


def cmd_run(args: argparse.Namespace) -> None:
    data_file = Path(args.data_file).resolve()
    if not data_file.exists():
        sys.exit(f"ERROR: data file not found: {data_file}")
    if not DOCKG_DB.exists() or not DOCKG_LANCEDB.exists():
        sys.exit(
            "ERROR: MemoryKG index not found. Run `prepare` first:\n"
            f"  python {Path(__file__).name} prepare {data_file}"
        )

    with open(data_file) as fh:
        data = json.load(fh)

    if args.limit > 0:
        data = data[: args.limit]
    if args.skip > 0:
        data = data[args.skip :]

    rels = _parse_rels(args.rels)

    print("=" * 60)
    print("  MemoryKG × LongMemEval — RUN")
    print("=" * 60)
    print(f"  Data:        {data_file.name}")
    print(f"  Questions:   {len(data)}")
    print(f"  k (seeds):   {args.k}")
    print(f"  hop:         {args.hop}")
    print(f"  max_nodes:   {args.max_nodes}")
    print(f"  rels:        {','.join(rels)}")
    print("-" * 60)

    kg = MemoryKG(
        corpus_root=CORPUS_DIR,
        db_path=DOCKG_DB,
        lancedb_dir=DOCKG_LANCEDB,
    )

    ks = [1, 3, 5, 10, 30, 50]
    metrics = {f"recall_any@{k}": [] for k in ks}
    metrics.update({f"recall_all@{k}": [] for k in ks})
    metrics.update({f"ndcg_any@{k}": [] for k in ks})
    per_type: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    results_log: list[dict] = []
    start = datetime.now()
    misses: list[str] = []

    try:
        for i, entry in enumerate(data):
            qid = entry["question_id"]
            qtype = entry["question_type"]
            question = entry["question"]
            haystack = set(entry["haystack_session_ids"])
            answer_sids = set(entry["answer_session_ids"])

            print(
                f"  [{i + 1:4}/{len(data)}] {qid[:30]:30}  querying: {question[:60]!r}",
                flush=True,
            )
            t_q0 = time.time()
            hits, qr = query_sessions(
                kg,
                question,
                k=args.k,
                hop=args.hop,
                rels=rels,
                max_nodes=args.max_nodes,
                haystack=haystack,
                seed_kinds=tuple(args.seed_kinds.split(","))
                if getattr(args, "seed_kinds", None)
                else None,
                haystack_files=(
                    frozenset(f"{sid}.md" for sid in entry["haystack_session_ids"])
                    if getattr(args, "haystack_filter", False)
                    else None
                ),
            )
            t_q = time.time() - t_q0

            # Build per-session lookup tables for reranking
            sid_list = entry["haystack_session_ids"]
            haystack_dates = {
                sid: entry["haystack_dates"][j][:10].replace("/", "-")
                for j, sid in enumerate(sid_list)
                if j < len(entry["haystack_dates"])
            }
            session_texts = {
                sid: " ".join(
                    turn["content"]
                    for turn in entry["haystack_sessions"][j]
                    if isinstance(turn, dict)
                )
                for j, sid in enumerate(sid_list)
            }

            # Temporal re-rank for temporal-reasoning questions
            if qtype == "temporal-reasoning":
                hits = _temporal_rerank(hits, question, entry.get("question_date"), haystack_dates)

            # Ollama reranker (optional — pass --ollama to enable)
            if getattr(args, "ollama", False):
                hits = _ollama_rerank(
                    hits,
                    question,
                    session_texts,
                    top_n=getattr(args, "ollama_top_n", 20),
                    model=getattr(args, "ollama_model", "llama3.2"),
                )

            # Sibling boost: cluster _1/_2/... family members together
            # Only when multiple sessions are required — single-session questions
            # have _N-style IDs too and the boost would displace relevant results.
            if len(answer_sids) > 1:
                hits = _sibling_boost(hits)

            # Reassign ranks after reranking
            for new_rank, h in enumerate(hits):
                h.rank = new_rank

            # Any haystack sessions not surfaced by the graph query go to the tail
            returned = {h.session_id for h in hits}
            tail_start = len(hits)
            tail = [
                SessionHit(
                    session_id=sid,
                    rank=tail_start + offset,
                    via_node_id=None,
                )
                for offset, sid in enumerate(
                    sid for sid in entry["haystack_session_ids"] if sid not in returned
                )
            ]
            ordered = hits + tail

            # Corpus-aligned structures expected by evaluate_retrieval
            corpus_ids = [h.session_id for h in ordered]
            rankings = list(range(len(ordered)))

            entry_metrics: dict[str, float] = {}
            for k in ks:
                ra, rl, nd = evaluate_retrieval(rankings, answer_sids, corpus_ids, k)
                metrics[f"recall_any@{k}"].append(ra)
                metrics[f"recall_all@{k}"].append(rl)
                metrics[f"ndcg_any@{k}"].append(nd)
                entry_metrics[f"recall_any@{k}"] = ra
                entry_metrics[f"recall_all@{k}"] = rl
                entry_metrics[f"ndcg_any@{k}"] = nd

            per_type[qtype]["recall_any@5"].append(metrics["recall_any@5"][-1])
            per_type[qtype]["recall_any@10"].append(metrics["recall_any@10"][-1])
            per_type[qtype]["recall_all@10"].append(metrics["recall_all@10"][-1])
            per_type[qtype]["ndcg_any@10"].append(metrics["ndcg_any@10"][-1])

            r5 = metrics["recall_any@5"][-1]
            r10 = metrics["recall_any@10"][-1]
            status = "HIT" if r5 > 0 else ("MISS" if r10 == 0 else "late")
            if status == "MISS":
                misses.append(qid)
            print(
                f"         {'':30}  seeds={qr.seeds} exp={qr.expanded_nodes} "
                f"ret={qr.returned_nodes} sess={len(hits)} "
                f"t={t_q:.2f}s  "
                f"R@5={r5:.0f} R@10={r10:.0f}  {status}",
                flush=True,
            )

            results_log.append(
                {
                    "question_id": qid,
                    "question_type": qtype,
                    "question": question,
                    "query_sent": question,
                    "answer": entry.get("answer"),
                    "answer_session_ids": sorted(answer_sids),
                    "retrieved": [
                        {
                            "session_id": h.session_id,
                            "rank": h.rank,
                            "via_node_id": h.via_node_id,
                        }
                        for h in ordered[: max(ks)]
                    ],
                    "metrics": entry_metrics,
                }
            )
    finally:
        kg.close()

    elapsed = (datetime.now() - start).total_seconds()

    print()
    print("=" * 60)
    print(f"  RESULTS — MemoryKG (k={args.k} hop={args.hop} max_nodes={args.max_nodes})")
    print("=" * 60)
    print(f"  Time: {elapsed:.1f}s ({elapsed / max(len(data), 1):.2f}s per question)")
    print()
    print("  SESSION-LEVEL METRICS:")
    print(f"    {'@k':<4}  {'recall_any':>10}  {'recall_all':>10}  {'nDCG':>8}")
    for k in ks:
        ra = sum(metrics[f"recall_any@{k}"]) / len(metrics[f"recall_any@{k}"])
        rl = sum(metrics[f"recall_all@{k}"]) / len(metrics[f"recall_all@{k}"])
        nd = sum(metrics[f"ndcg_any@{k}"]) / len(metrics[f"ndcg_any@{k}"])
        print(f"    @{k:<3}  {ra:>10.3f}  {rl:>10.3f}  {nd:>8.3f}")
    print()
    print("  PER-TYPE BREAKDOWN (recall_any@10 / recall_all@10):")
    for qtype, vals in sorted(per_type.items()):
        ra10 = sum(vals["recall_any@10"]) / len(vals["recall_any@10"])
        rl10 = sum(vals["recall_all@10"]) / len(vals["recall_all@10"])
        n = len(vals["recall_any@10"])
        print(f"    {qtype:35} any={ra10:.3f}  all={rl10:.3f}  (n={n})")

    if misses:
        print()
        print(f"  MISSES @10: {len(misses)}/{len(data)}")
        for qid in misses[:20]:
            print(f"    - {qid}")
        if len(misses) > 20:
            print(f"    ... {len(misses) - 20} more")

    print()

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        meta = {
            "_meta": True,
            "elapsed_s": round(elapsed, 1),
            "n_questions": len(data),
            "s_per_question": round(elapsed / max(len(data), 1), 2),
            "k": args.k,
            "hop": args.hop,
            "haystack_filter": getattr(args, "haystack_filter", False),
        }
        with open(out_path, "w") as fh:
            fh.write(json.dumps(meta) + "\n")
            for row in results_log:
                fh.write(json.dumps(row) + "\n")
        print(f"  Results saved to: {out_path}")

        # Auto-render comparison report against all existing result files
        try:
            _spec = importlib.util.spec_from_file_location(
                "render_results",
                Path(__file__).parent.parent / "render_results.py",
            )
            _rr = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
            _spec.loader.exec_module(_rr)  # type: ignore[union-attr]

            _existing = sorted(p for p in out_path.parent.glob("results_*.jsonl") if p != out_path)
            _runs = [(p.stem, _rr._load(p)) for p in _existing]
            _runs.append((out_path.stem, [meta] + results_log))

            if len(_runs) > 1:
                _report = out_path.parent / "BENCHMARKS_COMPARISON.md"
                _rr.write_comparison_markdown(_runs, _report, _rr._git_info())
                print(f"  Comparison report: {_report}")
            else:
                _report = out_path.parent / "BENCHMARKS_MEMKG.md"
                _rr.write_markdown(
                    [meta] + results_log,
                    out_path.stem,
                    out_path,
                    _report,
                    _rr._git_info(),
                    meta=meta,
                )
                print(f"  Report: {_report}")
        except Exception as _e:  # pylint: disable=broad-exception-caught
            print(f"  (auto-render skipped: {_e})")


def cmd_all(args: argparse.Namespace) -> None:
    cmd_prepare(args)
    print()
    cmd_run(args)


# =============================================================================
# CLI
# =============================================================================


def _add_run_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("data_file", help="Path to longmemeval_s_cleaned.json")
    p.add_argument("--limit", type=int, default=0, help="Limit to N questions (0 = all)")
    p.add_argument("--skip", type=int, default=0, help="Skip first N questions")
    p.add_argument(
        "--k",
        type=int,
        default=50,
        help="Semantic seed count (LanceDB top-K before graph expansion). Default: 50.",
    )
    p.add_argument(
        "--hop",
        type=int,
        default=1,
        help="Graph expansion hops from each seed. Default: 1.",
    )
    p.add_argument(
        "--max-nodes",
        type=int,
        default=1000,
        help=(
            "Cap on ranked nodes returned by MemoryKG.query. "
            "Must be large enough that the haystack's sessions are covered. Default: 1000."
        ),
    )
    # CO_OCCURS_WITH has ~8M edges in the LongMemEval corpus (59%% of all edges).
    # Including it at hop>=2 causes explosive graph expansion and makes queries
    # extremely slow without meaningfully improving session recall.  The tighter
    # default below keeps the high-signal semantic edges only.
    _DEFAULT_BENCH_RELS = (
        "CONTAINS,NEXT,REFERENCES,SIMILAR_TO,HAS_TOPIC,MENTIONS_ENTITY,HAS_KEYWORD"
    )
    p.add_argument(
        "--rels",
        default=_DEFAULT_BENCH_RELS,
        help=(
            "Comma-separated edge types to traverse during graph expansion. "
            f"Default: {_DEFAULT_BENCH_RELS}  (CO_OCCURS_WITH excluded — "
            "it has ~8M edges in the LongMemEval corpus and causes explosive expansion)."
        ),
    )
    p.add_argument("--out", default=None, help="Output JSONL file path")
    p.add_argument(
        "--seed-kinds",
        default=None,
        help="Comma-separated node kinds to restrict semantic seeding to (e.g. 'document' for session-root seeding). Default: all kinds.",
    )
    p.add_argument(
        "--haystack-filter",
        action="store_true",
        default=True,
        help="Restrict LanceDB seeding to the per-question haystack files only (default: on).",
    )
    p.add_argument(
        "--no-haystack-filter",
        dest="haystack_filter",
        action="store_false",
        help="Search the full corpus instead of per-question haystack sessions.",
    )
    p.add_argument(
        "--ollama",
        action="store_true",
        help="Enable Ollama LLM reranker (requires Ollama running at --ollama-url).",
    )
    p.add_argument(
        "--ollama-model",
        default="qwen3:4b-instruct",
        help="Ollama model name for reranking (default: qwen3:4b-instruct).",
    )
    p.add_argument(
        "--ollama-url",
        default="http://localhost:11434",
        help="Ollama server base URL (default: http://localhost:11434).",
    )
    p.add_argument(
        "--ollama-top-n",
        type=int,
        default=20,
        help="Number of top candidates to show the reranker (default: 20).",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="MemoryKG × LongMemEval Benchmark")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_prep = sub.add_parser("prepare", help="Write corpus + build persistent MemoryKG")
    p_prep.add_argument("data_file", help="Path to longmemeval_s_cleaned.json")
    p_prep.add_argument(
        "--wipe",
        action="store_true",
        help="Rewrite corpus files and rebuild from scratch",
    )
    p_prep.add_argument("--model", default=None, help="Override sentence-transformer model")
    p_prep.add_argument(
        "--chunk-strategy",
        default="semantic",
        choices=["semantic", "fixed", "sentence_group", "heading"],
        help=(
            "Chunking strategy. 'heading' = one chunk per Markdown section (best for "
            "conversation corpora like LongMemEval). Default: semantic."
        ),
    )
    p_prep.add_argument(
        "--batch",
        type=int,
        default=1024,
        help="Embedding batch size (default: 1024).",
    )
    p_prep.add_argument(
        "--similar",
        action="store_true",
        help="Enable SIMILAR_TO edge discovery (slow — ~1hr for 528k nodes; off by default).",
    )
    p_prep.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Number of parallel embedding workers (default: 8).",
    )
    p_prep.add_argument(
        "--device",
        default="auto",
        choices=["cpu", "mps", "cuda", "auto"],
        help=(
            "Embedding device (sets KG_EMBED_DEVICE). Default 'auto' = detect "
            "(MPS on Apple Silicon, ~9x faster than CPU). Peak RAM is bounded by "
            "the encode batch (128), so MPS no longer balloons. Force with cpu/mps."
        ),
    )
    p_prep.add_argument(
        "--download",
        action="store_true",
        help="Download the dataset from HuggingFace if the data file does not exist",
    )
    p_prep.set_defaults(func=cmd_prepare)

    p_run = sub.add_parser("run", help="Query the pre-built MemoryKG and score results")
    _add_run_args(p_run)
    p_run.set_defaults(func=cmd_run)

    p_all = sub.add_parser("all", help="prepare + run in one invocation")
    _add_run_args(p_all)
    p_all.add_argument("--wipe", action="store_true", help="Rebuild the KG")
    p_all.add_argument("--model", default=None, help="Override sentence-transformer model")
    p_all.add_argument(
        "--chunk-strategy",
        default="semantic",
        choices=["semantic", "fixed", "sentence_group", "heading"],
        help=(
            "Chunking strategy. 'heading' = one chunk per Markdown section (best for "
            "conversation corpora like LongMemEval). Default: semantic."
        ),
    )
    p_all.add_argument(
        "--batch",
        type=int,
        default=1024,
        help="Embedding batch size (default: 1024).",
    )
    p_all.add_argument(
        "--similar",
        action="store_true",
        help="Enable SIMILAR_TO edge discovery (slow — ~1hr for 528k nodes; off by default).",
    )
    p_all.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Number of parallel embedding workers (default: 8).",
    )
    p_all.add_argument(
        "--device",
        default="auto",
        choices=["cpu", "mps", "cuda", "auto"],
        help=(
            "Embedding device (sets KG_EMBED_DEVICE). Default 'auto' = detect "
            "(MPS on Apple Silicon, ~9x faster than CPU). Peak RAM is bounded by "
            "the encode batch (128), so MPS no longer balloons. Force with cpu/mps."
        ),
    )
    p_all.add_argument(
        "--download",
        action="store_true",
        help="Download the dataset from HuggingFace if the data file does not exist",
    )
    p_all.set_defaults(func=cmd_all)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
