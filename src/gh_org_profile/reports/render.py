from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, BaseLoader

_MARKDOWN_TEMPLATE = """\
# {{ report.org }} — GitHub Org Profile

**Generated:** {{ report.generated_at }}
{% if report.prev_run_at %}**Previous run:** {{ report.prev_run_at }}{% endif %}

## Summary

| | |
|---|---|
| Total repositories | {{ report.active_repo_count + report.dormant_repo_count }} |
| Active repositories | {{ report.active_repo_count }} |
| Dormant repositories | {{ report.dormant_repo_count }} |
| Contributors | {{ report.users | length }} |

## Output Files

{% for f in output_files %}
- `{{ f }}`
{%- endfor %}

---

## Repositories

### Active ({{ report.active_repo_count }})

| Repo | Category | Quality | Commits 30d | Commits 90d | Last Commit |
|---|---|---|---|---|---|
{% for name, r in active_repos %}| **{{ name }}** | {{ r.readme_class.category or "—" }} | {{ r.quality.quality_score }}/6 | {{ r.activity.commit_frequency_30d }} | {{ r.activity.commit_frequency_90d }} | {{ r.activity.last_commit_at or "—" }} |
{% endfor %}

### Dormant ({{ report.dormant_repo_count }})

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

    active_repos = sorted(
        [(n, r) for n, r in report["repos"].items() if not r["dormant"]],
        key=lambda x: x[0],
    )
    dormant_repos = sorted(
        [(n, r) for n, r in report["repos"].items() if r["dormant"]],
        key=lambda x: x[0],
    )

    md_text = tmpl.render(
        report=report,
        active_repos=active_repos,
        dormant_repos=dormant_repos,
        output_files=output_files,
    )

    md_path = output_dir / f"{org}_report.md"
    md_path.write_text(md_text)

    return json_path, md_path
