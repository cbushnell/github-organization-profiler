from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from github import GithubException

from gh_org_profile import cache
from gh_org_profile.client import safe_sleep


def collect(repo, org: str, max_age: int) -> dict[str, Any]:
    cached = cache.get(org, repo.name, "commits", max_age)
    if cached:
        return cached

    now = datetime.now(timezone.utc)
    since_30d = now - timedelta(days=30)
    since_90d = now - timedelta(days=90)
    since_6m = now - timedelta(days=180)

    last_commit_at: str | None = None
    commits_6m: list = []
    try:
        commits_6m = list(repo.get_commits(since=since_6m))
        if commits_6m:
            dt = commits_6m[0].commit.author.date
            last_commit_at = dt.replace(tzinfo=timezone.utc).isoformat() if dt else None
    except GithubException:
        pass

    commits_90 = [c for c in commits_6m if c.commit.author.date.replace(tzinfo=timezone.utc) >= since_90d]
    commits_30 = [c for c in commits_6m if c.commit.author.date.replace(tzinfo=timezone.utc) >= since_30d]

    data: dict[str, Any] = {
        "total_commits": len(commits_6m),
        "last_commit_at": last_commit_at,
        "commit_frequency_30d": len(commits_30),
        "commit_frequency_90d": len(commits_90),
    }
    cache.put(org, repo.name, "commits", data)
    safe_sleep()
    return data
