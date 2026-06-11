from __future__ import annotations

from typing import Any

from github import GithubException

from gh_org_profile import cache
from gh_org_profile.client import graphql, safe_sleep

# Single GraphQL query replaces 6-8 sequential REST file-existence checks.
# GraphQL returns null for missing paths — no exception, no extra round-trip.
_QUALITY_QUERY = """
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    licenseInfo { spdxId }
    license1:      object(expression: "HEAD:LICENSE")                   { __typename }
    license2:      object(expression: "HEAD:LICENSE.md")                { __typename }
    license3:      object(expression: "HEAD:LICENSE.txt")               { __typename }
    contributing1: object(expression: "HEAD:CONTRIBUTING.md")           { __typename }
    contributing2: object(expression: "HEAD:CONTRIBUTING")              { __typename }
    contributing3: object(expression: "HEAD:.github/CONTRIBUTING.md")   { __typename }
    codeowners1:   object(expression: "HEAD:CODEOWNERS")                { __typename }
    codeowners2:   object(expression: "HEAD:.github/CODEOWNERS")        { __typename }
    security1:     object(expression: "HEAD:SECURITY.md")               { __typename }
    security2:     object(expression: "HEAD:.github/SECURITY.md")       { __typename }
    dependabot1:   object(expression: "HEAD:.github/dependabot.yml")    { __typename }
    dependabot2:   object(expression: "HEAD:.github/dependabot.yaml")   { __typename }
  }
}
"""


def collect(repo, org: str, max_age: int, token: str) -> dict[str, Any]:
    cached = cache.get(org, repo.name, "quality", max_age)
    if cached:
        return cached

    has_license = False
    license_spdx: str | None = None
    has_contributing = False
    has_codeowners = False
    has_security_md = False
    has_dependabot = False

    try:
        gql_result = graphql(token, _QUALITY_QUERY, {"owner": org, "name": repo.name})
        r = gql_result.get("repository") or {}
        li = r.get("licenseInfo")
        license_spdx = li.get("spdxId") if li else None
        has_license = bool(li) or any(r.get(k) for k in ("license1", "license2", "license3"))
        has_contributing = any(r.get(k) for k in ("contributing1", "contributing2", "contributing3"))
        has_codeowners = any(r.get(k) for k in ("codeowners1", "codeowners2"))
        has_security_md = any(r.get(k) for k in ("security1", "security2"))
        has_dependabot = any(r.get(k) for k in ("dependabot1", "dependabot2"))
    except Exception:
        pass

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
