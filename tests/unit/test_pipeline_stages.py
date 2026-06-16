"""Unit tests for selective stage execution."""

from __future__ import annotations

from unittest.mock import patch

from typer.testing import CliRunner

from github_organization_profiler.cli import app
from github_organization_profiler.pipeline import _ALL_STAGES, _seed_from_prev_report

runner = CliRunner()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_PREV_REPORT = {
    "users": {"alice": {"login": "alice", "name": "Alice"}},
    "repos": {
        "repo-a": {
            "activity": {
                "total_commits": 42,
                "last_commit_at": "2026-01-01T00:00:00",
                "commit_frequency_30d": 5,
                "commit_frequency_90d": 15,
            },
            "quality": {"has_license": True, "quality_score": 3},
            "readme_class": {"category": "CLI Tool", "summary": "A tool.", "confidence": "high"},
            "connections": {
                "topics": ["cli", "python"],
                "fork_of": None,
                "forks": [],
                "internal_package_deps": [],
                "reusable_workflow_refs": [],
            },
        },
    },
    "connections_summary": {
        "topic_clusters": {"cli": ["repo-a"], "python": ["repo-a"]},
    },
}


def _empty_dicts():
    return {}, {}, {}, {}, {}, {}, {}


# ---------------------------------------------------------------------------
# CLI: --stages parsing and validation
# ---------------------------------------------------------------------------


class TestStagesCliParsing:
    def test_invalid_stage_exits_with_error(self):
        result = runner.invoke(app, ["--org", "x", "--token", "t", "--stages", "badstage"])
        assert result.exit_code == 1
        assert "unknown stage" in result.output

    def test_multiple_invalid_stages_listed(self):
        result = runner.invoke(app, ["--org", "x", "--token", "t", "--stages", "foo,bar"])
        assert result.exit_code == 1
        assert "unknown stage" in result.output

    def test_full_refresh_and_stages_mutually_exclusive(self):
        result = runner.invoke(
            app, ["--org", "x", "--token", "t", "--stages", "readme", "--full-refresh"]
        )
        assert result.exit_code == 1
        assert "mutually exclusive" in result.output

    def test_valid_stages_accepted(self):
        # Mock pipeline.run so no filesystem or network access occurs
        with patch("github_organization_profiler.pipeline.run") as mock_run:
            result = runner.invoke(
                app, ["--org", "myorg", "--token", "t", "--stages", "readme,contributors"]
            )
        assert result.exit_code == 0
        assert mock_run.called
        assert mock_run.call_args.kwargs["stages"] == {"readme", "contributors"}
        assert "unknown stage" not in result.output
        assert "mutually exclusive" not in result.output


# ---------------------------------------------------------------------------
# _seed_from_prev_report: collection skipped
# ---------------------------------------------------------------------------


class TestSeedCollectionSkipped:
    def setup_method(self):
        self.commit_data: dict = {}
        self.quality_data: dict = {}
        self.connections_data: dict = {}
        self.readme_classes: dict = {}
        self.users: dict = {}
        self.topic_clusters: dict = {}
        self.repo_data: dict = {}

    def _seed(self, stages):
        _seed_from_prev_report(
            _SAMPLE_PREV_REPORT,
            stages,
            self.commit_data,
            self.quality_data,
            self.connections_data,
            self.readme_classes,
            self.users,
            self.topic_clusters,
            self.repo_data,
        )

    def test_commit_data_seeded(self):
        self._seed({"readme"})
        assert self.commit_data["repo-a"]["total_commits"] == 42
        assert self.commit_data["repo-a"]["commit_frequency_30d"] == 5

    def test_quality_data_seeded(self):
        self._seed({"readme"})
        assert self.quality_data["repo-a"]["has_license"] is True

    def test_connections_data_seeded(self):
        self._seed({"readme"})
        assert self.connections_data["repo-a"]["fork_of"] is None
        assert self.connections_data["repo-a"]["forks"] == []

    def test_collection_data_not_seeded_when_collection_in_stages(self):
        self._seed({"collection", "readme"})
        assert "repo-a" not in self.commit_data
        assert "repo-a" not in self.quality_data
        assert "repo-a" not in self.connections_data

    def test_setdefault_does_not_overwrite_existing(self):
        self.commit_data["repo-a"] = {"total_commits": 99}
        self._seed({"readme"})
        assert self.commit_data["repo-a"]["total_commits"] == 99


