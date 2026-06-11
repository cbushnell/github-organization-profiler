from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def _repo_activity(report: dict) -> list[dict]:
    rows = []
    for name, r in report["repos"].items():
        act = r.get("activity") or {}
        rows.append({
            "repo": name,
            "pushed_at": act.get("pushed_at", ""),
            "last_commit_at": act.get("last_commit_at", ""),
            "commits_30d": act.get("commit_frequency_30d", 0),
            "commits_90d": act.get("commit_frequency_90d", 0),
            "open_issues_count": act.get("open_issues_count", 0),
            "forks_count": act.get("forks_count", 0),
            "is_archived": act.get("is_archived", False),
            "is_fork": act.get("is_fork", False),
            "dormant": r.get("dormant", False),
            "dormant_since": r.get("dormant_since", ""),
        })
    return sorted(rows, key=lambda x: x["repo"])


def _repo_quality(report: dict) -> list[dict]:
    rows = []
    for name, r in report["repos"].items():
        q = r.get("quality") or {}
        rows.append({
            "repo": name,
            "has_license": q.get("has_license", False),
            "license_spdx": q.get("license_spdx", ""),
            "has_contributing": q.get("has_contributing", False),
            "has_codeowners": q.get("has_codeowners", False),
            "has_security_md": q.get("has_security_md", False),
            "has_dependabot": q.get("has_dependabot", False),
            "has_actions": q.get("has_actions", False),
            "workflow_count": len(q.get("action_workflows") or []),
            "issues_enabled": q.get("issues_enabled", False),
            "quality_score": q.get("quality_score", 0),
            "dormant": r.get("dormant", False),
        })
    return sorted(rows, key=lambda x: x["repo"])


def _repo_classification(report: dict) -> list[dict]:
    rows = []
    for name, r in report["repos"].items():
        rc = r.get("readme_class") or {}
        rows.append({
            "repo": name,
            "category": rc.get("category") or "unclassified",
            "summary": rc.get("summary", ""),
            "confidence": rc.get("confidence", "n/a"),
            "dormant": r.get("dormant", False),
        })
    return sorted(rows, key=lambda x: x["repo"])


def _contributor_summary(report: dict) -> list[dict]:
    rows = []
    for login, u in report.get("users", {}).items():
        contrib = u.get("org_repos_contributed") or {}
        if not contrib:
            continue
        total_commits = sum(v.get("commits", 0) for v in contrib.values())
        first_commits = [v["first_commit"] for v in contrib.values() if v.get("first_commit")]
        last_commits = [v["last_commit"] for v in contrib.values() if v.get("last_commit")]
        most_active = max(contrib, key=lambda r: contrib[r].get("commits", 0)) if contrib else ""
        rows.append({
            "login": login,
            "name": u.get("name", ""),
            "company": u.get("company", ""),
            "bio": u.get("bio", ""),
            "total_org_commits": total_commits,
            "org_repos_contributed": len(contrib),
            "most_active_repo": most_active,
            "first_seen": min(first_commits) if first_commits else "",
            "last_seen": max(last_commits) if last_commits else "",
        })
    return sorted(rows, key=lambda x: (-x["total_org_commits"], x["login"]))


def _repo_contributor_matrix(report: dict) -> list[dict]:
    rows = []
    repo_dormant = {n: r.get("dormant", False) for n, r in report["repos"].items()}
    for login, u in report.get("users", {}).items():
        for repo_name, rec in (u.get("org_repos_contributed") or {}).items():
            rows.append({
                "repo": repo_name,
                "login": login,
                "commits": rec.get("commits", 0),
                "first_commit": rec.get("first_commit", ""),
                "last_commit": rec.get("last_commit", ""),
                "dormant": repo_dormant.get(repo_name, False),
            })
    return sorted(rows, key=lambda x: (x["repo"], x["login"]))


def _topic_clusters(report: dict) -> list[dict]:
    rows = []
    repo_dormant = {n: r.get("dormant", False) for n, r in report["repos"].items()}
    clusters = report.get("connections_summary", {}).get("topic_clusters") or {}
    for topic, repos in clusters.items():
        for repo_name in repos:
            rows.append({
                "topic": topic,
                "repo": repo_name,
                "dormant": repo_dormant.get(repo_name, False),
            })
    return sorted(rows, key=lambda x: (x["topic"], x["repo"]))


def _internal_deps(report: dict) -> list[dict]:
    rows = []
    repo_dormant = {n: r.get("dormant", False) for n, r in report["repos"].items()}
    for name, r in report["repos"].items():
        for dep in (r.get("connections") or {}).get("internal_package_deps") or []:
            rows.append({
                "consumer_repo": name,
                "dependency_repo": dep,
                "dormant": repo_dormant.get(name, False),
            })
    return sorted(rows, key=lambda x: (x["consumer_repo"], x["dependency_repo"]))


def export_all(report: dict, output_dir: Path, org: str) -> list[Path]:
    writers = [
        (_repo_activity, "repo_activity"),
        (_repo_quality, "repo_quality"),
        (_repo_classification, "repo_classification"),
        (_contributor_summary, "contributor_summary"),
        (_repo_contributor_matrix, "repo_contributor_matrix"),
        (_topic_clusters, "topic_clusters"),
        (_internal_deps, "internal_deps"),
    ]
    paths = []
    for fn, name in writers:
        p = output_dir / f"{org}_{name}.csv"
        rows = fn(report)
        if rows:
            with p.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
                w.writeheader()
                w.writerows(rows)
            paths.append(p)
    return paths
