"""MemoryKG — hybrid semantic + structural knowledge graph for document corpora."""

from memory_kg.kg import MemoryKG
from memory_kg.semantic_builder import SemanticBuildStats, SemanticMemoryBuilder
from memory_kg.semantic_extractor import (
    AssertionCandidate,
    AssertionExtractor,
    EventCandidate,
    EventExtractor,
)
from memory_kg.semantic_primitives import (
    ASSERTION_SCHEMA,
    EVENT_SCHEMA,
    SEMANTIC_EDGE_RELS,
    SEMANTIC_NODE_KINDS,
    assertion_node_id,
    event_node_id,
    slugify,
)

__all__ = [
    "MemoryKG",
    "SemanticMemoryBuilder",
    "SemanticBuildStats",
    "EventExtractor",
    "EventCandidate",
    "AssertionExtractor",
    "AssertionCandidate",
    "SEMANTIC_NODE_KINDS",
    "SEMANTIC_EDGE_RELS",
    "ASSERTION_SCHEMA",
    "EVENT_SCHEMA",
    "assertion_node_id",
    "event_node_id",
    "slugify",
]
