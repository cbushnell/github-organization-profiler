from __future__ import annotations

from typing import Any

from github import GithubException

from gh_org_profile import cache
from gh_org_profile.client import safe_sleep


def _try_get_contents(repo, path: str) -> bool:
    try:
        repo.get_contents(path)
        return True
    except GithubException:
        return False


def _has_file(repo, *paths: str) -> bool:
    return any(_try_get_contents(repo, p) for p in paths)


def collect(repo, org: str, max_age: int) -> dict[str, Any]:
    cached = cache.get(org, repo.name, "quality", max_age)
    if cached:
        return cached

    has_license = _has_file(repo, "LICENSE", "LICENSE.md", "LICENSE.txt")
    license_spdx: str | None = None
    try:
        lic = repo.get_license()
        license_spdx = lic.license.spdx_id if lic and lic.license else None
    except GithubException:
        pass

    has_contributing = _has_file(
        repo,
        "CONTRIBUTING.md",
        "CONTRIBUTING",
        ".github/CONTRIBUTING.md",
    )
    has_codeowners = _has_file(repo, "CODEOWNERS", ".github/CODEOWNERS")
    has_security_md = _has_file(repo, "SECURITY.md", ".github/SECURITY.md")
    has_dependabot = _has_file(
        repo,
        ".github/dependabot.yml",
        ".github/dependabot.yaml",
    )

    action_workflows: list[str] = []
    has_actions = False
    try:
        workflows = list(repo.get_workflows())
        action_workflows = [w.name for w in workflows]
        has_actions = len(action_workflows) > 0
    except GithubException:
        pass

    data: dict[str, Any] = {
        "has_license": has_license,
        "license_spdx": license_spdx,
        "has_contributing": has_contributing,
        "has_codeowners": has_codeowners,
        "has_security_md": has_security_md,
        "has_dependabot": has_dependabot,
        "has_actions": has_actions,
        "action_workflows": action_workflows,
        "issues_enabled": repo.has_issues,
    }
    cache.put(org, repo.name, "quality", data)
    safe_sleep()
    return data
