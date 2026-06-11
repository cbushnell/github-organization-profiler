from __future__ import annotations

import json

from github_organization_profiler.reports.render import render


class TestRenderOutput:
    def test_creates_json_file(self, sample_report, tmp_path):
        json_path, _ = render(sample_report, tmp_path, "test-org", [])
        assert json_path.exists()
        assert json_path.name == "test-org_report.json"

    def test_creates_markdown_file(self, sample_report, tmp_path):
        _, md_path = render(sample_report, tmp_path, "test-org", [])
        assert md_path.exists()
        assert md_path.name == "test-org_report.md"

    def test_json_is_valid_and_has_expected_keys(self, sample_report, tmp_path):
        json_path, _ = render(sample_report, tmp_path, "test-org", [])
        data = json.loads(json_path.read_text())
        assert data["org"] == "test-org"
        assert "generated_at" in data
        assert "repos" in data

    def test_json_contains_all_repos(self, sample_report, tmp_path):
        json_path, _ = render(sample_report, tmp_path, "test-org", [])
        data = json.loads(json_path.read_text())
        assert set(data["repos"].keys()) == {"repo-alpha", "repo-beta", "repo-old"}


class TestMarkdownContent:
    def test_contains_org_name(self, sample_report, tmp_path):
        _, md_path = render(sample_report, tmp_path, "test-org", [])
        content = md_path.read_text()
        assert "test-org" in content

    def test_summary_section_present(self, sample_report, tmp_path):
        _, md_path = render(sample_report, tmp_path, "test-org", [])
        content = md_path.read_text()
        assert "## Summary" in content

    def test_active_count_in_summary(self, sample_report, tmp_path):
        _, md_path = render(sample_report, tmp_path, "test-org", [])
        content = md_path.read_text()
        assert "2" in content  # 2 active repos

    def test_dormant_count_in_summary(self, sample_report, tmp_path):
        _, md_path = render(sample_report, tmp_path, "test-org", [])
        content = md_path.read_text()
        assert "1" in content  # 1 dormant repo

    def test_active_repos_section_present(self, sample_report, tmp_path):
        _, md_path = render(sample_report, tmp_path, "test-org", [])
        content = md_path.read_text()
        assert "## Active Repositories" in content

    def test_dormant_repos_section_present(self, sample_report, tmp_path):
        _, md_path = render(sample_report, tmp_path, "test-org", [])
        content = md_path.read_text()
        assert "## Dormant Repositories" in content

    def test_repo_names_appear_in_markdown(self, sample_report, tmp_path):
        _, md_path = render(sample_report, tmp_path, "test-org", [])
        content = md_path.read_text()
        assert "repo-alpha" in content
        assert "repo-old" in content

    def test_output_files_listed(self, sample_report, tmp_path):
        _, md_path = render(sample_report, tmp_path, "test-org", ["test-org_report.json"])
        content = md_path.read_text()
        assert "test-org_report.json" in content

    def test_topic_clusters_section_present(self, sample_report, tmp_path):
        _, md_path = render(sample_report, tmp_path, "test-org", [])
        content = md_path.read_text()
        assert "## Topic Clusters" in content

    def test_internal_deps_section_present(self, sample_report, tmp_path):
        _, md_path = render(sample_report, tmp_path, "test-org", [])
        content = md_path.read_text()
        assert "## Internal Dependencies" in content
