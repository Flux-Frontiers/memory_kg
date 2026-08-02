#!/usr/bin/env python3
"""
Quick smoke-test for _discover_similar_edges — no embedding pass required.

Creates a tiny synthetic GraphStore + vector set and calls the method directly.
Run from the repo root:
    python benchmarks/test_similar.py
"""

import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from doc_kg.dockg import DocNode
from doc_kg.index import SemanticIndex
from doc_kg.store import GraphStore

N_CHUNKS = 500  # small enough to be instant
DIM = 128  # fake dimension — no real model needed
THRESHOLD = 0.3  # low threshold so random vecs produce edges — proves the path works


class FakeEmbedder:
    dim = DIM

    def embed_texts(self, texts, **_):
        return np.random.randn(len(texts), DIM).tolist()

    def embed_query(self, q):
        return np.random.randn(DIM).tolist()


def make_store(db_path: Path) -> tuple[GraphStore, list[str]]:
    store = GraphStore(db_path)
    nodes = []
    edges = []
    for i in range(N_CHUNKS):
        nid = f"chunk:test/doc.md:{i:04d}"
        nodes.append(
            DocNode(
                id=nid,
                kind="chunk",
                name=f"chunk:{i:04d}",
                title=None,
                file_path="test/doc.md",
                char_start=i * 100,
                char_end=i * 100 + 100,
                heading_level=None,
                text=f"chunk text {i}",
            )
        )
    store.write(nodes, edges, wipe=True, quiet=True)
    return store, [n.id for n in nodes]


def make_vecs(n: int, dim: int) -> np.ndarray:
    vecs = np.random.randn(n, dim).astype(np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    return vecs / norms  # normalized — dot product == cosine similarity


def main():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.sqlite"
        lancedb_dir = Path(tmp) / "lancedb"

        print(f"Building synthetic store: {N_CHUNKS} chunks, dim={DIM}")
        store, node_ids = make_store(db_path)

        vecs = make_vecs(N_CHUNKS, DIM)

        # Seed the vector store. `_discover_similar_edges` works off the
        # in-memory vector matrix rather than the store, so this only has to
        # exist and be non-empty.
        #
        # NOTE: `lancedb_dir` is still the real parameter name on DocKG's
        # SemanticIndex and still takes a *directory* — a pre-0.20.0 leftover in
        # kg_utils, not something to rename. DocKG derives a sqlite-vec sidecar
        # from it. `_open_table`/`_tbl` were removed by DocKG 0.20.0, which is
        # what this script used to call.
        idx = SemanticIndex(lancedb_dir, embedder=FakeEmbedder())
        backend = idx._get_backend()
        backend.open(wipe=True)
        backend.upsert(
            [
                {
                    "id": nid,
                    "kind": "chunk",
                    "name": nid,
                    "title": "",
                    "file_path": "test/doc.md",
                    "text": f"text {i}",
                    "vector": vecs[i].tolist(),
                }
                for i, nid in enumerate(node_ids)
            ]
        )

        print(f"Calling _discover_similar_edges (threshold={THRESHOLD})...")
        n_edges = idx._discover_similar_edges(
            store,
            None,  # `tbl` is accepted for call-site compatibility and unused
            node_ids,
            vecs,
            k=5,
            threshold=THRESHOLD,
            quiet=False,
        )
        print(f"Done — {n_edges} SIMILAR_TO edges added")


if __name__ == "__main__":
    main()