# ---------------------------------------------------------------------------
# _seed_from_prev_report: readme skipped
# ---------------------------------------------------------------------------


class TestSeedReadmeSkipped:
    def _seed(self, stages):
        commit_data: dict = {}
        quality_data: dict = {}
        connections_data: dict = {}
        readme_classes: dict = {}
        users: dict = {}
        topic_clusters: dict = {}
        repo_data: dict = {}
        _seed_from_prev_report(
            _SAMPLE_PREV_REPORT,
            stages,
            commit_data,
            quality_data,
            connections_data,
            readme_classes,
            users,
            topic_clusters,
            repo_data,
        )
        return readme_classes

    def test_readme_classes_seeded(self):
        rc = self._seed({"collection"})
        assert rc["repo-a"]["category"] == "CLI Tool"
        assert rc["repo-a"]["confidence"] == "high"

    def test_readme_not_seeded_when_readme_in_stages(self):
        rc = self._seed({"readme"})
        assert "repo-a" not in rc


# ---------------------------------------------------------------------------
# _seed_from_prev_report: contributors skipped
# ---------------------------------------------------------------------------


class TestSeedContributorsSkipped:
    def _seed(self, stages):
        commit_data: dict = {}
        quality_data: dict = {}
        connections_data: dict = {}
        readme_classes: dict = {}
        users: dict = {}
        topic_clusters: dict = {}
        repo_data: dict = {}
        _seed_from_prev_report(
            _SAMPLE_PREV_REPORT,
            stages,
            commit_data,
            quality_data,
            connections_data,
            readme_classes,
            users,
            topic_clusters,
            repo_data,
        )
        return users

    def test_users_seeded(self):
        u = self._seed({"collection"})
        assert "alice" in u
        assert u["alice"]["name"] == "Alice"

    def test_users_not_seeded_when_contributors_in_stages(self):
        u = self._seed({"contributors"})
        assert "alice" not in u


# ---------------------------------------------------------------------------
# _seed_from_prev_report: topics skipped
# ---------------------------------------------------------------------------


class TestSeedTopicsSkipped:
    def _seed(self, stages):
        commit_data: dict = {}
        quality_data: dict = {}
        connections_data: dict = {}
        readme_classes: dict = {}
        users: dict = {}
        topic_clusters: dict = {}
        repo_data: dict = {}
        _seed_from_prev_report(
            _SAMPLE_PREV_REPORT,
            stages,
            commit_data,
            quality_data,
            connections_data,
            readme_classes,
            users,
            topic_clusters,
            repo_data,
        )
        return topic_clusters, repo_data

    def test_topic_clusters_seeded(self):
        tc, _ = self._seed({"collection"})
        assert "cli" in tc
        assert "repo-a" in tc["cli"]

    def test_repo_data_topics_seeded(self):
        _, rd = self._seed({"collection"})
        assert rd["repo-a"]["topics"] == ["cli", "python"]

    def test_topics_not_seeded_when_topics_in_stages(self):
        tc, rd = self._seed({"topics"})
        assert "cli" not in tc
        assert "repo-a" not in rd


# ---------------------------------------------------------------------------
# _seed_from_prev_report: no prev_report crash guard (call-site logic)
# ---------------------------------------------------------------------------


class TestSeedNoPrevReport:
    def test_empty_prev_report_no_crash(self):
        commit_data: dict = {}
        quality_data: dict = {}
        connections_data: dict = {}
        readme_classes: dict = {}
        users: dict = {}
        topic_clusters: dict = {}
        repo_data: dict = {}
        # Empty dict — all .get() calls return None/{}
        _seed_from_prev_report(
            {},
            {"readme"},
            commit_data,
            quality_data,
            connections_data,
            readme_classes,
            users,
            topic_clusters,
            repo_data,
        )
        assert commit_data == {}
        assert readme_classes == {}


# ---------------------------------------------------------------------------
# _ALL_STAGES constant
# ---------------------------------------------------------------------------


def test_all_stages_contains_expected_values():
    assert _ALL_STAGES == {"topics", "collection", "readme", "contributors"}
