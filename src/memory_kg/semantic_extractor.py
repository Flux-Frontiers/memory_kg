#!/usr/bin/env python3
"""
semantic_extractor.py

Deterministic, regex-based extractors for semantic memory.

- EventExtractor: finds temporally anchored occurrences (relocation, employment, publication, etc.)
- AssertionExtractor: finds subject-predicate-object facts from entity mentions

Author: Eric G. Suchanek, PhD
License: Elastic-2.0
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ============================================================================
# Temporal patterns
# ============================================================================

ISO_DATE_PATTERN = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
YEAR_PATTERN = re.compile(r"\b((19|20)\d{2})\b")
MONTH_YEAR_PATTERN = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December"
    r"|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+(20\d{2}|19\d{2})\b",
    re.IGNORECASE,
)
RELATIVE_TEMPORAL_PATTERN = re.compile(
    r"\b(last|this|next)\s+(year|month|week|decade)\b"
    r"|in\s+(20\d{2}|19\d{2})\b"
    r"|during\s+\d{4}\b",
    re.IGNORECASE,
)

# ============================================================================
# Event verb patterns
# ============================================================================

VERB_TO_EVENT_TYPE = {
    "moved": "relocation",
    "relocated": "relocation",
    "moved_to": "relocation",
    "joined": "employment_start",
    "started": "employment_start",
    "began": "employment_start",
    "hired": "employment_start",
    "left": "employment_end",
    "quit": "employment_end",
    "resigned": "employment_end",
    "fired": "employment_end",
    "married": "marriage",
    "divorced": "divorce",
    "published": "publication",
    "released": "publication",
    "launched": "publication",
}

VERB_PATTERN = re.compile(
    r"\b(moved|relocated|joined|started|began|hired|left|quit|resigned|fired|"
    r"married|divorced|published|released|launched)"
    r"(?:\s+to)?\b",
    re.IGNORECASE,
)

# ============================================================================
# Assertion predicate patterns
# ============================================================================

PREDICATE_PATTERNS = [
    (r"(?:is|was|are|were)\s+(?:a|an|the)?\s*(.+?)(?:\.|,|$)", "is_a"),
    (r"(?:lives?|lived?)\s+in\b", "lives_in"),
    (r"(?:works?|worked?)\s+(?:at|for)\b", "works_at"),
    (r"(?:has|have|had)\s+(?:a|an)?\s*(.+?)(?:\.|,|$)", "has"),
    (r"(?:likes?|prefers?|enjoys?)\s+(.+?)(?:\.|,|$)", "prefers"),
    (r"(?:married?)\s+(?:to)?\s*(.+?)(?:\.|,|$)", "married_to"),
    (r"(?:owns?)\s+(.+?)(?:\.|,|$)", "owns"),
]

PREDICATE_REGEX_PATTERNS = [
    (re.compile(pat, re.IGNORECASE), pred) for pat, pred in PREDICATE_PATTERNS
]

# ============================================================================
# Result types
# ============================================================================


@dataclass
class EventCandidate:
    """A candidate event extracted from text."""

    event_type: str
    summary: str
    time_start: str | None
    time_end: str | None = None
    time_uncertainty: str | None = None
    entities_involved: list[str] | None = None
    confidence: float = 0.8

    def __post_init__(self):
        if self.entities_involved is None:
            self.entities_involved = []


@dataclass
class AssertionCandidate:
    """A candidate assertion (SVO triple) extracted from text."""

    subject_entity_id: str
    predicate: str
    object_str: str
    object_entity_id: str | None = None
    polarity: str = "affirmed"
    confidence: float = 0.8


# ============================================================================
# EventExtractor
# ============================================================================


class EventExtractor:
    """Extract temporally anchored events from text."""

    def extract(
        self,
        text: str,
        entity_names: list[str],
        window_chars: int = 100,
        max_events: int = 5,
    ) -> list[EventCandidate]:
        """Extract event candidates from text."""
        events: list[EventCandidate] = []

        for verb_match in VERB_PATTERN.finditer(text):
            verb = verb_match.group(1).lower()
            event_type = VERB_TO_EVENT_TYPE.get(verb)
            if not event_type:
                continue

            start = max(0, verb_match.start() - 100)
            end = min(len(text), verb_match.end() + window_chars)
            context = text[start:end]

            time_start = self._extract_temporal(context)
            if not time_start:
                continue

            entities_in_context = [e for e in entity_names if e.lower() in context.lower()]
            summary_text = context.strip()[:150]
            summary = f"{' '.join(entities_in_context)} - {summary_text}"

            events.append(
                EventCandidate(
                    event_type=event_type,
                    summary=summary,
                    time_start=time_start,
                    entities_involved=entities_in_context,
                    confidence=0.7,
                )
            )

            if len(events) >= max_events:
                break

        return events

    @staticmethod
    def _extract_temporal(text: str) -> str | None:
        """Extract a temporal anchor from text."""
        m = ISO_DATE_PATTERN.search(text)
        if m:
            return m.group(0)

        m = MONTH_YEAR_PATTERN.search(text)
        if m:
            return m.group(0)

        m = YEAR_PATTERN.search(text)
        if m:
            return m.group(1)

        m = RELATIVE_TEMPORAL_PATTERN.search(text)
        if m:
            return m.group(0)

        return None


# ============================================================================
# AssertionExtractor
# ============================================================================


class AssertionExtractor:
    """Extract subject-predicate-object facts from text."""

    def extract(
        self,
        text: str,
        entity_ids: list[str],
        entity_names_map: dict[str, str] | None = None,
        max_assertions: int = 8,
    ) -> list[AssertionCandidate]:
        """Extract assertion candidates from text."""
        assertions: list[AssertionCandidate] = []

        if not entity_ids:
            return assertions

        for entity_id in entity_ids:
            if len(assertions) >= max_assertions:
                break

            for pattern, predicate in PREDICATE_REGEX_PATTERNS:
                matches = list(pattern.finditer(text))
                if not matches:
                    continue

                for match in matches:
                    if len(assertions) >= max_assertions:
                        break

                    object_str = None
                    if len(match.groups()) > 0 and match.group(len(match.groups())):
                        object_str = match.group(len(match.groups())).strip()
                    else:
                        end_pos = match.end()
                        end_chunk = text[end_pos : end_pos + 50].split(".")[0]
                        if end_chunk:
                            object_str = end_chunk.strip()

                    if object_str:
                        assertions.append(
                            AssertionCandidate(
                                subject_entity_id=entity_id,
                                predicate=predicate,
                                object_str=object_str,
                                confidence=0.6,
                            )
                        )

        return assertions[:max_assertions]
