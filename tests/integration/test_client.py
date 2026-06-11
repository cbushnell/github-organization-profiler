from __future__ import annotations

import pytest

from gh_org_profile.client import get_github, get_org, graphql
from gh_org_profile.collectors.connections import _TOPICS_QUERY

DEFAULT_ORG = "github"


@pytest.mark.integration
class TestGetGithub:
    def test_returns_github_instance(self, github_token):
        from github import Github

        g = get_github(github_token)
        assert isinstance(g, Github)

    def test_authenticated_user_accessible(self, github_token):
        g = get_github(github_token)
        # Should not raise
        rate = g.get_rate_limit()
        assert rate.resources.core.limit > 0


@pytest.mark.integration
class TestGetOrg:
    def test_returns_org_with_correct_login(self, github_token):
        g = get_github(github_token)
        org = get_org(g, DEFAULT_ORG)
        assert org.login == DEFAULT_ORG

    def test_org_has_public_repos(self, github_token):
        g = get_github(github_token)
        org = get_org(g, DEFAULT_ORG)
        repos = list(org.get_repos(type="public"))
        assert len(repos) > 0


@pytest.mark.integration
class TestGraphQL:
    def test_topics_query_returns_data(self, github_token):
        data = graphql(github_token, _TOPICS_QUERY, {"org": DEFAULT_ORG, "cursor": None})
        assert "organization" in data
        assert "repositories" in data["organization"]

    def test_repos_have_expected_shape(self, github_token):
        data = graphql(github_token, _TOPICS_QUERY, {"org": DEFAULT_ORG, "cursor": None})
        nodes = data["organization"]["repositories"]["nodes"]
        assert isinstance(nodes, list)
        assert len(nodes) > 0
        first = nodes[0]
        assert "name" in first
        assert "repositoryTopics" in first
