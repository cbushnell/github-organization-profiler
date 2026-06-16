from __future__ import annotations

import re
from typing import Any

from github_organization_profiler import cache

_NULL_CLASS: dict[str, Any] = {"category": None, "summary": None, "confidence": "n/a"}

_HIGH_THRESHOLD = 4
_MEDIUM_THRESHOLD = 2
_TOPIC_WEIGHT = 2

# (category, readme_keywords, topic_keywords) — checked in order; earlier rules win ties.
CATEGORY_RULES: list[tuple[str, list[str], list[str]]] = [
    (
        "Archive / Deprecated",
        [
            "deprecated",
            "archived",
            "no longer maintained",
            "sunset",
            "legacy",
            "unmaintained",
            "end of life",
            "eol",
        ],
        ["deprecated", "archived", "legacy"],
    ),
    (
        "ML / AI",
        [
            "machine learning",
            "neural network",
            "deep learning",
            "pytorch",
            "tensorflow",
            "llm",
            "large language model",
            "fine-tun",
            "embedding",
            "nlp",
            "natural language",
            "scikit-learn",
            "sklearn",
            "onnx",
            "diffusion",
            "computer vision",
            "reinforcement learning",
            "gradient",
            "huggingface",
        ],
        [
            "machine-learning",
            "deep-learning",
            "nlp",
            "pytorch",
            "tensorflow",
            "ai",
            "llm",
            "huggingface",
            "computer-vision",
        ],
    ),
    (
        "Data Pipeline / ETL",
        [
            "etl",
            "extract transform load",
            "data ingestion",
            "kafka",
            "airflow",
            "prefect",
            "dbt",
            "spark",
            "flink",
            "stream processing",
            "batch processing",
            "dagster",
            "luigi",
            "data warehouse",
            "glue job",
            "dataflow",
        ],
        ["etl", "data-pipeline", "airflow", "kafka", "spark", "dbt"],
    ),
    (
        "Infrastructure / IaC",
        [
            "terraform",
            "pulumi",
            "cloudformation",
            "ansible",
            "kubernetes",
            "helm",
            "infrastructure as code",
            "iac",
            "aws cdk",
            "opentofu",
            "chef",
            "puppet",
            "vagrant",
            "docker",
            "container orchestration",
        ],
        ["terraform", "kubernetes", "helm", "infrastructure", "iac", "ansible", "pulumi"],
    ),
    (
        "Design System",
        [
            "design system",
            "component library",
            "storybook",
            "design token",
            "figma",
            "ui kit",
            "icon set",
            "atomic design",
        ],
        ["design-system", "storybook", "component-library", "design-tokens"],
    ),
    (
        "CLI Tool",
        [
            "command-line",
            "command line",
            "cli",
            "argparse",
            "click",
            "typer",
            "cobra",
            "usage:",
            "subcommand",
            "shell script",
            "bash script",
        ],
        ["cli", "command-line", "terminal"],
    ),
    (
        "API / Data Service",
        [
            "rest api",
            "graphql",
            "grpc",
            "openapi",
            "swagger",
            "webhook",
            "microservice",
            "fastapi",
            "django",
            "flask",
            "express",
            "spring boot",
            "api server",
            "endpoint",
            "rate limit",
        ],
        ["api", "rest", "graphql", "microservice", "fastapi", "django", "flask"],
    ),
    (
        "Frontend / UI",
        [
            "react",
            "vue",
            "angular",
            "svelte",
            "next.js",
            "nuxt",
            "frontend",
            "browser",
            "webpack",
            "vite",
            "single page",
            "spa",
            "html",
            "css",
        ],
        ["react", "vue", "angular", "frontend", "nextjs", "typescript", "javascript"],
    ),
    (
        "Python Library / SDK",
        [
            "pip install",
            "pypi",
            "python library",
            "python package",
            "sdk",
            "client library",
            "api client",
            "wheel",
            "setup.py",
            "pyproject.toml",
        ],
        ["python", "library", "sdk", "pypi", "package"],
    ),
    (
        "Configuration / Shared Tooling",
        [
            "shared config",
            "dotfiles",
            "linting",
            "eslint",
            "prettier",
            "ruff",
            "pre-commit",
            "editorconfig",
            "reusable workflow",
            "composite action",
            "monorepo tooling",
        ],
        ["dotfiles", "configuration", "linting", "pre-commit", "shared"],
    ),
    (
        "Example / Demo",
        [
            "example",
            "demo",
            "tutorial",
            "sample",
            "getting started",
            "quickstart",
            "boilerplate",
            "template",
            "starter",
            "cookbook",
            "playground",
        ],
        ["example", "demo", "tutorial", "sample", "template", "starter"],
    ),
    (
        "Documentation / Reference",
        [
            "documentation",
            "docs",
            "reference",
            "wiki",
            "knowledge base",
            "handbook",
            "runbook",
            "spec",
            "rfc",
            "architecture decision",
            "mkdocs",
            "docusaurus",
            "gitbook",
        ],
        ["documentation", "docs", "wiki"],
    ),
]

