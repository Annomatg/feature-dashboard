"""
Token Normalization Utilities
==============================

Shared text tokenization used by both backfill migrations and live extraction.
"""

import re


def normalize_tokens(text: str) -> list[str]:
    """Normalize text into a list of word tokens.

    Rules (in order):
    1. Lowercase all text.
    2. Remove punctuation — replace any character that is not alphanumeric or
       whitespace with a space so that hyphenated / underscored words are split.
    3. Split on whitespace.
    4. Drop tokens shorter than 2 characters.

    No stemming, lemmatization, or stopword removal is applied.

    Args:
        text: Raw input string (feature name, description, etc.).

    Returns:
        List of normalized token strings.  Returns an empty list for empty or
        whitespace-only input.
    """
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return [token for token in text.split() if len(token) >= 2]
