from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


_BASE = Path.home() / ".cache" / "gh-org-profile"


def _path(org: str, repo: str, collector: str) -> Path:
    return _BASE / org / repo / f"{collector}.json"


def get(org: str, repo: str, collector: str, max_age_hours: int) -> Any | None:
    p = _path(org, repo, collector)
    if not p.exists():
        return None
    if max_age_hours == 0:
        return None
    age_hours = (time.time() - p.stat().st_mtime) / 3600
    if age_hours > max_age_hours:
        return None
    return json.loads(p.read_text())


def put(org: str, repo: str, collector: str, data: Any) -> None:
    p = _path(org, repo, collector)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, default=str))
