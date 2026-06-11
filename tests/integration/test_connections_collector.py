from __future__ import annotations

import pytest

from gh_org_profile.client import get_github, get_org
from gh_org_profile.collectors.connections import (
    build_topic_clusters,
    collect_active,
    fetch_all_topics,
)

DEFAULT_ORG = "github"


@pytest.mark.integration
class TestFetchAllTopics:
    def test_returns_dict(self, github_token):
        result = fetch_all_topics(github_token, DEFAULT_ORG)
        assert isinstance(result, dict)

    def test_hello_world_key_present(self, github_token):
        result = fetch_all_topics(github_token, DEFAULT_ORG)
        assert "linguist" in result

    def test_topics_are_lists_of_strings(self, github_token):
        result = fetch_all_topics(github_token, DEFAULT_ORG)
        for repo_name, topics in result.items():
            assert isinstance(topics, list), f"{repo_name} topics should be a list"
            for t in topics:
                assert isinstance(t, str)


@pytest.mark.integration
class TestBuildTopicClusters:
    def test_clusters_from_real_data(self, github_token):
        repo_topics = fetch_all_topics(github_token, DEFAULT_ORG)
        clusters = build_topic_clusters(repo_topics)
        assert isinstance(clusters, dict)
        for topic, repos in clusters.items():
            assert isinstance(topic, str)
            assert isinstance(repos, list)
            assert all(isinstance(r, str) for r in repos)


@pytest.mark.integration
class TestCollectActive:
    @pytest.fixture
    def hello_world(self, github_token):
        g = get_github(github_token)
        org = get_org(g, DEFAULT_ORG)
        return org.get_repo("linguist")

    def test_returns_expected_keys(self, hello_world, github_token):
        result = collect_active(hello_world, github_token, DEFAULT_ORG, max_age=0)
        for key in ("fork_of", "forks", "internal_package_deps", "reusable_workflow_refs"):
            assert key in result

    def test_forks_is_list(self, hello_world, github_token):
        result = collect_active(hello_world, github_token, DEFAULT_ORG, max_age=0)
        assert isinstance(result["forks"], list)

    def test_internal_package_deps_is_list(self, hello_world, github_token):
        result = collect_active(hello_world, github_token, DEFAULT_ORG, max_age=0)
        assert isinstance(result["internal_package_deps"], list)

    def test_reusable_workflow_refs_is_list(self, hello_world, github_token):
        result = collect_active(hello_world, github_token, DEFAULT_ORG, max_age=0)
        assert isinstance(result["reusable_workflow_refs"], list)
