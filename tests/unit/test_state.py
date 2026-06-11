from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from gh_org_profile.state import RunState, classify_repos, load_state, save_state


def _repo(name: str, pushed_at: datetime | None):
    r = MagicMock()
    r.name = name
    r.pushed_at = pushed_at
    return r


class TestClassifyReposFirstRun:
    def test_all_recent_repos_are_active(self):
        now = datetime.now(timezone.utc)
        repos = [
            _repo("a", pushed_at=(now - timedelta(days=10)).replace(tzinfo=None)),
            _repo("b", pushed_at=(now - timedelta(days=30)).replace(tzinfo=None)),
        ]
        active, dormant = classify_repos(repos, prev_state=None, dormancy_days=90)
        assert len(active) == 2
        assert len(dormant) == 0

    def test_old_repos_are_dormant(self):
        now = datetime.now(timezone.utc)
        repos = [
            _repo("old", pushed_at=(now - timedelta(days=120)).replace(tzinfo=None)),
        ]
        active, dormant = classify_repos(repos, prev_state=None, dormancy_days=90)
        assert len(active) == 0
        assert len(dormant) == 1

    def test_null_pushed_at_is_dormant(self):
        repos = [_repo("no-push", pushed_at=None)]
        active, dormant = classify_repos(repos, prev_state=None, dormancy_days=90)
        assert dormant[0].name == "no-push"

    def test_boundary_exactly_at_cutoff_is_dormant(self):
        now = datetime.now(timezone.utc)
        pushed = (now - timedelta(days=90)).replace(tzinfo=None)
        repos = [_repo("boundary", pushed_at=pushed)]
        active, dormant = classify_repos(repos, prev_state=None, dormancy_days=90)
        assert len(dormant) == 1

    def test_mixed_repos(self):
        now = datetime.now(timezone.utc)
        repos = [
            _repo("recent", pushed_at=(now - timedelta(days=5)).replace(tzinfo=None)),
            _repo("stale", pushed_at=(now - timedelta(days=200)).replace(tzinfo=None)),
        ]
        active, dormant = classify_repos(repos, prev_state=None, dormancy_days=90)
        assert [r.name for r in active] == ["recent"]
        assert [r.name for r in dormant] == ["stale"]


class TestClassifyReposWithPriorState:
    def test_unchanged_pushed_at_is_dormant(self):
        ts = datetime(2026, 1, 1, 0, 0, 0)
        repo = _repo("x", pushed_at=ts)
        prior = RunState(org="test-org", run_at="2026-01-01", repo_last_activity={"x": ts.isoformat()})
        active, dormant = classify_repos([repo], prev_state=prior)
        assert dormant[0].name == "x"

    def test_changed_pushed_at_is_active(self):
        old_ts = datetime(2026, 1, 1)
        new_ts = datetime(2026, 2, 1)
        repo = _repo("x", pushed_at=new_ts)
        prior = RunState(org="test-org", run_at="2026-01-01", repo_last_activity={"x": old_ts.isoformat()})
        active, dormant = classify_repos([repo], prev_state=prior)
        assert active[0].name == "x"

    def test_new_repo_not_in_prior_state_is_active(self):
        repo = _repo("new-repo", pushed_at=datetime(2026, 5, 1))
        prior = RunState(org="test-org", run_at="2026-01-01", repo_last_activity={})
        active, dormant = classify_repos([repo], prev_state=prior)
        assert active[0].name == "new-repo"


class TestLoadSaveState:
    def test_load_returns_none_when_file_missing(self, tmp_path):
        result = load_state(tmp_path, "nonexistent-org")
        assert result is None

    def test_save_then_load_round_trip(self, tmp_path):
        repos = [
            _repo("repo-a", pushed_at=datetime(2026, 1, 1)),
            _repo("repo-b", pushed_at=None),
        ]
        save_state(tmp_path, "my-org", repos)
        loaded = load_state(tmp_path, "my-org")
        assert loaded is not None
        assert loaded.org == "my-org"
        assert "repo-a" in loaded.repo_last_activity
        assert loaded.repo_last_activity["repo-b"] is None

    def test_state_file_is_valid_json(self, tmp_path):
        repos = [_repo("r", pushed_at=datetime(2026, 3, 1))]
        save_state(tmp_path, "org", repos)
        raw = json.loads((tmp_path / "org_state.json").read_text())
        assert raw["org"] == "org"
        assert "run_at" in raw
        assert "repo_last_activity" in raw
