# Checkpoint & Interrupt Recovery — Execution Plan

## Problem

The pipeline runs as a single long-lived process. If interrupted (keyboard interrupt, rate-limit
exception, crash), three things are lost:

1. **Aggregated in-memory data** — `commit_data`, `quality_data`, `connections_data`,
   `readme_classes`, `users`, `repo_data` are held in memory until the final report write.
   Any interrupt before that step discards all collected data for the current run.

2. **State file not written** — `{org}_state.json` is saved only at the very end.
   A missing state file causes the next run to treat every repo as active, re-doing all
   collection rather than skipping unchanged (dormant) repos.

3. **Rate limits not handled** — `rate_limit_sleep()` exists in `client.py` but is never
   called from the pipeline. `RateLimitExceededException` propagates uncaught and aborts
   the run with no recovery.

**What already works:** each individual collector calls `cache.put()` immediately after a
successful API call, so on resume those per-item results are cache-hits. The checkpoint
system only needs to persist the *aggregated* pipeline data between stages.

---

## Solution Overview

Introduce a pipeline-level **checkpoint file** (`{org}_checkpoint.json`) written to the
output directory after each stage completes. On startup the pipeline detects an existing
checkpoint and resumes from the last completed stage, restoring in-memory state from disk.
A signal/exception handler ensures the checkpoint is flushed on any interrupt.

---

## New File: `src/gh_org_profile/checkpoint.py`

Thin module responsible only for reading and writing the checkpoint file.

```python
# Checkpoint schema
{
  "org":               str,
  "run_at":            str,           # ISO timestamp of the original run
  "last_stage":        str,           # name of last successfully completed stage
  "repo_data":         dict | None,
  "commit_data":       dict | None,
  "quality_data":      dict | None,
  "connections_data":  dict | None,
  "readme_classes":    dict | None,
  "users":             dict | None,
  "topic_clusters":    dict | None,
}
```

**Functions:**

- `path(output_dir, org) -> Path`
  Returns `output_dir / f"{org}_checkpoint.json"`.

- `load(output_dir, org) -> dict | None`
  Returns parsed checkpoint dict if file exists, else `None`.

- `save(output_dir, org, last_stage, **data) -> None`
  Merges `data` into any existing checkpoint (so each stage only needs to pass its own
  new fields), then atomically writes via a `.tmp` rename to avoid partial writes.

- `delete(output_dir, org) -> None`
  Removes checkpoint file on clean completion.

---

## Modified: `src/gh_org_profile/pipeline.py`

### 1. Load checkpoint at startup

```python
ckpt = checkpoint_mod.load(output_dir, org)
if ckpt:
    console.print(f"[yellow]Resuming from checkpoint (last stage: {ckpt['last_stage']})")
```

Each stage checks whether its data is already present in the checkpoint and skips
collection if so, restoring from the checkpoint dict instead:

```python
if ckpt and ckpt.get("commit_data") is not None:
    commit_data = ckpt["commit_data"]
else:
    # ... run the commits collector loop ...
    checkpoint_mod.save(output_dir, org, "commits", commit_data=commit_data)
```

### 2. Stage checkpointing

Write checkpoint after each stage in this order:

| Stage name       | Data saved                                      |
|------------------|-------------------------------------------------|
| `repo_metadata`  | `repo_data`                                     |
| `topics`         | `topic_clusters` (merged into `repo_data`)      |
| `commits`        | `commit_data`                                   |
| `quality`        | `quality_data`                                  |
| `connections`    | `connections_data`                              |
| `readme`         | `readme_classes`                                |
| `contributors`   | `users`                                         |

### 3. Interrupt / exception handler

Wrap the entire pipeline body in a `try/except`:

```python
try:
    # ... all stages ...
    checkpoint_mod.delete(output_dir, org)   # clean run: remove checkpoint
except KeyboardInterrupt:
    _flush_on_interrupt(output_dir, org, repos, locals())
    raise
except Exception:
    _flush_on_interrupt(output_dir, org, repos, locals())
    raise
```

`_flush_on_interrupt` saves:
- The checkpoint with whatever data has been collected so far
- A partial `state.json` (repos seen, so next run can detect dormant repos)
- A console message: `"Interrupted. Checkpoint saved — re-run to resume."`

Does **not** write partial report files (they would be incomplete and misleading).

### 4. `--full-refresh` clears checkpoint

```python
if full_refresh and checkpoint_mod.load(output_dir, org):
    checkpoint_mod.delete(output_dir, org)
    console.print("[yellow]Full refresh: cleared existing checkpoint.")
```

---

## Modified: `src/gh_org_profile/client.py`

### `rate_limit_sleep` accepts a pre-sleep callback

```python
def rate_limit_sleep(g: Github, on_sleep=None) -> None:
    rl = g.get_rate_limit()
    if rl.resources.core.remaining < 50:
        reset = rl.resources.core.reset
        wait = (reset.timestamp() - time.time()) + 5
        if wait > 0:
            if on_sleep:
                on_sleep(wait)
            time.sleep(wait)
```

Pipeline passes a callback that saves the checkpoint before the process sleeps:

```python
def _before_rate_sleep(wait: float) -> None:
    checkpoint_mod.save(output_dir, org, current_stage, **current_data)
    console.print(f"[yellow]Rate limit hit — saving checkpoint, sleeping {wait:.0f}s")

rate_limit_sleep(g, on_sleep=_before_rate_sleep)
```

`rate_limit_sleep` should be called at the top of each per-repo collector loop iteration
in `pipeline.py` (not inside the individual collector modules, so the pipeline controls
the callback).

---

## Modified: `src/gh_org_profile/cli.py`

No new flags needed — `--full-refresh` already signals "ignore prior state". The checkpoint
is auto-detected and auto-resumed by default.

Optionally surface checkpoint status in the help text:

```
If a checkpoint from a previous interrupted run exists, the pipeline resumes
automatically from the last completed stage. Use --full-refresh to discard it.
```

---

## Resume Behavior (full example)

```
$ gh-org-profile --org myorg
Resuming from checkpoint (last stage: commits)
  commit_data: restored (42 repos)
  quality_data: not found — collecting...
[green]Quality (42 active)... ━━━━━━━━━━━━━━━━  12/42
^C
Interrupted. Checkpoint saved to output/myorg_checkpoint.json — re-run to resume.

$ gh-org-profile --org myorg
Resuming from checkpoint (last stage: quality)
  commit_data: restored (42 repos)
  quality_data: restored (42 repos)
  connections_data: not found — collecting...
...
```

---

## Files Changed

| File | Change |
|------|--------|
| `src/gh_org_profile/checkpoint.py` | **New** — checkpoint read/write/delete |
| `src/gh_org_profile/pipeline.py` | Load/save checkpoint per stage; interrupt handler; rate_limit_sleep calls |
| `src/gh_org_profile/client.py` | `rate_limit_sleep` accepts `on_sleep` callback |
| `src/gh_org_profile/cli.py` | Update help text only |

No changes needed to collectors, classifiers, or reports modules.
