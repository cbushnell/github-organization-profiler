from __future__ import annotations

import time
from typing import Any

import httpx
from github import Github, GithubException
from github.Organization import Organization


def get_github(token: str) -> Github:
    return Github(token)


def get_org(g: Github, name: str) -> Organization:
    return g.get_organization(name)


def graphql(token: str, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    headers = {"Authorization": f"bearer {token}", "Content-Type": "application/json"}
    payload: dict[str, Any] = {"query": query}
    if variables:
        payload["variables"] = variables

    resp = httpx.post("https://api.github.com/graphql", json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(f"GraphQL errors: {data['errors']}")
    return data["data"]


def rate_limit_sleep(g: Github, on_sleep=None) -> None:
    """Sleep until the core rate limit resets if remaining calls are low.

    on_sleep: optional callable(wait_seconds) invoked before sleeping,
              e.g. to save a checkpoint before a long pause.
    """
    rl = g.get_rate_limit()
    if rl.resources.core.remaining < 50:
        reset = rl.resources.core.reset
        now = time.time()
        wait = (reset.timestamp() - now) + 5
        if wait > 0:
            if on_sleep:
                on_sleep(wait)
            time.sleep(wait)


def safe_sleep() -> None:
    time.sleep(0.1)
