from __future__ import annotations

import pytest

DEFAULT_ORG = "github"
from gh_org_profile.client import get_github, get_org
from gh_org_profile.collectors.repos import collect_repo_metadata


@pytest.mark.integration
class TestCollectRepoMetadata:
    @pytest.fixture
    def org_obj(self, github_token):
        g = get_github(github_token)
        return get_org(g, DEFAULT_ORG)

    def test_returns_nonempty_lists(self, org_obj, github_token):
        repos, repo_data = collect_repo_metadata(org_obj, DEFAULT_ORG, max_age=0, max_repos=5)
        assert len(repos) > 0
        assert len(repo_data) > 0

    def test_returns_exactly_max_repos(self, org_obj, github_token):
        repos, repo_data = collect_repo_metadata(org_obj, DEFAULT_ORG, max_age=0, max_repos=5)
        assert len(repos) == 5
        assert len(repo_data) == 5

    def test_first_repo_metadata_shape(self, org_obj, github_token):
        repos, repo_data = collect_repo_metadata(org_obj, DEFAULT_ORG, max_age=0, max_repos=5)
        meta = repo_data[repos[0].name]
        assert "name" in meta
        assert "pushed_at" in meta
        assert "open_issues_count" in meta
        assert "forks_count" in meta
        assert "is_archived" in meta
        assert "is_fork" in meta

    def test_first_repo_readme_is_string_or_none(self, org_obj, github_token):
        repos, repo_data = collect_repo_metadata(org_obj, DEFAULT_ORG, max_age=0, max_repos=5)
        readme = repo_data[repos[0].name].get("readme")
        assert readme is None or isinstance(readme, str)

    def test_all_repos_have_name_field(self, org_obj, github_token):
        _, repo_data = collect_repo_metadata(org_obj, DEFAULT_ORG, max_age=0, max_repos=5)
        for name, meta in repo_data.items():
            assert meta["name"] == name
