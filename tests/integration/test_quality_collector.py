from __future__ import annotations

import pytest

DEFAULT_ORG = "github"
from gh_org_profile.client import get_github, get_org
from gh_org_profile.collectors.quality import collect

_BOOL_FIELDS = [
    "has_license",
    "has_contributing",
    "has_codeowners",
    "has_security_md",
    "has_dependabot",
    "has_actions",
    "issues_enabled",
]


@pytest.mark.integration
class TestQualityCollector:
    @pytest.fixture
    def hello_world(self, github_token):
        g = get_github(github_token)
        org = get_org(g, DEFAULT_ORG)
        return org.get_repo("linguist")

    def test_returns_all_expected_keys(self, hello_world):
        result = collect(hello_world, DEFAULT_ORG, max_age=0)
        for key in _BOOL_FIELDS + ["license_spdx", "action_workflows"]:
            assert key in result

    def test_boolean_fields_are_bool(self, hello_world):
        result = collect(hello_world, DEFAULT_ORG, max_age=0)
        for field in _BOOL_FIELDS:
            assert isinstance(result[field], bool), f"{field} should be bool"

    def test_hello_world_has_license(self, hello_world):
        result = collect(hello_world, DEFAULT_ORG, max_age=0)
        assert result["has_license"] is True

    def test_action_workflows_is_list(self, hello_world):
        result = collect(hello_world, DEFAULT_ORG, max_age=0)
        assert isinstance(result["action_workflows"], list)

    def test_quality_score_not_in_result(self, hello_world):
        # quality_score is computed by builder.py, not quality.py
        result = collect(hello_world, DEFAULT_ORG, max_age=0)
        assert "quality_score" not in result

    def test_license_spdx_is_string_or_none(self, hello_world):
        result = collect(hello_world, DEFAULT_ORG, max_age=0)
        assert result["license_spdx"] is None or isinstance(result["license_spdx"], str)
