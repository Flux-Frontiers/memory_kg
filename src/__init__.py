"""
MemoryKG — Document Knowledge Graph

Builds a semantically searchable knowledge graph from .md and .txt files.
Same architecture as CodeKG, adapted for natural-language documents.

Pipeline:
    corpus → DocGraph (chunker) → GraphStore (SQLite) → SemanticIndex (LanceDB)

Key classes:
    MemoryKG       — top-level orchestrator
    DocGraph    — corpus parsing and chunking
    GraphStore  — SQLite persistence
    SemanticIndex — LanceDB vector index + SIMILAR_TO edge discovery
    TextChunker — semantic text segmentation

Author: Eric G. Suchanek, PhD
"""

from memory_kg.graph import DocGraph
from memory_kg.index import Embedder, SemanticIndex, SentenceTransformerEmbedder
from memory_kg.kg import BuildStats, MemoryKG, QueryResult, TextPack
from memory_kg.memorykg import DEFAULT_MODEL, DocEdge, DocNode
from memory_kg.store import GraphStore
from memory_kg.topics import TopicExtractor

__all__ = [
    "MemoryKG",
    "DocGraph",
    "GraphStore",
    "SemanticIndex",
    "SentenceTransformerEmbedder",
    "Embedder",
    "DocNode",
    "DocEdge",
    "BuildStats",
    "QueryResult",
    "TextPack",
    "DEFAULT_MODEL",
    "TopicExtractor",
]

__version__ = "0.5.1"
