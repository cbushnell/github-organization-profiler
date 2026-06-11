from __future__ import annotations

import json
import os
from typing import Any

import anthropic

from github_organization_profiler import cache

_SYSTEM = """You are classifying GitHub repository README files.
Respond ONLY with valid JSON matching this schema:
{"category": string, "summary": string, "confidence": "high"|"medium"|"low"}

Categories (pick the single best fit):
- API / Data Service
- CLI Tool
- Python Library / SDK
- Infrastructure / IaC
- Frontend / UI
- Design System
- Documentation / Reference
- Data Pipeline / ETL
- ML / AI
- Configuration / Shared Tooling
- Example / Demo
- Archive / Deprecated
- Other
"""

_NULL_CLASS: dict[str, Any] = {"category": None, "summary": None, "confidence": "n/a"}


def _parse_json(text: str) -> dict[str, Any]:
    """Parse JSON from model output, stripping markdown code fences if present."""
    text = text.strip()
    if text.startswith("```"):
        # Strip opening fence (```json or ```) and closing fence
        lines = text.splitlines()
        lines = lines[1:]  # drop opening fence line
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)


def _classify_one(
    client: anthropic.Anthropic, repo_name: str, readme: str
) -> dict[str, Any] | None:
    """Call the LLM. Returns parsed dict on success, None on any failure."""
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            system=_SYSTEM,
            messages=[
                {"role": "user", "content": f"Repository: {repo_name}\n\nREADME:\n{readme[:8000]}"}
            ],
        )
        text = next((b.text for b in response.content if b.type == "text"), "")
        return _parse_json(text)
    except Exception:
        return None


def make_client() -> anthropic.Anthropic | None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    return anthropic.Anthropic(api_key=api_key) if api_key else None


def classify_one_cached(
    client: anthropic.Anthropic, repo_name: str, readme: str, org: str, max_age: int
) -> dict[str, Any]:
    """Classify a single repo's README with caching. Returns the classification dict."""
    cached = cache.get(org, repo_name, "readme_class", max_age)
    if cached:
        return cached
    if not readme.strip():
        result = _NULL_CLASS
        cache.put(org, repo_name, "readme_class", result)
        return result
    result = _classify_one(client, repo_name, readme)
    if result is None:
        # LLM call failed — return null but do NOT cache so the next run retries
        return _NULL_CLASS
    cache.put(org, repo_name, "readme_class", result)
    return result


def classify_active(
    active_repos: list, repo_data: dict, org: str, max_age: int, no_llm: bool
) -> dict[str, dict]:
    if no_llm:
        return {r.name: _NULL_CLASS for r in active_repos}

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {r.name: _NULL_CLASS for r in active_repos}

    client = anthropic.Anthropic(api_key=api_key)
    results: dict[str, dict] = {}

    for repo in active_repos:
        cached = cache.get(org, repo.name, "readme_class", max_age)
        if cached:
            results[repo.name] = cached
            continue

        readme = (repo_data.get(repo.name) or {}).get("readme") or ""
        if not readme.strip():
            results[repo.name] = _NULL_CLASS
            cache.put(org, repo.name, "readme_class", _NULL_CLASS)
            continue

        result = _classify_one(client, repo.name, readme)
        if result is None:
            # LLM call failed — don't cache so the next run retries
            results[repo.name] = _NULL_CLASS
            continue
        cache.put(org, repo.name, "readme_class", result)
        results[repo.name] = result

    return results


def carry_forward_dormant(dormant_repos: list, org: str) -> dict[str, dict]:
    results: dict[str, dict] = {}
    for repo in dormant_repos:
        cached = cache.get(org, repo.name, "readme_class", max_age_hours=99999)
        results[repo.name] = cached if cached else _NULL_CLASS
    return results
