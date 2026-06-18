"""measure_denoise.py — A/B the query denoiser on the MemBench ``noisy`` set.

Runs the *same* prepared KG twice per item — once with the raw question, once
with ``denoise_query`` applied — and reports the recall delta. Non-invasive:
reuses the harness's own ``score_item`` by feeding it a denoised copy of the
item, so nothing in membench_bench.py changes.

Prereq: ``prepare --category noisy --topic all`` has built the KG.
Run with ``KG_EMBED_DEVICE=cpu`` on CPU-only hosts.
"""

from __future__ import annotations

import statistics
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import membench_bench as mb
from denoise import denoise_query

from memory_kg.index import DEFAULT_MODEL, SentenceTransformerEmbedder
from memory_kg.kg import MemoryKG

CATS = ["noisy"]
K, HOP, MAX_NODES = 20, 1, 50
RELS = tuple("CONTAINS,NEXT,REFERENCES,SIMILAR_TO,HAS_TOPIC,MENTIONS_ENTITY,HAS_KEYWORD".split(","))


def main() -> None:
    tag = mb._corpus_tag("all", CATS)
    corpus_dir, db_path, lancedb_dir = mb._corpus_dir(tag), mb._kg_db(tag), mb._kg_lancedb(tag)
    if not db_path.exists() or not lancedb_dir.exists():
        sys.exit(f"KG not found for tag '{tag}' — run prepare --category noisy --topic all first.")

    items = mb.load_membench(CATS, "", 100)
    filenames = [mb._item_filename(it["category"], it["topic"], i) for i, it in enumerate(items)]

    embedder = SentenceTransformerEmbedder(DEFAULT_MODEL)
    kg = MemoryKG(
        corpus_root=corpus_dir,
        db_path=db_path,
        lancedb_dir=lancedb_dir,
        model=DEFAULT_MODEL,
        embedder=embedder,
    )

    raw, den = [], []
    improved = regressed = unchanged = 0
    for it, fn in zip(items, filenames):
        r0, _ = mb.score_item(it, kg, fn, k=K, hop=HOP, rels=RELS, max_nodes=MAX_NODES)
        it2 = {**it, "question": denoise_query(it["question"])}
        r1, _ = mb.score_item(it2, kg, fn, k=K, hop=HOP, rels=RELS, max_nodes=MAX_NODES)
        raw.append(r0)
        den.append(r1)
        if r1 > r0:
            improved += 1
        elif r1 < r0:
            regressed += 1
        else:
            unchanged += 1

    print("\n" + "=" * 56)
    print(f"  noisy  n={len(items)}  k={K} hop={HOP} max_nodes={MAX_NODES}")
    print("=" * 56)
    print(f"  raw      recall: {statistics.mean(raw):.4f}")
    print(f"  denoised recall: {statistics.mean(den):.4f}")
    print(f"  delta:           {statistics.mean(den) - statistics.mean(raw):+.4f}")
    print(f"  improved={improved}  regressed={regressed}  unchanged={unchanged}")


if __name__ == "__main__":
    main()
