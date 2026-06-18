"""Tests for memory_kg.query_denoise.denoise_query."""

from __future__ import annotations

from memory_kg.query_denoise import denoise_query


def test_strips_distractor_preamble_and_keeps_real_question():
    q = (
        "I was thinking about going for a hike this weekend, but then again, I "
        "remembered I need to finish that book. Did you see the weather forecast? "
        "Oh, what I truly wanted to clarify is,What position does someone who has "
        "rock climbing as a hobby hold?"
    )
    assert denoise_query(q) == "What position does someone who has rock climbing as a hobby hold?"


def test_handles_contraction_whats():
    q = "Random chatter here. Wait a minute, what I wanted to ask is,What's the capital of France?"
    assert denoise_query(q) == "What's the capital of France?"


def test_noop_on_clean_question():
    q = "What is the name of my niece's company?"
    assert denoise_query(q) == q


def test_noop_on_clean_non_what_question():
    q = "How many people live in Philadelphia, PA?"
    assert denoise_query(q) == q


def test_returns_input_when_no_wh_word():
    q = "Tell me about the budget."
    assert denoise_query(q) == "Tell me about the budget."


def test_picks_last_wh_clause_when_preamble_has_decoy_question():
    # Decoy "How do I keep track?" precedes the real ask; the trailing one wins.
    q = "How do I even keep track of these things? Oops, what I wanted: Where do I live?"
    assert denoise_query(q) == "Where do I live?"
