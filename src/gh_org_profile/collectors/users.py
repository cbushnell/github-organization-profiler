from __future__ import annotations

from typing import Any

from github import Github, GithubException

from gh_org_profile import cache
from gh_org_profile.client import safe_sleep


def collect_repo_contributors(repo, users: dict, org: str, max_age: int) -> None:
    """Fetch contributors for one repo and update the shared users dict in-place."""
    cached = cache.get(org, repo.name, "contributors", max_age)
    if cached:
        contributors = cached
    else:
        try:
            contributors = [
                {"login": c.login, "contributions": c.contributions}
                for c in repo.get_contributors()
            ]
        except GithubException:
            contributors = []
        cache.put(org, repo.name, "contributors", contributors)
        safe_sleep()

    for contrib in contributors:
        login = contrib["login"]
        if login not in users:
            users[login] = {
                "name": None,
                "company": None,
                "bio": None,
                "email": None,
                "org_repos_contributed": {},
            }
        users[login]["org_repos_contributed"][repo.name] = {
            "commits": contrib["contributions"],
            "first_commit": None,
            "last_commit": None,
        }


def fetch_user_profile(login: str, users: dict, g: Github, org: str, max_age: int) -> None:
    """Fetch and merge profile data for a single user. Updates users[login] in-place."""
    profile_cached = cache.get(org, login, "user_profile", max_age)
    if profile_cached:
        users[login].update(profile_cached)
        return
    try:
        u = g.get_user(login)
        profile = {"name": u.name, "company": u.company, "bio": u.bio, "email": u.email}
    except GithubException:
        profile = {"name": None, "company": None, "bio": None, "email": None}
    cache.put(org, login, "user_profile", profile)
    users[login].update(profile)
    safe_sleep()


def collect(active_repos: list, g: Github, org: str, max_age: int) -> dict[str, Any]:
    """Collect all contributor data for active repos. Convenience wrapper used by tests."""
    users: dict[str, Any] = {}
    for repo in active_repos:
        collect_repo_contributors(repo, users, org, max_age)
    for login in list(users):
        fetch_user_profile(login, users, g, org, max_age)
    return users