_VALID_CATEGORIES = {cat for cat, _, _ in CATEGORY_RULES} | {"Other"}


def _normalize(text: str) -> str:
    return re.sub(r"[\s\W]+", " ", text.lower()).strip()


def _count_hits(corpus: str, keywords: list[str]) -> int:
    return sum(1 for kw in keywords if kw in corpus)


def _extract_summary(readme: str, description: str | None) -> str | None:
    lines = readme.splitlines()

    # Drop leading blank lines, ATX headings, and badge lines
    body_lines = []
    past_header = False
    for line in lines:
        stripped = line.strip()
        if not past_header:
            if not stripped:
                continue
            if stripped.startswith("#") or stripped.startswith("[!["):
                continue
            past_header = True
        body_lines.append(line)

    paragraph_lines = []
    for line in body_lines:
        if not line.strip() and paragraph_lines:
            break
        paragraph_lines.append(line)

    paragraph = " ".join(ln.strip() for ln in paragraph_lines).strip()
    paragraph = re.sub(r"\s+", " ", paragraph)

    # Truncate at second sentence boundary within 300 chars
    if len(paragraph) > 300:
        paragraph = paragraph[:300]
    sentence_ends = [m.end() for m in re.finditer(r"\.\s", paragraph)]
    if len(sentence_ends) >= 2:
        paragraph = paragraph[: sentence_ends[1]].rstrip()
    elif len(sentence_ends) == 1:
        paragraph = paragraph[: sentence_ends[0]].rstrip()

    paragraph = paragraph.strip()
    if len(paragraph) >= 20:
        return paragraph

    if description and description.strip():
        return description.strip()

    return None


def classify_one(
    repo_name: str,
    readme: str,
    description: str | None,
    topics: list[str],
) -> dict[str, Any]:
    if not readme.strip() and not (description or "").strip() and not topics:
        return _NULL_CLASS

    corpus = _normalize(f"{repo_name} {description or ''} {readme[:8000]}")
    topic_str = _normalize(" ".join(topics))

    best_category = "Other"
    best_score = 0

    for category, keywords, topic_keywords in CATEGORY_RULES:
        score = (
            _count_hits(corpus, keywords) + _count_hits(topic_str, topic_keywords) * _TOPIC_WEIGHT
        )
        if score > best_score:
            best_score = score
            best_category = category

    if best_score == 0:
        confidence = "low"
    elif best_score >= _HIGH_THRESHOLD:
        confidence = "high"
    elif best_score >= _MEDIUM_THRESHOLD:
        confidence = "medium"
    else:
        confidence = "low"

    summary = _extract_summary(readme, description)
    return {"category": best_category, "summary": summary, "confidence": confidence}


def classify_one_cached(
    repo_name: str,
    readme: str,
    description: str | None,
    topics: list[str],
    org: str,
    max_age: int,
) -> dict[str, Any]:
    cached = cache.get(org, repo_name, "readme_class_local", max_age)
    if cached:
        return cached
    result = classify_one(repo_name, readme, description, topics)
    cache.put(org, repo_name, "readme_class_local", result)
    return result


def carry_forward_dormant(dormant_repos: list, org: str) -> dict[str, dict]:
    results: dict[str, dict] = {}
    for repo in dormant_repos:
        cached = cache.get(org, repo.name, "readme_class_local", max_age_hours=99999)
        results[repo.name] = cached if cached else _NULL_CLASS
    return results
