from __future__ import annotations

import pytest

from github_organization_profiler.client import get_github, get_org
from github_organization_profiler.collectors.commits import collect

DEFAULT_ORG = "github"


@pytest.mark.integration
class TestCommitsCollector:
    @pytest.fixture
    def hello_world(self, github_token):
        g = get_github(github_token)
        org = get_org(g, DEFAULT_ORG)
        return org.get_repo("linguist")

    def test_returns_dict_with_required_keys(self, hello_world):
        result = collect(hello_world, DEFAULT_ORG, max_age=0)
        for key in (
            "total_commits",
            "last_commit_at",
            "commit_frequency_30d",
            "commit_frequency_90d",
        ):
            assert key in result

    def test_total_commits_positive(self, hello_world):
        result = collect(hello_world, DEFAULT_ORG, max_age=0)
        assert result["total_commits"] > 0

    def test_30d_subset_of_90d(self, hello_world):
        result = collect(hello_world, DEFAULT_ORG, max_age=0)
        assert result["commit_frequency_30d"] <= result["commit_frequency_90d"]

    def test_last_commit_at_is_string_or_none(self, hello_world):
        result = collect(hello_world, DEFAULT_ORG, max_age=0)
        assert result["last_commit_at"] is None or isinstance(result["last_commit_at"], str)

    def test_frequency_fields_are_nonnegative(self, hello_world):
        result = collect(hello_world, DEFAULT_ORG, max_age=0)
        assert result["commit_frequency_30d"] >= 0
        assert result["commit_frequency_90d"] >= 0
