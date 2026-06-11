"""Unit tests for the README classifier — no external calls."""

from __future__ import annotations

from gh_org_profile.classifiers.readme import _parse_json


class TestParseJson:
    """Regression guards for the JSON parser fix.

    Before the fix, json.loads() raised on fenced model output and the bare
    except silently returned _NULL_CLASS, consuming API tokens with no result.
    """

    def test_handles_markdown_fences(self):
        fenced = (
            '```json\n{"category": "CLI Tool", "summary": "A tool.", "confidence": "high"}\n```'
        )
        result = _parse_json(fenced)
        assert result["category"] == "CLI Tool"
        assert result["confidence"] == "high"

    def test_handles_fence_without_language_tag(self):
        fenced = '```\n{"category": "Other", "summary": "x", "confidence": "low"}\n```'
        result = _parse_json(fenced)
        assert result["category"] == "Other"

    def test_handles_bare_json(self):
        bare = '{"category": "ML / AI", "summary": "An AI model.", "confidence": "medium"}'
        result = _parse_json(bare)
        assert result["category"] == "ML / AI"
