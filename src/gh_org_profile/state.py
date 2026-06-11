from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path


@dataclass
class RunState:
    org: str
    run_at: str
    repo_last_activity: dict[str, str | None] = field(default_factory=dict)


def load_state(output_dir: Path, org: str) -> RunState | None:
    p = output_dir / f"{org}_state.json"
    if not p.exists():
        return None
    return RunState(**json.loads(p.read_text()))


def save_state(output_dir: Path, org: str, repos: list) -> None:
    state = RunState(
        org=org,
        run_at=datetime.now(UTC).isoformat(),
        repo_last_activity={
            r.name: r.pushed_at.isoformat() if r.pushed_at else None for r in repos
        },
    )
    p = output_dir / f"{org}_state.json"
    p.write_text(json.dumps(state.__dict__, indent=2))


def classify_repos(
    repos: list, prev_state: RunState | None, dormancy_days: int = 90
) -> tuple[list, list]:
    if prev_state is None:
        cutoff = datetime.now(UTC) - timedelta(days=dormancy_days)
        active = [r for r in repos if r.pushed_at and r.pushed_at.replace(tzinfo=UTC) > cutoff]
        dormant = [r for r in repos if not r.pushed_at or r.pushed_at.replace(tzinfo=UTC) <= cutoff]
        return active, dormant

    active, dormant = [], []
    for r in repos:
        prev_ts = prev_state.repo_last_activity.get(r.name)
        current_ts = r.pushed_at.isoformat() if r.pushed_at else None
        if current_ts == prev_ts:
            dormant.append(r)
        else:
            active.append(r)
    return active, dormant
