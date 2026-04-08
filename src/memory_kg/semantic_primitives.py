#!/usr/bin/env python3
"""
semantic_primitives.py

Constants and utilities for the semantic memory layer.

Defines node kinds (assertion, event) and edge relations for semantic facts
with temporal reasoning, supersession, and contradiction handling.

Author: Eric G. Suchanek, PhD
License: Elastic-2.0
"""

from __future__ import annotations

import hashlib
import re

# ============================================================================
# Node kinds for semantic memory layer
# ============================================================================

SEMANTIC_NODE_KINDS = frozenset(("assertion", "event"))
"""Node kinds introduced by the semantic memory layer."""

# ============================================================================
# Edge relations for semantic memory layer
# ============================================================================

SEMANTIC_EDGE_RELS = frozenset((
    "SUPPORTS",       # chunk → assertion: chunk provides evidence for assertion
    "ABOUT",          # assertion → entity: assertion is about (subject) entity
    "REFERS_TO",      # assertion → entity: assertion refers to (object) entity
    "INVOLVES",       # event → entity: entity participated in event
    "DESCRIBES",      # chunk → event: chunk describes event
    "SUPERSEDES",     # assertion → assertion: newer assertion supersedes older
    "DERIVED_FROM",   # assertion → event: assertion derived from event
))
"""Edge relations introduced by the semantic memory layer."""

# ============================================================================
# Temporal field schemas (stored as JSON in DocNode.text)
# ============================================================================

ASSERTION_SCHEMA = {
    "subject": str,                  # entity name or entity_id
    "predicate": str,                # normalized relation (lives_in, works_at, etc.)
    "object": str,                   # literal value (location, org, etc.)
    "polarity": str,                 # affirmed | negated | uncertain
    "status": str,                   # active | superseded | contradicted | deprecated
    "valid_at_start": str | None,    # ISO date or year or None
    "valid_at_end": str | None,      # ISO date or year or None
    "confidence": float | None,      # 0-1 extraction confidence
}

EVENT_SCHEMA = {
    "event_type": str,               # relocation | employment_start | employment_end | publication | etc.
    "summary": str,                  # human-readable event description
    "time_start": str | None,        # ISO date / year / fuzzy temporal phrase
    "time_end": str | None,
    "time_uncertainty": str | None,  # year-only | month-only | fuzzy | None
}

# ============================================================================
# Stable ID builders
# ============================================================================


def assertion_node_id(chunk_id: str, predicate: str, subject_slug: str) -> str:
    """Build a stable assertion node ID.

    :param chunk_id: Source chunk ID (e.g. "chunk:docs/file.md:0001").
    :param predicate: Normalized predicate (e.g. "lives_in").
    :param subject_slug: Subject entity slug (e.g. "alice").
    :return: Stable assertion node ID.
    """
    key = f"{chunk_id}:{predicate}:{subject_slug}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]
    return f"assertion:{chunk_id}:{digest}"


def event_node_id(chunk_id: str, event_type: str, idx: int) -> str:
    """Build a stable event node ID.

    :param chunk_id: Source chunk ID.
    :param event_type: Event type (e.g. "relocation").
    :param idx: Index within chunk (0-based).
    :return: Stable event node ID.
    """
    return f"event:{chunk_id}:{idx:04d}"


def slugify(text: str) -> str:
    """Convert text to a URL-safe slug.

    :param text: Input text.
    :return: Lowercased, hyphenated slug.
    """
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text or "unknown"
