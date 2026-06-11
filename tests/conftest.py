from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

DEFAULT_ORG = "github"
_FIXTURES = Path(__file__).parent / "fixtures"


def pytest_addoption(parser):
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration tests that hit the real GitHub API",
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-integration"):
        skip = pytest.mark.skip(reason="Pass --run-integration to run live API tests")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip)


@pytest.fixture
def github_token():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        pytest.skip("GITHUB_TOKEN not set")
    return token


@pytest.fixture
def anthropic_api_key():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        pytest.skip("ANTHROPIC_API_KEY not set")
    return key


@pytest.fixture
def sample_report():
    return json.loads((_FIXTURES / "sample_report.json").read_text())


def _make_repo(
    name: str,
    pushed_at: datetime | None = None,
    open_issues: int = 0,
    forks: int = 0,
    archived: bool = False,
    is_fork: bool = False,
):
    repo = MagicMock()
    repo.name = name
    repo.pushed_at = pushed_at
    repo.open_issues_count = open_issues
    repo.forks_count = forks
    repo.archived = archived
    repo.fork = is_fork
    repo.has_issues = True
    repo.description = None
    repo.homepage = None
    return repo


@pytest.fixture
def mock_repo():
    return _make_repo("test-repo", pushed_at=datetime(2026, 5, 1, 0, 0, 0))


@pytest.fixture
def make_repo():
    return _make_repo
