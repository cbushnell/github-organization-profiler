from __future__ import annotations

import csv

import pytest

from gh_org_profile.reports.csv_export import (
    _contributor_summary,
    _internal_deps,
    _repo_activity,
    _repo_classification,
    _repo_contributor_matrix,
    _repo_quality,
    _topic_clusters,
    export_all,
)


@pytest.fixture
def report(sample_report):
    return sample_report


class TestRepoActivity:
    def test_row_count(self, report):
        rows = _repo_activity(report)
        assert len(rows) == 3

    def test_required_columns(self, report):
        row = _repo_activity(report)[0]
        for col in (
            "repo",
            "pushed_at",
            "last_commit_at",
            "commits_30d",
            "commits_90d",
            "open_issues_count",
            "forks_count",
            "is_archived",
            "is_fork",
            "dormant",
            "dormant_since",
        ):
            assert col in row

    def test_dormant_column_correct(self, report):
        rows = {r["repo"]: r for r in _repo_activity(report)}
        assert rows["repo-old"]["dormant"] is True
        assert rows["repo-alpha"]["dormant"] is False

    def test_sorted_by_repo_name(self, report):
        names = [r["repo"] for r in _repo_activity(report)]
        assert names == sorted(names)


class TestRepoQuality:
    def test_row_count(self, report):
        rows = _repo_quality(report)
        assert len(rows) == 3

    def test_required_columns(self, report):
        row = _repo_quality(report)[0]
        for col in (
            "repo",
            "has_license",
            "license_spdx",
            "has_contributing",
            "has_codeowners",
            "has_security_md",
            "has_dependabot",
            "has_actions",
            "workflow_count",
            "issues_enabled",
            "quality_score",
            "dormant",
        ):
            assert col in row

    def test_workflow_count_derived(self, report):
        rows = {r["repo"]: r for r in _repo_quality(report)}
        assert rows["repo-alpha"]["workflow_count"] == 2
        assert rows["repo-beta"]["workflow_count"] == 1
        assert rows["repo-old"]["workflow_count"] == 0

    def test_quality_score_from_json(self, report):
        rows = {r["repo"]: r for r in _repo_quality(report)}
        assert rows["repo-alpha"]["quality_score"] == 4


class TestRepoClassification:
    def test_row_count(self, report):
        rows = _repo_classification(report)
        assert len(rows) == 3

    def test_null_category_becomes_unclassified(self):
        r = {
            "repos": {
                "x": {
                    "dormant": False,
                    "readme_class": {"category": None, "summary": None, "confidence": "n/a"},
                }
            }
        }
        rows = _repo_classification(r)
        assert rows[0]["category"] == "unclassified"

    def test_confidence_present(self, report):
        rows = {r["repo"]: r for r in _repo_classification(report)}
        assert rows["repo-alpha"]["confidence"] == "high"


class TestContributorSummary:
    def test_row_count(self, report):
        rows = _contributor_summary(report)
        assert len(rows) == 2

    def test_total_org_commits_summed(self, report):
        rows = {r["login"]: r for r in _contributor_summary(report)}
        assert rows["alice"]["total_org_commits"] == 52  # 42 + 10
        assert rows["bob"]["total_org_commits"] == 5

    def test_org_repos_contributed_count(self, report):
        rows = {r["login"]: r for r in _contributor_summary(report)}
        assert rows["alice"]["org_repos_contributed"] == 2
        assert rows["bob"]["org_repos_contributed"] == 1

    def test_most_active_repo(self, report):
        rows = {r["login"]: r for r in _contributor_summary(report)}
        assert rows["alice"]["most_active_repo"] == "repo-alpha"

    def test_first_and_last_seen(self, report):
        rows = {r["login"]: r for r in _contributor_summary(report)}
        assert rows["alice"]["first_seen"] == "2024-01-01T00:00:00+00:00"
        assert rows["alice"]["last_seen"] == "2026-05-01T00:00:00+00:00"

    def test_sorted_by_commit_count_desc(self, report):
        rows = _contributor_summary(report)
        commits = [r["total_org_commits"] for r in rows]
        assert commits == sorted(commits, reverse=True)


class TestRepoContributorMatrix:
    def test_one_row_per_repo_contributor_pair(self, report):
        rows = _repo_contributor_matrix(report)
        # alice: repo-alpha + repo-beta; bob: repo-alpha = 3 pairs
        assert len(rows) == 3

    def test_dormant_inherited_from_repo(self, report):
        rows = {(r["repo"], r["login"]): r for r in _repo_contributor_matrix(report)}
        # repo-old has no contributors in sample, all active
        for row in rows.values():
            assert row["dormant"] is False

    def test_required_columns(self, report):
        row = _repo_contributor_matrix(report)[0]
        for col in ("repo", "login", "commits", "first_commit", "last_commit", "dormant"):
            assert col in row


class TestTopicClusters:
    def test_one_row_per_topic_repo_pair(self, report):
        rows = _topic_clusters(report)
        # python: 2, data: 1, api: 1, legacy: 1 = 5
        assert len(rows) == 5

    def test_dormant_inherited(self, report):
        rows = {(r["topic"], r["repo"]): r for r in _topic_clusters(report)}
        assert rows[("legacy", "repo-old")]["dormant"] is True
        assert rows[("python", "repo-alpha")]["dormant"] is False

    def test_required_columns(self, report):
        row = _topic_clusters(report)[0]
        for col in ("topic", "repo", "dormant"):
            assert col in row


class TestInternalDeps:
    def test_one_row_per_dep_pair(self, report):
        rows = _internal_deps(report)
        assert len(rows) == 1
        assert rows[0]["consumer_repo"] == "repo-beta"
        assert rows[0]["dependency_repo"] == "repo-alpha"

    def test_dormant_from_consumer(self, report):
        rows = _internal_deps(report)
        assert rows[0]["dormant"] is False


class TestExportAll:
    def test_writes_seven_files(self, report, tmp_path):
        paths = export_all(report, tmp_path, "test-org")
        assert len(paths) == 7

    def test_files_named_correctly(self, report, tmp_path):
        paths = export_all(report, tmp_path, "test-org")
        names = {p.name for p in paths}
        for stem in (
            "repo_activity",
            "repo_quality",
            "repo_classification",
            "contributor_summary",
            "repo_contributor_matrix",
            "topic_clusters",
            "internal_deps",
        ):
            assert f"test-org_{stem}.csv" in names

    def test_csv_files_are_parseable(self, report, tmp_path):
        export_all(report, tmp_path, "test-org")
        activity_csv = tmp_path / "test-org_repo_activity.csv"
        rows = list(csv.DictReader(activity_csv.open()))
        assert len(rows) == 3
