from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

_QUALITY_BOOL_FIELDS = [
    "has_license",
    "has_contributing",
    "has_codeowners",
    "has_security_md",
    "has_dependabot",
    "has_actions",
]

_NULL_QUALITY = {
    "has_license": False,
    "license_spdx": None,
    "has_contributing": False,
    "has_codeowners": False,
    "has_security_md": False,
    "has_dependabot": False,
    "has_actions": False,
    "action_workflows": [],
    "issues_enabled": False,
    "quality_score": 0,
}

_NULL_ACTIVITY = {
    "total_commits": 0,
    "last_commit_at": None,
    "commit_frequency_30d": 0,
    "commit_frequency_90d": 0,
    "open_issues_count": 0,
    "forks_count": 0,
    "is_archived": False,
    "is_fork": False,
}

_NULL_README = {"category": None, "summary": None, "confidence": "n/a"}

_NULL_CONNECTIONS = {
    "topics": [],
    "fork_of": None,
    "forks": [],
    "internal_package_deps": [],
    "reusable_workflow_refs": [],
}


def _build_internal_dep_graph(repos: dict[str, dict]) -> dict[str, list[str]]:
    graph: dict[str, list[str]] = defaultdict(list)
    for repo_name, repo in repos.items():
        for dep in repo.get("connections", {}).get("internal_package_deps", []):
            graph[dep].append(repo_name)
    return dict(graph)


def build_report(
    org: str,
    run_at: str,
    prev_report: dict[str, Any] | None,
    active_repos: list,
    dormant_repos: list,
    repo_data: dict[str, dict],
    commit_data: dict[str, dict],
    quality_data: dict[str, dict],
    connections_data: dict[str, dict],
    readme_classes: dict[str, dict],
    users: dict[str, Any],
    topic_clusters: dict[str, list[str]],
) -> dict[str, Any]:
    repos: dict[str, Any] = {}

    # Active repos — full fresh data
    for repo in active_repos:
        name = repo.name
        meta = repo_data.get(name) or {}
        commits = commit_data.get(name) or {}
        quality = dict(quality_data.get(name) or _NULL_QUALITY)
        conns = connections_data.get(name) or {}
        readme = readme_classes.get(name) or _NULL_README

        quality["quality_score"] = sum(
            bool(quality.get(f)) for f in _QUALITY_BOOL_FIELDS
        )

        repos[name] = {
            "dormant": False,
            "dormant_since": None,
            "activity": {
                "total_commits": commits.get("total_commits", 0),
                "last_commit_at": commits.get("last_commit_at"),
                "commit_frequency_30d": commits.get("commit_frequency_30d", 0),
                "commit_frequency_90d": commits.get("commit_frequency_90d", 0),
                "open_issues_count": meta.get("open_issues_count", 0),
                "forks_count": meta.get("forks_count", 0),
                "is_archived": meta.get("is_archived", False),
                "is_fork": meta.get("is_fork", False),
            },
            "readme_class": readme,
            "quality": quality,
            "connections": {
                "topics": meta.get("topics", []),
                "fork_of": conns.get("fork_of"),
                "forks": conns.get("forks", []),
                "internal_package_deps": conns.get("internal_package_deps", []),
                "reusable_workflow_refs": conns.get("reusable_workflow_refs", []),
            },
        }

    # Dormant repos — carry forward from prev_report; overwrite 4 live activity fields
    today = datetime.now(timezone.utc).date().isoformat()

    for repo in dormant_repos:
        name = repo.name
        meta = repo_data.get(name) or {}

        if prev_report and name in prev_report.get("repos", {}):
            prior = prev_report["repos"][name]
            record: dict[str, Any] = {
                "dormant": True,
                "dormant_since": prior.get("dormant_since") or today,
                "activity": dict(prior.get("activity") or _NULL_ACTIVITY),
                "readme_class": prior.get("readme_class") or _NULL_README,
                "quality": prior.get("quality") or dict(_NULL_QUALITY),
                "connections": prior.get("connections") or dict(_NULL_CONNECTIONS),
            }
            # Overwrite only the four cheaply-refreshed fields
            record["activity"]["open_issues_count"] = meta.get("open_issues_count", record["activity"]["open_issues_count"])
            record["activity"]["forks_count"] = meta.get("forks_count", record["activity"]["forks_count"])
            record["activity"]["is_archived"] = meta.get("is_archived", record["activity"]["is_archived"])
            record["activity"]["pushed_at"] = meta.get("pushed_at", record["activity"].get("pushed_at"))
        else:
            # First time seen as dormant (no prior record)
            readme = readme_classes.get(name) or _NULL_README
            record = {
                "dormant": True,
                "dormant_since": today,
                "activity": {
                    "total_commits": 0,
                    "last_commit_at": None,
                    "commit_frequency_30d": 0,
                    "commit_frequency_90d": 0,
                    "open_issues_count": meta.get("open_issues_count", 0),
                    "forks_count": meta.get("forks_count", 0),
                    "is_archived": meta.get("is_archived", False),
                    "is_fork": meta.get("is_fork", False),
                },
                "readme_class": readme,
                "quality": dict(_NULL_QUALITY),
                "connections": {
                    "topics": meta.get("topics", []),
                    "fork_of": meta.get("fork_of"),
                    "forks": [],
                    "internal_package_deps": [],
                    "reusable_workflow_refs": [],
                },
            }

        repos[name] = record

    internal_dep_graph = _build_internal_dep_graph(repos)

    delta = None
    if prev_report:
        prev_repos = prev_report.get("repos", {})
        curr_names = set(repos.keys())
        prev_names = set(prev_repos.keys())

        quality_changes = {}
        for name in curr_names & prev_names:
            prev_q = (prev_repos[name].get("quality") or {}).get("quality_score", 0)
            curr_q = repos[name]["quality"]["quality_score"]
            if curr_q != prev_q:
                quality_changes[name] = {"from": prev_q, "to": curr_q}

        delta = {
            "repos_added": sorted(curr_names - prev_names),
            "repos_removed": sorted(prev_names - curr_names),
            "quality_changes": quality_changes,
            "active_to_dormant": sorted(
                n for n in curr_names & prev_names
                if repos[n]["dormant"] and not prev_repos[n].get("dormant", True)
            ),
            "dormant_to_active": sorted(
                n for n in curr_names & prev_names
                if not repos[n]["dormant"] and prev_repos[n].get("dormant", False)
            ),
            "new_contributors": sorted(
                set(users.keys()) - set((prev_report.get("users") or {}).keys())
            ),
        }

    return {
        "org": org,
        "generated_at": run_at,
        "prev_run_at": (prev_report or {}).get("generated_at"),
        "active_repo_count": len(active_repos),
        "dormant_repo_count": len(dormant_repos),
        "users": users,
        "repos": repos,
        "connections_summary": {
            "topic_clusters": topic_clusters,
            "internal_dep_graph": internal_dep_graph,
        },
        "delta": delta,
    }
