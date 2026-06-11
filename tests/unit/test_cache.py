from __future__ import annotations

import json
import time

import pytest

import gh_org_profile.cache as cache_mod


@pytest.fixture(autouse=True)
def redirect_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_mod, "_BASE", tmp_path)


class TestCachePut:
    def test_creates_file(self, tmp_path):
        cache_mod.put("org", "repo", "collector", {"key": "value"})
        p = tmp_path / "org" / "repo" / "collector.json"
        assert p.exists()

    def test_no_tmp_file_left_behind(self, tmp_path):
        cache_mod.put("org", "repo", "collector", {"key": "value"})
        tmp = tmp_path / "org" / "repo" / "collector.tmp"
        assert not tmp.exists()

    def test_creates_parent_directories(self, tmp_path):
        cache_mod.put("deep-org", "deep-repo", "test", [1, 2, 3])
        p = tmp_path / "deep-org" / "deep-repo" / "test.json"
        assert p.exists()

    def test_serializes_data_as_json(self, tmp_path):
        data = {"a": 1, "b": [True, None]}
        cache_mod.put("org", "repo", "col", data)
        raw = json.loads((tmp_path / "org" / "repo" / "col.json").read_text())
        assert raw == data


class TestCacheGet:
    def test_returns_data_for_warm_cache(self, tmp_path):
        data = {"x": 42}
        cache_mod.put("org", "repo", "col", data)
        result = cache_mod.get("org", "repo", "col", max_age_hours=24)
        assert result == data

    def test_returns_none_when_file_missing(self):
        result = cache_mod.get("no-org", "no-repo", "no-col", max_age_hours=24)
        assert result is None

    def test_max_age_zero_always_returns_none(self, tmp_path):
        cache_mod.put("org", "repo", "col", {"data": True})
        result = cache_mod.get("org", "repo", "col", max_age_hours=0)
        assert result is None

    def test_expired_cache_returns_none(self, tmp_path, monkeypatch):
        cache_mod.put("org", "repo", "col", {"val": 1})
        # Simulate file being written 2 hours ago
        p = tmp_path / "org" / "repo" / "col.json"
        old_mtime = time.time() - 7200
        import os
        os.utime(p, (old_mtime, old_mtime))
        result = cache_mod.get("org", "repo", "col", max_age_hours=1)
        assert result is None

    def test_non_expired_cache_returns_data(self, tmp_path):
        data = {"fresh": True}
        cache_mod.put("org", "repo", "col", data)
        result = cache_mod.get("org", "repo", "col", max_age_hours=24)
        assert result == data

    def test_different_collectors_are_isolated(self, tmp_path):
        cache_mod.put("org", "repo", "col-a", {"a": 1})
        cache_mod.put("org", "repo", "col-b", {"b": 2})
        assert cache_mod.get("org", "repo", "col-a", 24) == {"a": 1}
        assert cache_mod.get("org", "repo", "col-b", 24) == {"b": 2}
