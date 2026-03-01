"""
Unit tests for api.tokens.normalize_tokens
============================================

Covers:
- Empty / whitespace-only input
- Mixed-case input (must be lowercased)
- Punctuation stripping
- Short token filtering (len < 2 dropped)
- Numeric tokens
- Mixed real-world inputs
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.tokens import normalize_tokens


# ---------------------------------------------------------------------------
# Empty / whitespace-only input
# ---------------------------------------------------------------------------

def test_empty_string():
    assert normalize_tokens("") == []


def test_whitespace_only():
    assert normalize_tokens("   \t\n  ") == []


# ---------------------------------------------------------------------------
# Mixed-case → lowercase
# ---------------------------------------------------------------------------

def test_lowercase_conversion():
    result = normalize_tokens("Hello World")
    assert result == ["hello", "world"]


def test_all_uppercase():
    result = normalize_tokens("FEATURE REQUEST")
    assert result == ["feature", "request"]


def test_mixed_case():
    result = normalize_tokens("SQLAlchemy ORM Model")
    assert result == ["sqlalchemy", "orm", "model"]


# ---------------------------------------------------------------------------
# Punctuation stripping
# ---------------------------------------------------------------------------

def test_punctuation_stripped():
    result = normalize_tokens("Hello, World!")
    assert result == ["hello", "world"]


def test_hyphenated_word_split():
    """Hyphens count as punctuation so 'auto-restart' → ['auto', 'restart']."""
    result = normalize_tokens("auto-restart")
    assert result == ["auto", "restart"]


def test_underscore_split():
    result = normalize_tokens("feature_list")
    assert result == ["feature", "list"]


def test_parentheses_stripped():
    result = normalize_tokens("normalize_tokens(text: str) -> list[str]")
    assert result == ["normalize", "tokens", "text", "str", "list", "str"]


def test_colon_stripped():
    result = normalize_tokens("key: value")
    assert result == ["key", "value"]


def test_period_stripped():
    result = normalize_tokens("end of sentence.")
    assert result == ["end", "of", "sentence"]


def test_all_punctuation():
    result = normalize_tokens("!@#$%^&*()")
    assert result == []


# ---------------------------------------------------------------------------
# Short token filtering (len < 2 dropped)
# ---------------------------------------------------------------------------

def test_single_char_tokens_dropped():
    result = normalize_tokens("a b c d word")
    assert result == ["word"]


def test_length_exactly_two_kept():
    result = normalize_tokens("an ok go")
    assert result == ["an", "ok", "go"]


def test_single_char_after_punctuation_strip():
    """'a.' → 'a' (length 1) → dropped."""
    result = normalize_tokens("a. the end")
    assert result == ["the", "end"]


# ---------------------------------------------------------------------------
# Numeric tokens
# ---------------------------------------------------------------------------

def test_numeric_tokens_kept():
    result = normalize_tokens("version 42 release")
    assert result == ["version", "42", "release"]


def test_single_digit_dropped():
    result = normalize_tokens("step 1 done")
    assert result == ["step", "done"]


def test_alphanumeric_token():
    result = normalize_tokens("v2 api endpoint")
    assert result == ["v2", "api", "endpoint"]


# ---------------------------------------------------------------------------
# Real-world feature name / description samples
# ---------------------------------------------------------------------------

def test_feature_name_sample():
    result = normalize_tokens("Token normalization function")
    assert result == ["token", "normalization", "function"]


def test_description_sample():
    result = normalize_tokens(
        "Implement a shared token normalization function used by both backfill and live extraction."
    )
    assert "implement" in result
    assert "shared" in result
    assert "token" in result
    assert "normalization" in result
    assert "function" in result
    # Single-char word 'a' is dropped; 'by' (len 2) is kept
    assert "a" not in result
    assert "by" in result


def test_returns_list_type():
    assert isinstance(normalize_tokens("hello world"), list)


def test_no_duplicates_in_output_for_repeated_word():
    """normalize_tokens does NOT deduplicate — that's the caller's job."""
    result = normalize_tokens("test test test")
    assert result == ["test", "test", "test"]
