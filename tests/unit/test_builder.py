from __future__ import annotations

from unittest.mock import MagicMock

from github_organization_profiler.reports.builder import build_report


def _make_repo(name: str):
    r = MagicMock()
    r.name = name
    return r


def _base_call(**overrides):
    defaults = dict(
        org="test-org",
        run_at="2026-06-10T00:00:00+00:00",
        prev_report=None,
        active_repos=[_make_repo("repo-a")],
        dormant_repos=[],
        repo_data={
            "repo-a": {
                "open_issues_count": 4,
                "forks_count": 1,
                "is_archived": False,
                "is_fork": False,
                "pushed_at": "2026-05-01T00:00:00+00:00",
                "topics": ["python"],
            }
        },
        commit_data={
            "repo-a": {
                "total_commits": 50,
                "last_commit_at": "2026-05-01",
                "commit_frequency_30d": 5,
                "commit_frequency_90d": 15,
            }
        },
        quality_data={
            "repo-a": {
                "has_license": True,
                "license_spdx": "MIT",
                "has_contributing": True,
                "has_codeowners": False,
                "has_security_md": False,
                "has_dependabot": True,
                "has_actions": True,
                "action_workflows": ["ci.yml"],
                "issues_enabled": True,
            }
        },
        connections_data={
            "repo-a": {
                "fork_of": None,
                "forks": [],
                "internal_package_deps": [],
                "reusable_workflow_refs": [],
            }
        },
        readme_classes={
            "repo-a": {"category": "CLI Tool", "summary": "A CLI.", "confidence": "high"}
        },
        users={
            "alice": {
                "name": "Alice",
                "company": None,
                "bio": None,
                "email": None,
                "org_repos_contributed": {},
            }
        },
        topic_clusters={"python": ["repo-a"]},
    )
    defaults.update(overrides)
    return defaults


class TestActiveRepoAssembly:
    def test_repo_present_in_output(self):
        report = build_report(**_base_call())
        assert "repo-a" in report["repos"]

    def test_dormant_false_for_active(self):
        report = build_report(**_base_call())
        assert report["repos"]["repo-a"]["dormant"] is False

    def test_dormant_since_null_for_active(self):
        report = build_report(**_base_call())
        assert report["repos"]["repo-a"]["dormant_since"] is None

    def test_activity_fields_populated(self):
        report = build_report(**_base_call())
        act = report["repos"]["repo-a"]["activity"]
        assert act["total_commits"] == 50
        assert act["commit_frequency_30d"] == 5
        assert act["open_issues_count"] == 4
        assert act["is_fork"] is False

    def test_readme_class_populated(self):
        report = build_report(**_base_call())
        assert report["repos"]["repo-a"]["readme_class"]["category"] == "CLI Tool"

    def test_quality_score_computed_correctly(self):
        report = build_report(**_base_call())
        # has_license, has_contributing, has_dependabot, has_actions = True (4)
        # has_codeowners, has_security_md = False (2 missing)
        assert report["repos"]["repo-a"]["quality"]["quality_score"] == 4

    def test_quality_score_zero_when_all_false(self):
        q = {
            k: False
            for k in [
                "has_license",
                "has_contributing",
                "has_codeowners",
                "has_security_md",
                "has_dependabot",
                "has_actions",
            ]
        }
        q.update({"license_spdx": None, "action_workflows": [], "issues_enabled": False})
        report = build_report(**_base_call(quality_data={"repo-a": q}))
        assert report["repos"]["repo-a"]["quality"]["quality_score"] == 0

    def test_quality_score_six_when_all_true(self):
        q = {
            k: True
            for k in [
                "has_license",
                "has_contributing",
                "has_codeowners",
                "has_security_md",
                "has_dependabot",
                "has_actions",
            ]
        }
        q.update({"license_spdx": "MIT", "action_workflows": ["ci.yml"], "issues_enabled": True})
        report = build_report(**_base_call(quality_data={"repo-a": q}))
        assert report["repos"]["repo-a"]["quality"]["quality_score"] == 6

    def test_connections_topics_from_repo_data(self):
        report = build_report(**_base_call())
        assert "python" in report["repos"]["repo-a"]["connections"]["topics"]


