"""Unit tests for the local keyword-based README classifier."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from github_organization_profiler.classifiers.local import (
    _NULL_CLASS,
    _extract_summary,
    classify_one,
    classify_one_cached,
)


class TestClassifyOne:
    def test_empty_inputs_returns_null_class(self):
        result = classify_one("repo", "", None, [])
        assert result == _NULL_CLASS

    def test_description_alone_can_classify(self):
        result = classify_one("myrepo", "", "A CLI tool for deployment", ["cli"])
        assert result["category"] == "CLI Tool"

    def test_topics_alone_can_classify(self):
        result = classify_one("myrepo", "", None, ["machine-learning", "pytorch"])
        assert result["category"] == "ML / AI"

    def test_cli_keywords_high_confidence(self):
        result = classify_one(
            "deploy-cli",
            "A command-line tool. Usage: deploy-cli --flag subcommand. Built with typer.",
            "CLI deployment tool",
            ["cli"],
        )
        assert result["category"] == "CLI Tool"
        assert result["confidence"] == "high"

    def test_ml_keywords_high_confidence(self):
        result = classify_one(
            "train-model",
            "PyTorch fine-tuning framework for NLP models. Supports deep learning and embeddings.",
            None,
            ["pytorch", "nlp"],
        )
        assert result["category"] == "ML / AI"
        assert result["confidence"] == "high"

    def test_infra_keywords(self):
        result = classify_one(
            "infra-modules",
            "Terraform modules for AWS EKS clusters. Includes helm charts.",
            None,
            ["terraform", "kubernetes"],
        )
        assert result["category"] == "Infrastructure / IaC"

    def test_archive_takes_precedence_over_ml(self):
        result = classify_one(
            "old-model",
            "Deprecated. This repo is no longer maintained. Previously a PyTorch machine learning framework.",
            None,
            [],
        )
        assert result["category"] == "Archive / Deprecated"

    def test_topic_weight_medium_confidence(self):
        # Single topic keyword hit = 2 points → medium
        result = classify_one("myrepo", "Generic project description.", None, ["cli"])
        assert result["category"] == "CLI Tool"
        assert result["confidence"] == "medium"

    def test_zero_score_yields_other_low(self):
        result = classify_one("myrepo", "A thing that does stuff with widgets.", None, [])
        assert result["category"] == "Other"
        assert result["confidence"] == "low"

    def test_returned_category_is_valid(self):
        from github_organization_profiler.classifiers.local import _VALID_CATEGORIES

        result = classify_one("any", "random text", None, [])
        assert result["category"] in _VALID_CATEGORIES

    def test_confidence_values_are_valid(self):
        result = classify_one("any", "random text", None, [])
        assert result["confidence"] in {"high", "medium", "low", "n/a"}

    def test_readme_truncated_to_8000_chars(self):
        # Should not crash on very long readmes
        long_readme = "terraform " * 2000  # 20000 chars
        result = classify_one("infra", long_readme, None, [])
        assert result["category"] == "Infrastructure / IaC"


class TestExtractSummary:
    def test_extracts_first_paragraph(self):
        readme = "This is a great tool. It does things. And more things."
        result = _extract_summary(readme, None)
        assert "This is a great tool." in result
        assert "And more things." not in result

    def test_skips_leading_heading(self):
        readme = "# My Project\n\nThis tool helps with deployment."
        result = _extract_summary(readme, None)
        assert "My Project" not in result
        assert "deployment" in result

    def test_skips_badge_lines(self):
        readme = "[![Build](badge.svg)](link)\n\nActual description here."
        result = _extract_summary(readme, None)
        assert "Build" not in result
        assert "Actual description" in result

    def test_truncates_at_two_sentences(self):
        readme = "First sentence. Second sentence. Third sentence should be cut."
        result = _extract_summary(readme, None)
        assert "Third" not in result
        assert "Second sentence." in result

    def test_falls_back_to_description_for_short_paragraph(self):
        readme = "# Title\n\nHi."
        result = _extract_summary(readme, "A longer, more useful description.")
        assert result == "A longer, more useful description."

    def test_returns_none_when_both_empty(self):
        assert _extract_summary("", None) is None
        assert _extract_summary("   ", "") is None

    def test_no_trailing_whitespace(self):
        readme = "A tool for doing things.  "
        result = _extract_summary(readme, None)
        assert result == result.strip()


@pytest.mark.parametrize(
    "repo_name,readme,topics,expected_category",
    [
        ("ml-trainer", "PyTorch model fine-tuning for NLP and deep learning tasks.", ["pytorch", "nlp"], "ML / AI"),
        ("etl-runner", "Apache Airflow DAG for Kafka stream data ingestion.", ["etl", "airflow"], "Data Pipeline / ETL"),
        ("infra-core", "Terraform and Ansible modules for Kubernetes clusters.", ["terraform", "kubernetes"], "Infrastructure / IaC"),
        ("design-kit", "Our design system and component library using Storybook and design tokens.", ["design-system", "storybook"], "Design System"),
        ("deploy-cli", "A command-line tool. Usage: deploy-cli --flag. Built with click.", ["cli"], "CLI Tool"),
        ("data-api", "REST API and GraphQL endpoint for data service. Built with FastAPI.", ["api", "fastapi"], "API / Data Service"),
        ("web-app", "React and Next.js frontend application for the dashboard.", ["react", "frontend"], "Frontend / UI"),
        ("py-sdk", "Python library and SDK. pip install mysdk. Distributed on PyPI.", ["python", "sdk"], "Python Library / SDK"),
        ("dotfiles", "Shared dotfiles and linting configuration with pre-commit hooks.", ["dotfiles", "configuration"], "Configuration / Shared Tooling"),
        ("demo-app", "Example and tutorial quickstart template for getting started.", ["example", "tutorial"], "Example / Demo"),
        ("docs-site", "Documentation and reference wiki built with MkDocs.", ["documentation", "docs"], "Documentation / Reference"),
        ("old-service", "Deprecated. This service is archived and no longer maintained.", ["archived"], "Archive / Deprecated"),
        ("misc-tool", "A thing that manages widgets.", [], "Other"),
    ],
)
def test_category_coverage(repo_name, readme, topics, expected_category):
    result = classify_one(repo_name, readme, None, topics)
    assert result["category"] == expected_category


class TestClassifyOneCached:
    def test_writes_to_readme_class_local_key(self, tmp_path, monkeypatch):
        import github_organization_profiler.cache as cache_mod

        monkeypatch.setattr(cache_mod, "_BASE", tmp_path)
        classify_one_cached("myrepo", "A CLI tool with argparse.", None, ["cli"], "myorg", 24)
        cache_file = tmp_path / "myorg" / "myrepo" / "readme_class_local.json"
        assert cache_file.exists()
        data = json.loads(cache_file.read_text())
        assert data["category"] == "CLI Tool"

    def test_returns_cached_result_without_reclassifying(self, tmp_path, monkeypatch):
        import github_organization_profiler.cache as cache_mod
        from github_organization_profiler.classifiers import local as local_mod

        monkeypatch.setattr(cache_mod, "_BASE", tmp_path)

        call_count = 0
        original = local_mod.classify_one

        def counting_classify(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(local_mod, "classify_one", counting_classify)

        classify_one_cached("myrepo", "A CLI tool.", None, ["cli"], "myorg", 24)
        classify_one_cached("myrepo", "A CLI tool.", None, ["cli"], "myorg", 24)
        assert call_count == 1

    def test_empty_readme_is_cached_as_null(self, tmp_path, monkeypatch):
        import github_organization_profiler.cache as cache_mod

        monkeypatch.setattr(cache_mod, "_BASE", tmp_path)
        result = classify_one_cached("myrepo", "", None, [], "myorg", 24)
        assert result == _NULL_CLASS
        cache_file = tmp_path / "myorg" / "myrepo" / "readme_class_local.json"
        assert cache_file.exists()
