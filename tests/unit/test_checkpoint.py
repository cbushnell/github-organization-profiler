from __future__ import annotations

import json

from gh_org_profile.checkpoint import delete, is_complete, load, path, save


class TestPath:
    def test_returns_correct_filename(self, tmp_path):
        p = path(tmp_path, "myorg")
        assert p == tmp_path / "myorg_checkpoint.json"

    def test_different_orgs_produce_different_paths(self, tmp_path):
        assert path(tmp_path, "org-a") != path(tmp_path, "org-b")


class TestLoad:
    def test_returns_none_when_file_missing(self, tmp_path):
        assert load(tmp_path, "nonexistent") is None

    def test_returns_dict_when_file_exists(self, tmp_path):
        p = path(tmp_path, "myorg")
        p.write_text(json.dumps({"org": "myorg", "last_stage": "collection"}))
        result = load(tmp_path, "myorg")
        assert result == {"org": "myorg", "last_stage": "collection"}

    def test_returns_none_on_corrupt_file(self, tmp_path):
        p = path(tmp_path, "myorg")
        p.write_text("not valid json{{")
        assert load(tmp_path, "myorg") is None


class TestSave:
    def test_creates_checkpoint_file(self, tmp_path):
        save(tmp_path, "myorg", "collection", commit_data={"repo-a": {}})
        assert path(tmp_path, "myorg").exists()

    def test_sets_last_stage(self, tmp_path):
        save(tmp_path, "myorg", "collection")
        result = load(tmp_path, "myorg")
        assert result["last_stage"] == "collection"

    def test_stores_extra_data(self, tmp_path):
        save(tmp_path, "myorg", "collection", commit_data={"repo-a": {"total_commits": 5}})
        result = load(tmp_path, "myorg")
        assert result["commit_data"] == {"repo-a": {"total_commits": 5}}

    def test_merges_with_existing_checkpoint(self, tmp_path):
        save(tmp_path, "myorg", "topics", topic_clusters={"python": ["repo-a"]})
        save(
            tmp_path, "myorg", "collection", commit_data={"repo-a": {}}, quality_data={"repo-a": {}}
        )
        result = load(tmp_path, "myorg")
        # Both keys present after second save
        assert "topic_clusters" in result
        assert "commit_data" in result
        assert result["last_stage"] == "collection"

    def test_later_save_advances_last_stage(self, tmp_path):
        save(tmp_path, "myorg", "topics")
        save(tmp_path, "myorg", "collection")
        assert load(tmp_path, "myorg")["last_stage"] == "collection"

    def test_atomic_write_does_not_leave_tmp_file(self, tmp_path):
        save(tmp_path, "myorg", "collection")
        tmp_file = path(tmp_path, "myorg").with_suffix(".tmp")
        assert not tmp_file.exists()

    def test_save_does_not_overwrite_existing_key_with_none(self, tmp_path):
        save(tmp_path, "myorg", "topics", topic_clusters={"python": ["repo-a"]})
        # Second save omits topic_clusters — existing value should be preserved
        save(tmp_path, "myorg", "collection", commit_data={"repo-a": {}})
        result = load(tmp_path, "myorg")
        assert result["topic_clusters"] == {"python": ["repo-a"]}


class TestDelete:
    def test_removes_file(self, tmp_path):
        save(tmp_path, "myorg", "collection")
        assert path(tmp_path, "myorg").exists()
        delete(tmp_path, "myorg")
        assert not path(tmp_path, "myorg").exists()

    def test_noop_when_file_missing(self, tmp_path):
        # Should not raise
        delete(tmp_path, "myorg")


class TestIsComplete:
    def test_returns_false_when_no_checkpoint(self):
        assert is_complete(None, "collection") is False

    def test_returns_false_when_last_stage_before_query(self, tmp_path):
        ckpt = {"last_stage": "repo_metadata"}
        assert is_complete(ckpt, "collection") is False

    def test_returns_true_when_last_stage_equals_query(self):
        ckpt = {"last_stage": "collection"}
        assert is_complete(ckpt, "collection") is True

    def test_returns_true_when_last_stage_after_query(self):
        ckpt = {"last_stage": "readme"}
        assert is_complete(ckpt, "collection") is True

    def test_returns_false_for_unknown_last_stage(self):
        ckpt = {"last_stage": "none"}
        assert is_complete(ckpt, "collection") is False

    def test_returns_false_for_unknown_query_stage(self):
        ckpt = {"last_stage": "collection"}
        assert is_complete(ckpt, "nonexistent_stage") is False

    def test_full_stage_ordering(self):
        stages = ["repo_metadata", "topics", "collection", "readme", "contributors"]
        for i, completed in enumerate(stages):
            ckpt = {"last_stage": completed}
            for j, query in enumerate(stages):
                expected = j <= i
                assert is_complete(ckpt, query) is expected, (
                    f"is_complete(last={completed!r}, query={query!r}) expected {expected}"
                )

    def test_contributors_complete_implies_all_complete(self):
        ckpt = {"last_stage": "contributors"}
        for stage in ["repo_metadata", "topics", "collection", "readme", "contributors"]:
            assert is_complete(ckpt, stage) is True

    def test_repo_metadata_complete_implies_only_itself_complete(self):
        ckpt = {"last_stage": "repo_metadata"}
        assert is_complete(ckpt, "repo_metadata") is True
        for stage in ["topics", "collection", "readme", "contributors"]:
            assert is_complete(ckpt, stage) is False


class TestSaveLoadRoundTrip:
    def test_full_round_trip(self, tmp_path):
        commit_data = {"repo-a": {"total_commits": 42}}
        quality_data = {"repo-a": {"has_license": True}}
        save(tmp_path, "myorg", "collection", commit_data=commit_data, quality_data=quality_data)
        result = load(tmp_path, "myorg")
        assert result["last_stage"] == "collection"
        assert result["commit_data"] == commit_data
        assert result["quality_data"] == quality_data
        assert result["org"] == "myorg"

    def test_resume_skips_completed_stages(self, tmp_path):
        save(tmp_path, "myorg", "collection", commit_data={"a": {}}, quality_data={"a": {}})
        ckpt = load(tmp_path, "myorg")
        assert is_complete(ckpt, "repo_metadata") is True
        assert is_complete(ckpt, "topics") is True
        assert is_complete(ckpt, "collection") is True
        assert is_complete(ckpt, "readme") is False
        assert is_complete(ckpt, "contributors") is False