class TestDormantRepoCarryForward:
    def _prev_report(self):
        return {
            "generated_at": "2026-05-01T00:00:00+00:00",
            "repos": {
                "repo-d": {
                    "dormant": True,
                    "dormant_since": "2025-11-01",
                    "activity": {
                        "total_commits": 10,
                        "last_commit_at": "2025-10-01",
                        "commit_frequency_30d": 0,
                        "commit_frequency_90d": 0,
                        "open_issues_count": 2,
                        "forks_count": 1,
                        "is_archived": False,
                        "is_fork": False,
                    },
                    "readme_class": {
                        "category": "Other",
                        "summary": "Old stuff.",
                        "confidence": "low",
                    },
                    "quality": {
                        "has_license": False,
                        "has_contributing": False,
                        "has_codeowners": False,
                        "has_security_md": False,
                        "has_dependabot": False,
                        "has_actions": False,
                        "license_spdx": None,
                        "action_workflows": [],
                        "issues_enabled": False,
                        "quality_score": 0,
                    },
                    "connections": {
                        "topics": ["legacy"],
                        "fork_of": None,
                        "forks": [],
                        "internal_package_deps": [],
                        "reusable_workflow_refs": [],
                    },
                }
            },
        }

    def _dormant_call(self):
        return _base_call(
            active_repos=[],
            dormant_repos=[_make_repo("repo-d")],
            repo_data={
                "repo-d": {
                    "open_issues_count": 5,
                    "forks_count": 2,
                    "is_archived": True,
                    "is_fork": False,
                    "pushed_at": "2025-10-01T00:00:00+00:00",
                    "topics": ["legacy"],
                }
            },
            commit_data={},
            quality_data={},
            connections_data={
                "repo-d": {
                    "fork_of": None,
                    "forks": [],
                    "internal_package_deps": [],
                    "reusable_workflow_refs": [],
                }
            },
            readme_classes={"repo-d": {"category": None, "summary": None, "confidence": "n/a"}},
            prev_report=self._prev_report(),
        )

    def test_dormant_true_for_dormant_repo(self):
        report = build_report(**self._dormant_call())
        assert report["repos"]["repo-d"]["dormant"] is True

    def test_dormant_since_preserved_from_prev_report(self):
        report = build_report(**self._dormant_call())
        assert report["repos"]["repo-d"]["dormant_since"] == "2025-11-01"

    def test_live_fields_updated(self):
        report = build_report(**self._dormant_call())
        act = report["repos"]["repo-d"]["activity"]
        assert act["open_issues_count"] == 5
        assert act["forks_count"] == 2
        assert act["is_archived"] is True

    def test_non_live_fields_carried_forward(self):
        report = build_report(**self._dormant_call())
        act = report["repos"]["repo-d"]["activity"]
        # total_commits comes from prev_report, not fresh collection
        assert act["total_commits"] == 10
        assert act["last_commit_at"] == "2025-10-01"

    def test_readme_class_carried_forward_from_prev(self):
        report = build_report(**self._dormant_call())
        assert report["repos"]["repo-d"]["readme_class"]["category"] == "Other"

    def test_dormant_since_set_to_today_when_first_time(self):
        call = self._dormant_call()
        call["prev_report"] = None
        report = build_report(**call)
        from datetime import date

        assert report["repos"]["repo-d"]["dormant_since"] == date.today().isoformat()


class TestInternalDepGraph:
    def test_dep_graph_built_from_connections(self):
        call = _base_call(
            active_repos=[_make_repo("consumer"), _make_repo("lib")],
            repo_data={
                "consumer": {
                    "open_issues_count": 0,
                    "forks_count": 0,
                    "is_archived": False,
                    "is_fork": False,
                    "pushed_at": None,
                    "topics": [],
                },
                "lib": {
                    "open_issues_count": 0,
                    "forks_count": 0,
                    "is_archived": False,
                    "is_fork": False,
                    "pushed_at": None,
                    "topics": [],
                },
            },
            commit_data={
                "consumer": {
                    "total_commits": 1,
                    "last_commit_at": None,
                    "commit_frequency_30d": 0,
                    "commit_frequency_90d": 0,
                },
                "lib": {
                    "total_commits": 1,
                    "last_commit_at": None,
                    "commit_frequency_30d": 0,
                    "commit_frequency_90d": 0,
                },
            },
            quality_data={},
            connections_data={
                "consumer": {
                    "fork_of": None,
                    "forks": [],
                    "internal_package_deps": ["lib"],
                    "reusable_workflow_refs": [],
                },
                "lib": {
                    "fork_of": None,
                    "forks": [],
                    "internal_package_deps": [],
                    "reusable_workflow_refs": [],
                },
            },
            readme_classes={
                "consumer": {"category": None, "summary": None, "confidence": "n/a"},
                "lib": {"category": None, "summary": None, "confidence": "n/a"},
            },
            topic_clusters={},
        )
        report = build_report(**call)
        assert report["connections_summary"]["internal_dep_graph"]["lib"] == ["consumer"]


class TestReportMetadata:
    def test_org_set(self):
        report = build_report(**_base_call())
        assert report["org"] == "test-org"

    def test_active_dormant_counts(self):
        report = build_report(**_base_call())
        assert report["active_repo_count"] == 1
        assert report["dormant_repo_count"] == 0

    def test_prev_run_at_from_prev_report(self):
        prev = {"generated_at": "2026-01-01T00:00:00+00:00", "repos": {}}
        report = build_report(**_base_call(prev_report=prev))
        assert report["prev_run_at"] == "2026-01-01T00:00:00+00:00"

    def test_prev_run_at_none_on_first_run(self):
        report = build_report(**_base_call())
        assert report["prev_run_at"] is None
