from __future__ import annotations

import base64
import itertools
from typing import Any

from github import GithubException
from github.Organization import Organization

from github_organization_profiler import cache
from github_organization_profiler.client import safe_sleep


def list_repos(org_obj: Organization, max_repos: int | None = None) -> list:
    """Enumerate all public repos in the org. max_repos caps the result."""
    return list(itertools.islice(org_obj.get_repos(type="public"), max_repos))


def fetch_repo_metadata(repo, org: str, max_age: int) -> dict[str, Any]:
    """Fetch metadata + README for a single repo. Returns the metadata dict."""
    cached = cache.get(org, repo.name, "repos", max_age)
    if cached:
        return cached

    readme_content: str | None = None
    try:
        readme = repo.get_readme()
        readme_content = base64.b64decode(readme.content).decode("utf-8", errors="replace")
    except GithubException:
        pass

    data: dict[str, Any] = {
        "name": repo.name,
        "description": repo.description,
        "homepage": repo.homepage,
        "pushed_at": repo.pushed_at.isoformat() if repo.pushed_at else None,
        "open_issues_count": repo.open_issues_count,
        "forks_count": repo.forks_count,
        "is_archived": repo.archived,
        "is_fork": repo.fork,
        "has_issues": repo.has_issues,
        "readme": readme_content,
    }
    cache.put(org, repo.name, "repos", data)
    safe_sleep()
    return data


def collect_repo_metadata(
    org_obj: Organization, org: str, max_age: int, max_repos: int | None = None
) -> tuple[list, dict[str, dict]]:
    """
    Enumerate all public repos, fetch metadata + README for each.
    Returns (repos_list, repo_data_dict).
    max_repos: optional cap on the number of repos processed (useful for testing).
    """
    repos = list_repos(org_obj, max_repos)
    repo_data = {repo.name: fetch_repo_metadata(repo, org, max_age) for repo in repos}
    return repos, repo_data
