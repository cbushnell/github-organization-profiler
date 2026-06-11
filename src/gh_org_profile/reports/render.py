from __future__ import annotations

import json
from pathlib import Path

from jinja2 import BaseLoader, Environment

_MARKDOWN_TEMPLATE = """\
# {{ report.org }} — GitHub Org Profile

**Generated:** {{ report.generated_at }}
{% if report.prev_run_at %}**Previous run:** {{ report.prev_run_at }}{% endif %}

## Table of Contents

- [Summary](#summary)
{% if report.delta %}- [Changes Since Last Run](#changes-since-last-run)
{% endif %}- [Active Repositories](#active-repositories-{{ report.active_repo_count }})
{% if unclassified_repos %}- [Repos Needing README Attention](#repos-needing-readme-attention)
{% endif %}- [Dormant Repositories](#dormant-repositories-{{ report.dormant_repo_count }})
- [Topic Clusters](#topic-clusters)
- [Internal Dependencies](#internal-dependencies)

---

## Summary

| | |
|---|---|
| Total repositories | {{ report.active_repo_count + report.dormant_repo_count }} |
| Active repositories | {{ report.active_repo_count }} |
| Dormant repositories | {{ report.dormant_repo_count }} |
| Contributors | {{ report.users | length }} |

{% if top_contributors %}
**Top contributors:**
{% for login, count in top_contributors %}
- [@{{ login }}](https://github.com/{{ login }}) — {{ count }} commits
{%- endfor %}
{% endif %}

## Output Files

{% for f in output_files %}
- `{{ f }}`
{%- endfor %}

---

{% if report.delta %}
{% set d = report.delta %}
## Changes Since Last Run

{% if d.repos_added %}**New repositories ({{ d.repos_added | length }}):** {{ d.repos_added | join(", ") }}
{% endif %}
{% if d.repos_removed %}**Removed repositories ({{ d.repos_removed | length }}):** {{ d.repos_removed | join(", ") }}
{% endif %}
{% if d.active_to_dormant %}**Went dormant ({{ d.active_to_dormant | length }}):** {{ d.active_to_dormant | join(", ") }}
{% endif %}
{% if d.dormant_to_active %}**Became active ({{ d.dormant_to_active | length }}):** {{ d.dormant_to_active | join(", ") }}
{% endif %}
{% if d.quality_changes %}
**Quality score changes:**

| Repo | Before | After | Change |
|---|---|---|---|
{% for name, chg in d.quality_changes.items() | sort %}| **{{ name }}** | {{ chg["from"] }}/6 | {{ chg["to"] }}/6 | {{ "+" if chg["to"] > chg["from"] else "" }}{{ chg["to"] - chg["from"] }} |
{% endfor %}
{% endif %}
{% if d.new_contributors %}**New contributors ({{ d.new_contributors | length }}):** {{ d.new_contributors | join(", ") }}
{% endif %}

---
{% endif %}

## Active Repositories ({{ report.active_repo_count }})

> Sorted by quality score ascending — lowest quality first.

| Repo | Category | Quality | Commits 30d | Commits 90d | Last Commit |
|---|---|---|---|---|---|
{% for name, r in active_repos %}| **{{ name }}** | {{ r.readme_class.category or "—" }} | {{ r.quality.quality_score }}/6 | {{ r.activity.commit_frequency_30d }} | {{ r.activity.commit_frequency_90d }} | {{ r.activity.last_commit_at or "—" }} |
{% endfor %}

{% if unclassified_repos %}
### Repos Needing README Attention

The following active repos have no detected category or a low-confidence classification:

{% for name, r in unclassified_repos %}
- **{{ name }}**{% if r.readme_class.confidence == "low" %} *(low confidence: {{ r.readme_class.category }})*{% endif %}
{%- endfor %}

{% endif %}

---

## Dormant Repositories ({{ report.dormant_repo_count }})

| Repo | Dormant Since | Category | Quality |
|---|---|---|---|
{% for name, r in dormant_repos %}| **{{ name }}** | {{ r.dormant_since or "—" }} | {{ r.readme_class.category or "—" }} | {{ r.quality.quality_score }}/6 |
{% endfor %}

---

## Topic Clusters

{% for topic, repos in report.connections_summary.topic_clusters.items() | sort %}
- **{{ topic }}**: {{ repos | join(", ") }}
{%- endfor %}

---

## Internal Dependencies

{% if report.connections_summary.internal_dep_graph %}
| Dependency | Consumers |
|---|---|
{% for dep, consumers in report.connections_summary.internal_dep_graph.items() | sort %}| `{{ dep }}` | {{ consumers | join(", ") }} |
{% endfor %}
{% else %}
No internal package dependencies detected.
{% endif %}
"""


def render(report: dict, output_dir: Path, org: str, output_files: list[str]) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / f"{org}_report.json"
    json_path.write_text(json.dumps(report, indent=2, default=str))

    env = Environment(loader=BaseLoader(), keep_trailing_newline=True)
    tmpl = env.from_string(_MARKDOWN_TEMPLATE)

    # Sort active repos by quality score ascending (worst first) so low-quality repos are visible
    active_repos = sorted(
        [(n, r) for n, r in report["repos"].items() if not r["dormant"]],
        key=lambda x: (x[1]["quality"]["quality_score"], x[0]),
    )
    dormant_repos = sorted(
        [(n, r) for n, r in report["repos"].items() if r["dormant"]],
        key=lambda x: x[0],
    )

    unclassified_repos = [
        (n, r)
        for n, r in active_repos
        if not r["readme_class"].get("category") or r["readme_class"].get("confidence") == "low"
    ]

    top_contributors = sorted(
        [
            (login, sum(v.get("commits", 0) for v in data["org_repos_contributed"].values()))
            for login, data in report["users"].items()
        ],
        key=lambda x: -x[1],
    )[:5]

    md_text = tmpl.render(
        report=report,
        active_repos=active_repos,
        dormant_repos=dormant_repos,
        unclassified_repos=unclassified_repos,
        top_contributors=top_contributors,
        output_files=output_files,
    )

    md_path = output_dir / f"{org}_report.md"
    md_path.write_text(md_text)

    return json_path, md_path
