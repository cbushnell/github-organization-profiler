from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

import httpx
from github import GithubException

from gh_org_profile import cache
from gh_org_profile.client import graphql, safe_sleep

_TOPICS_QUERY = """
query OrgTopics($org: String!, $cursor: String) {
  organization(login: $org) {
    repositories(first: 100, after: $cursor, privacy: PUBLIC) {
      pageInfo { hasNextPage endCursor }
      nodes {
        name
        repositoryTopics(first: 20) {
          nodes { topic { name } }
        }
      }
    }
  }
}
"""


def fetch_all_topics(token: str, org: str, on_page: object = None) -> dict[str, list[str]]:
    repo_topics: dict[str, list[str]] = {}
    cursor = None
    while True:
        data = graphql(token, _TOPICS_QUERY, {"org": org, "cursor": cursor})
        repos_page = data["organization"]["repositories"]
        for node in repos_page["nodes"]:
            name = node["name"]
            topics = [t["topic"]["name"] for t in node["repositoryTopics"]["nodes"]]
            repo_topics[name] = topics
        if on_page:
            on_page(len(repo_topics))
        if not repos_page["pageInfo"]["hasNextPage"]:
            break
        cursor = repos_page["pageInfo"]["endCursor"]
    return repo_topics


def build_topic_clusters(repo_topics: dict[str, list[str]]) -> dict[str, list[str]]:
    clusters: dict[str, list[str]] = defaultdict(list)
    for repo_name, topics in repo_topics.items():
        for t in topics:
            clusters[t].append(repo_name)
    return dict(clusters)


def _fetch_sbom(token: str, org: str, repo_name: str) -> list[str]:
    url = f"https://api.github.com/repos/{org}/{repo_name}/dependency-graph/sbom"
    resp = httpx.get(
        url,
        headers={"Authorization": f"bearer {token}", "Accept": "application/vnd.github+json"},
        timeout=30,
    )
    if resp.status_code != 200:
        return []
    sbom = resp.json()
    packages = sbom.get("sbom", {}).get("packages", [])
    pattern = re.compile(rf"github\.com/{re.escape(org)}/([^@\s]+)")
    deps = []
    for pkg in packages:
        name = pkg.get("name", "")
        m = pattern.search(name)
        if m:
            deps.append(m.group(1))
    return list(set(deps))


def _fetch_workflow_refs(repo, org: str) -> list[str]:
    refs = []
    try:
        contents = repo.get_contents(".github/workflows")
        if not isinstance(contents, list):
            contents = [contents]
        for f in contents:
            if not f.name.endswith((".yml", ".yaml")):
                continue
            try:
                text = f.decoded_content.decode("utf-8", errors="replace")
                for line in text.splitlines():
                    m = re.search(rf"uses:\s+({re.escape(org)}/[^\s@]+)", line)
                    if m:
                        refs.append(m.group(1))
            except Exception:
                pass
    except GithubException:
        pass
    return list(set(refs))


def collect_active(repo, token: str, org: str, max_age: int) -> dict[str, Any]:
    cached = cache.get(org, repo.name, "connections_active", max_age)
    if cached:
        return cached

    internal_package_deps = _fetch_sbom(token, org, repo.name)
    safe_sleep()

    reusable_workflow_refs = _fetch_workflow_refs(repo, org)
    safe_sleep()

    forks: list[str] = []
    if repo.forks_count > 0:
        try:
            forks = [f.full_name for f in repo.get_forks()]
        except GithubException:
            pass
        safe_sleep()

    fork_of: str | None = repo.parent.full_name if repo.fork and repo.parent else None

    data: dict[str, Any] = {
        "fork_of": fork_of,
        "forks": forks,
        "internal_package_deps": internal_package_deps,
        "reusable_workflow_refs": reusable_workflow_refs,
    }
    cache.put(org, repo.name, "connections_active", data)
    return data


def collect_dormant(repo, org: str) -> dict[str, Any]:
    cached = cache.get(org, repo.name, "connections_active", max_age_hours=99999)
    if cached:
        fork_of = cached.get("fork_of")
        forks = cached.get("forks", [])
        internal_package_deps = cached.get("internal_package_deps", [])
        reusable_workflow_refs = cached.get("reusable_workflow_refs", [])
    else:
        fork_of = repo.parent.full_name if repo.fork and repo.parent else None
        forks = []
        internal_package_deps = []
        reusable_workflow_refs = []

    return {
        "fork_of": fork_of,
        "forks": forks,
        "internal_package_deps": internal_package_deps,
        "reusable_workflow_refs": reusable_workflow_refs,
    }
