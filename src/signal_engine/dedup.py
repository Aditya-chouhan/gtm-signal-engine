"""Cross-source entity resolution.

SEC and GitHub signals never need this: SEC hits are already keyed to one
CIK, GitHub releases are already keyed to one org slug, and both keys are
looked up from entities.ENTITIES before a request is even made -- there is
no ambiguity to resolve.

HN is the one source that starts from free text, so it's the one place a
raw hit has to be matched back to a canonical entity after the fact. This
module makes that matching, and its failure mode, explicit rather than
silently discarding or silently guessing.
"""

from __future__ import annotations

import re

from .entities import ENTITIES

_WORD_BOUNDARY = "(?:^|[^A-Za-z0-9])"


def _alias_pattern(alias: str) -> re.Pattern:
    return re.compile(_WORD_BOUNDARY + re.escape(alias) + r"(?:$|[^A-Za-z0-9])")


def resolve_hn_text(text: str) -> str | None:
    """Whole-word, case-sensitive match against every entity's HN aliases.

    Returns the matching ticker, or None if zero or more-than-one distinct
    entities match. The more-than-one case is a real and expected outcome
    (e.g. a story discussing two of these companies together) -- dropping
    it rather than guessing is the honest choice, since guessing which
    entity a two-company story "belongs to" would be inventing precision
    that doesn't exist. Callers should count and report drops, not just
    swallow them: see scripts/fetch_live_signals.py's reported
    `hn_ambiguous_dropped` / `hn_no_match_dropped` counts.
    """
    matched = set()
    for entity in ENTITIES:
        for alias in entity.hn_aliases:
            if _alias_pattern(alias).search(text):
                matched.add(entity.ticker)
                break
    if len(matched) == 1:
        return next(iter(matched))
    return None
