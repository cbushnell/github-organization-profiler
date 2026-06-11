"""Integration tests for the README LLM classifier.

NOTE: These tests make real calls to the Anthropic API and will incur a
minor cost (one claude-haiku-4-5 inference, ~256 output tokens).
Only run intentionally via --run-integration.
"""

from __future__ import annotations

import anthropic
import pytest

from gh_org_profile.classifiers.readme import _classify_one

# A short but clearly distinctive README for a Python CLI tool.
# Distinctive enough that the model should reliably categorise it as "CLI Tool".
_CLI_README = """\
# deploy-cli

A command-line tool for deploying applications to cloud infrastructure.

## Installation

```bash
pip install deploy-cli
```

## Usage

```bash
deploy-cli --env production --region us-east-1 app.yaml
```

## Commands

- `deploy` — Push a new release to the target environment
- `rollback` — Revert to the previous stable release
- `status` — Show current deployment state across all regions

## Configuration

All options can be provided via CLI flags or a `deploy.yml` config file.
"""

_VALID_CATEGORIES = {
    "API / Data Service",
    "CLI Tool",
    "Python Library / SDK",
    "Infrastructure / IaC",
    "Frontend / UI",
    "Design System",
    "Documentation / Reference",
    "Data Pipeline / ETL",
    "ML / AI",
    "Configuration / Shared Tooling",
    "Example / Demo",
    "Archive / Deprecated",
    "Other",
}


@pytest.mark.integration
class TestReadmeClassifierLive:
    """Live LLM tests — each test method that calls the API costs ~1 Haiku inference."""

    def test_classifies_cli_readme(self, anthropic_api_key):
        """Single API call. Verifies end-to-end: request → JSON parse → valid result."""
        client = anthropic.Anthropic(api_key=anthropic_api_key)
        result = _classify_one(client, "deploy-cli", _CLI_README)

        assert result is not None, (
            "_classify_one returned None — the API call succeeded but the response "
            "could not be parsed as JSON. Check _parse_json and the model output."
        )
        assert result.get("category") in _VALID_CATEGORIES, (
            f"Unexpected category {result.get('category')!r}. "
            f"Expected one of: {sorted(_VALID_CATEGORIES)}"
        )
        assert result.get("confidence") in ("high", "medium", "low"), (
            f"Unexpected confidence {result.get('confidence')!r}"
        )
        assert isinstance(result.get("summary"), str) and result["summary"].strip(), (
            "summary should be a non-empty string"
        )
        # The CLI README should not be misclassified as a completely unrelated category
        assert result["category"] in ("CLI Tool", "Infrastructure / IaC", "Other"), (
            f"Model classified a clearly CLI README as {result['category']!r}"
        )
