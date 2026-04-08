#!/usr/bin/env python3
"""
semantic_builder.py

SemanticMemoryBuilder — builds the semantic memory layer on top of MemoryKG.

Processes chunks to extract assertions and events, detects supersession (temporal
updates), and writes memory nodes and edges back to the same SQLite store.

Author: Eric G. Suchanek, PhD
License: Elastic-2.0
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from memory_kg.memorykg import DocEdge, DocNode
from memory_kg.semantic_extractor import AssertionExtractor, EventExtractor
from memory_kg.semantic_primitives import (
    SEMANTIC_EDGE_RELS,
    SEMANTIC_NODE_KINDS,
    assertion_node_id,
    event_node_id,
)

if TYPE_CHECKING:
    from memory_kg.store import GraphStore

logger = logging.getLogger(__name__)


@dataclass
class SemanticBuildStats:
    """Statistics returned by SemanticMemoryBuilder.build()."""

    events_added: int = 0
    assertions_added: int = 0
    edges_added: int = 0
    supersession_edges: int = 0
    assertions_superseded: int = 0

    def __str__(self) -> str:
        return (
            f"Semantic memory built:\n"
            f"  events:                {self.events_added}\n"
            f"  assertions:            {self.assertions_added}\n"
            f"  edges:                 {self.edges_added}\n"
            f"  supersession edges:    {self.supersession_edges}\n"
            f"  assertions superseded: {self.assertions_superseded}"
        )


# ============================================================================
# SemanticMemoryBuilder
# ============================================================================


class SemanticMemoryBuilder:
    """Build the semantic memory layer on top of MemoryKG."""

    def __init__(self, store: GraphStore) -> None:
        """Initialize builder with a GraphStore instance."""
        self.store = store
        self.event_extractor = EventExtractor()
        self.assertion_extractor = AssertionExtractor()

        self.nodes_to_write: dict[str, DocNode] = {}
        self.edges_to_write: dict[tuple[str, str, str], DocEdge] = {}
        self.assertions_by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)

    def build(
        self,
        *,
        enable_events: bool = True,
        enable_assertions: bool = True,
        detect_supersession: bool = True,
        quiet: bool = False,
    ) -> SemanticBuildStats:
        """Build the semantic memory layer."""
        stats = SemanticBuildStats()

        if not quiet:
            logger.info("Semantic memory: processing chunks...")

        chunks = self.store.query_nodes(kinds=["chunk"])
        for chunk in chunks:
            chunk_id = chunk["id"]

            entity_edges = self.store.edges_from(chunk_id, rel="MENTIONS_ENTITY")
            entity_ids = [e["dst"] for e in entity_edges]

            if enable_events:
                event_candidates = self.event_extractor.extract(
                    chunk.get("text") or "", [e.get("name", "") for e in entity_edges]
                )
                for i, event_cand in enumerate(event_candidates):
                    event_id = event_node_id(chunk_id, event_cand.event_type, i)

                    event_text = json.dumps({
                        "event_type": event_cand.event_type,
                        "summary": event_cand.summary,
                        "time_start": event_cand.time_start,
                        "time_end": event_cand.time_end,
                        "time_uncertainty": event_cand.time_uncertainty,
                    }, ensure_ascii=False)

                    self.nodes_to_write[event_id] = DocNode(
                        id=event_id,
                        kind="event",
                        name=f"{event_cand.event_type}_{i}",
                        title=event_cand.summary[:100],
                        file_path=chunk.get("file_path"),
                        char_start=chunk.get("char_start"),
                        char_end=chunk.get("char_end"),
                        heading_level=None,
                        text=event_text,
                    )

                    self.edges_to_write[(chunk_id, "DESCRIBES", event_id)] = DocEdge(
                        src=chunk_id, rel="DESCRIBES", dst=event_id
                    )

                    for entity_id in entity_ids:
                        self.edges_to_write[(event_id, "INVOLVES", entity_id)] = DocEdge(
                            src=event_id, rel="INVOLVES", dst=entity_id
                        )

                    stats.events_added += 1
                    stats.edges_added += 1 + len(entity_ids)

            if enable_assertions:
                assertion_candidates = self.assertion_extractor.extract(
                    chunk.get("text") or "", entity_ids
                )
                for assertion_cand in assertion_candidates:
                    assertion_id = assertion_node_id(
                        chunk_id, assertion_cand.predicate, assertion_cand.subject_entity_id
                    )

                    assertion_text = json.dumps({
                        "subject": assertion_cand.subject_entity_id,
                        "predicate": assertion_cand.predicate,
                        "object": assertion_cand.object_str,
                        "polarity": assertion_cand.polarity,
                        "status": "active",
                        "valid_at_start": None,
                        "valid_at_end": None,
                        "confidence": assertion_cand.confidence,
                    }, ensure_ascii=False)

                    self.nodes_to_write[assertion_id] = DocNode(
                        id=assertion_id,
                        kind="assertion",
                        name=f"{assertion_cand.subject_entity_id}_{assertion_cand.predicate}",
                        title=f"{assertion_cand.subject_entity_id} {assertion_cand.predicate} {assertion_cand.object_str}",
                        file_path=chunk.get("file_path"),
                        char_start=chunk.get("char_start"),
                        char_end=chunk.get("char_end"),
                        heading_level=None,
                        text=assertion_text,
                    )

                    self.edges_to_write[(chunk_id, "SUPPORTS", assertion_id)] = DocEdge(
                        src=chunk_id, rel="SUPPORTS", dst=assertion_id
                    )

                    subject_id = assertion_cand.subject_entity_id
                    self.edges_to_write[(assertion_id, "ABOUT", subject_id)] = DocEdge(
                        src=assertion_id, rel="ABOUT", dst=subject_id
                    )

                    if assertion_cand.object_entity_id:
                        self.edges_to_write[
                            (assertion_id, "REFERS_TO", assertion_cand.object_entity_id)
                        ] = DocEdge(
                            src=assertion_id,
                            rel="REFERS_TO",
                            dst=assertion_cand.object_entity_id,
                        )
                        stats.edges_added += 1

                    key = (assertion_cand.subject_entity_id, assertion_cand.predicate)
                    self.assertions_by_key[key].append({
                        "assertion_id": assertion_id,
                        "char_start": chunk.get("char_start", 0),
                        "object_str": assertion_cand.object_str,
                    })

                    stats.assertions_added += 1
                    stats.edges_added += 2

        if detect_supersession and enable_assertions:
            stats.supersession_edges, stats.assertions_superseded = (
                self._detect_supersession()
            )

        if not quiet:
            logger.info(f"Semantic memory: upserting {len(self.nodes_to_write)} nodes...")
        self.store._upsert_nodes(self.nodes_to_write.values())

        if not quiet:
            logger.info(f"Semantic memory: upserting {len(self.edges_to_write)} edges...")
        self.store._upsert_edges(self.edges_to_write.values())

        if not quiet:
            logger.info(str(stats))

        return stats

    def _detect_supersession(self) -> tuple[int, int]:
        """Detect supersession (temporal updates) among assertions."""
        supersession_edges = 0
        superseded_count = 0

        for key, assertions in self.assertions_by_key.items():
            if len(assertions) < 2:
                continue

            sorted_assertions = sorted(assertions, key=lambda a: a["char_start"])

            for i in range(len(sorted_assertions) - 1):
                older = sorted_assertions[i]
                newer = sorted_assertions[i + 1]

                self.edges_to_write[(newer["assertion_id"], "SUPERSEDES", older["assertion_id"])] = (
                    DocEdge(
                        src=newer["assertion_id"],
                        rel="SUPERSEDES",
                        dst=older["assertion_id"],
                    )
                )
                supersession_edges += 1

                older_node = self.nodes_to_write.get(older["assertion_id"])
                if older_node:
                    old_text = json.loads(older_node.text or "{}")
                    old_text["status"] = "superseded"
                    self.nodes_to_write[older["assertion_id"]] = DocNode(
                        id=older_node.id,
                        kind=older_node.kind,
                        name=older_node.name,
                        title=older_node.title,
                        file_path=older_node.file_path,
                        char_start=older_node.char_start,
                        char_end=older_node.char_end,
                        heading_level=older_node.heading_level,
                        text=json.dumps(old_text, ensure_ascii=False),
                    )
                    superseded_count += 1

        return supersession_edges, superseded_count
