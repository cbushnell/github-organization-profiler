from __future__ import annotations

from gh_org_profile.collectors.connections import build_topic_clusters


class TestBuildTopicClusters:
    def test_empty_input_returns_empty(self):
        assert build_topic_clusters({}) == {}

    def test_single_repo_single_topic(self):
        result = build_topic_clusters({"repo-a": ["python"]})
        assert result == {"python": ["repo-a"]}

    def test_multiple_repos_same_topic(self):
        result = build_topic_clusters({"repo-a": ["python"], "repo-b": ["python"]})
        assert sorted(result["python"]) == ["repo-a", "repo-b"]

    def test_repo_with_multiple_topics(self):
        result = build_topic_clusters({"repo-a": ["python", "data"]})
        assert result["python"] == ["repo-a"]
        assert result["data"] == ["repo-a"]

    def test_repo_with_no_topics_not_in_clusters(self):
        result = build_topic_clusters({"repo-a": ["python"], "repo-empty": []})
        for cluster in result.values():
            assert "repo-empty" not in cluster

    def test_topic_clusters_are_independent(self):
        result = build_topic_clusters({"repo-a": ["a"], "repo-b": ["b"]})
        assert "repo-a" not in result.get("b", [])
        assert "repo-b" not in result.get("a", [])

    def test_does_not_mutate_input(self):
        input_data = {"repo": ["topic1", "topic2"]}
        original = dict(input_data)
        build_topic_clusters(input_data)
        assert input_data == original
