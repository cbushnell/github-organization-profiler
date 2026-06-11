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
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, default=str))
    tmp.rename(p)


def evict_null_readme_classes(org: str) -> int:
    """Delete cached readme_class entries where category is None.
    Returns the number of files removed."""
    count = 0
    org_dir = _BASE / org
    if not org_dir.exists():
        return 0
    for p in org_dir.glob("*/readme_class.json"):
        try:
            data = json.loads(p.read_text())
            if data.get("category") is None:
                p.unlink()
                count += 1
        except Exception:
            pass
    return count
