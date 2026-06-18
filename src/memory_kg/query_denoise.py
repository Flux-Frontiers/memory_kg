"""query_denoise.py — recover the real question from a noise-padded query.

Some query sources wrap the actual question in conversational filler — several
sentences of unrelated chit-chat, *including decoy questions*, followed by a
pivot phrase and the real ask:

    "I was thinking about going for a hike ... Did you see the weather forecast?
     ... Oh, what I truly wanted to clarify is, What position does someone who
     has rock climbing as a hobby hold?"

That preamble pollutes the dense query embedding and pulls retrieval toward
irrelevant content. :func:`denoise_query` recovers just the trailing question.

Heuristic: the real ask is the **last** interrogative clause beginning with a
capitalized wh-word (``What``/``Which``/``How``/``Where``/``When``/``Who``/
``Whose``/``Why``). Decoy preamble questions are either yes/no ("Did I leave the
oven on?") or sit *before* the pivot, so the trailing wh-clause is the real one.
Pivot phrases use lowercase "what" ("what I wanted to ask is"), so capitalization
alone separates them from the question.

It is a **safe no-op on clean queries**: a normal single-question string has one
wh-word, at the start, so the function returns it unchanged. Opt-in via
``MemoryKG.query(..., denoise=True)`` / ``pack(..., denoise=True)``.
"""

from __future__ import annotations

import re

# Capitalized wh-word starting an interrogative clause. Word-boundary anchored so
# the lowercase pivot ("...what I wanted to ask is,") is never matched.
_WH_START = re.compile(r"\b(?:What|Which|How|Where|When|Who|Whose|Why)\b")


def denoise_query(question: str) -> str:
    """Return the trailing real question, stripping any distractor preamble.

    :param question: Raw (possibly noise-padded) query string.
    :return: The substring from the last capitalized wh-word to the end, trimmed.
        Returns the input unchanged when no wh-word is found.
    """
    matches = list(_WH_START.finditer(question))
    if not matches:
        return question.strip()
    return question[matches[-1].start() :].strip()
