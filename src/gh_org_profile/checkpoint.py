from __future__ import annotations

import json
from pathlib import Path
from typing import Any


# Ordered list of pipeline stages. is_complete() uses this ordering.
_STAGES = [
    "repo_metadata",
    "topics",
    "collection",
    "readme",
    "contributors",
]


def path(output_dir: Path, org: str) -> Path:
    return output_dir / f"{org}_checkpoint.json"


def load(output_dir: Path, org: str) -> dict[str, Any] | None:
    """Return the parsed checkpoint dict, or None if absent or unreadable."""
    p = path(output_dir, org)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def save(output_dir: Path, org: str, last_stage: str, **data: Any) -> None:
    """Merge data into the checkpoint and write atomically via a .tmp rename."""
    p = path(output_dir, org)
    existing: dict[str, Any] = load(output_dir, org) or {"org": org}
    existing["last_stage"] = last_stage
    existing.update(data)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(existing, default=str))
    tmp.rename(p)


def delete(output_dir: Path, org: str) -> None:
    """Remove the checkpoint file. No-op if it does not exist."""
    p = path(output_dir, org)
    if p.exists():
        p.unlink()


def is_complete(ckpt: dict[str, Any] | None, stage: str) -> bool:
    """Return True if stage has already been completed in the checkpoint."""
    if not ckpt:
        return False
    last = ckpt.get("last_stage", "")
    if last not in _STAGES or stage not in _STAGES:
        return False
    return _STAGES.index(last) >= _STAGES.index(stage)
