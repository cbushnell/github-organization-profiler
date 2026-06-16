# GitHub Org Profiler — Architecture Reference

## Overview

`github-organization-profiler` is a CLI tool that profiles GitHub organizations by collecting structured data about repositories and generating multi-format reports (JSON, Markdown, CSV). The tool is designed to be **incremental**: it skips detailed collection for dormant repos on subsequent runs, only updating lightweight metrics.

## Project Structure

```
src/github_organization_profiler/
├── __init__.py
├── cli.py              # Typer CLI entrypoint
├── pipeline.py         # Main orchestration
├── client.py           # GitHub API wrapper (PyGithub + GraphQL)
├── state.py            # Run state & dormancy detection
├── cache.py            # Local ~./cache filesystem cache
├── checkpoint.py       # Pipeline checkpoint: interrupt recovery & resume
├── collectors/         # Data collection modules
│   ├── repos.py       # Repository metadata, README, topics, license
│   ├── commits.py     # Commit frequency & recency
│   ├── users.py       # Contributor profiles
│   ├── quality.py     # Quality signals (CI, issues, CODEOWNERS, etc.)
│   └── connections.py # Topics, fork graph, dependencies, workflows
├── classifiers/       # README classification
│   └── local.py       # Keyword/rule-based README classifier (no API required)
└── reports/           # Report generation
    ├── builder.py     # Assemble structured report data
    ├── render.py      # Output JSON & Markdown
    └── csv_export.py  # Export CSV tables
```

## Key Components

### CLI (`cli.py`)

**Entrypoint:** `github-organization-profiler --org <name> [options]`

**Options:**
- `--org` (required): GitHub organization name
- `--token`: GitHub PAT; fallback to `GITHUB_TOKEN` env var
- `--full-refresh`: Treat all repos as active (ignore dormancy state)
- `--dormancy-days`: Days without push to mark repo dormant (default: 90)
- `--max-age`: Cache max age in hours; 0 = always re-fetch (default: 24)
- `--output`: Output directory for reports (default: `./<org>`)
- `--workers`: Number of parallel worker threads for repo collection (default: 4)
- `--max-repos`: Limit number of repos processed (useful for testing)
- `--stages`: Comma-separated list of stages to run selectively (e.g. `readme,contributors`). `repo_metadata` always runs. Skipped stages are seeded from the previous report. Mutually exclusive with `--full-refresh`.

### Pipeline (`pipeline.py`)

Main orchestration that:
1. Loads previous run state from `{org}_state.json`
2. Connects to GitHub
3. Enumerates repos via `list_repos()` (shows count before fetching metadata)
4. Fetches per-repo metadata + READMEs with a live `X/N` progress bar
5. Classifies repos as active (changed) or dormant (unchanged since last run); prints newly-dormant repos
6. For **active repos**: runs commits, quality, and connections collectors in parallel via `ThreadPoolExecutor` (controlled by `--workers`); per-repo errors are isolated and logged rather than crashing the run
7. For **dormant repos**: carries forward connections data only (lightweight)
8. Classifies all READMEs via local keyword classifier
9. Builds, renders, and exports reports
10. Prints elapsed time and any failed repos in the final summary

**Key Design:** Dormancy detection avoids expensive re-collection of metadata for unchanged repositories, enabling fast subsequent runs.

### Client (`client.py`)

GitHub API wrapper providing:
- **REST API** via PyGithub (`Github` object)
- **GraphQL** queries via httpx (for topics, complex queries)
- **Rate limit handling** (`rate_limit_sleep()`) to respect GitHub limits
- **Safe sleeps** (`safe_sleep()`) to avoid API throttling

### State Management (`state.py`)

**`RunState` dataclass:**
- `org`: Organization name
- `run_at`: ISO timestamp of run
- `repo_last_activity`: Dict mapping repo name → last push timestamp

**Functions:**
- `load_state(output_dir, org)`: Load previous `{org}_state.json` or None
- `save_state(output_dir, org, repos)`: Save current run state
- `classify_repos(repos, prev_state, dormancy_days)`: Split repos into active/dormant

**Dormancy Logic:**
- If no previous state: classify by age (pushed_at > now - dormancy_days)
- If previous state: mark as dormant if last push timestamp unchanged

### Cache (`cache.py`)

Filesystem cache at `~/.cache/github-organization-profiler/{org}/{repo}/{collector}.json`

**Functions:**
- `get(org, repo, collector, max_age_hours)`: Retrieve cached data if fresh
- `put(org, repo, collector, data)`: Store data in cache

Used by collectors to avoid re-fetching unchanged data within `max_age` window.

### Checkpoint (`checkpoint.py`)

Pipeline-level checkpoint written to `{org}_checkpoint.json` in the output directory after each stage completes. Enables resume after interrupts (keyboard, rate limit, crash).

**Functions:**
- `path(output_dir, org)`: Returns checkpoint file path
- `load(output_dir, org)`: Returns parsed checkpoint dict or `None`
- `save(output_dir, org, last_stage, **data)`: Merges data into checkpoint; writes atomically via `.tmp` rename to avoid partial writes
- `delete(output_dir, org)`: Removes checkpoint on clean completion
- `is_complete(ckpt, stage)`: Returns `True` if `stage` has already been completed in the checkpoint, using ordered stage list

**Stage ordering** (used by `is_complete`):
`repo_metadata` → `topics` → `collection` → `readme` → `contributors`

The `collection` stage covers commits, quality, and connections, which are now run in parallel via `ThreadPoolExecutor`.

**Checkpoint schema:**
```json
{
  "org": "...",
  "last_stage": "collection",
  "repo_data": {...},
  "commit_data": {...},
  "quality_data": {...},
  "connections_data": {...},
  "readme_classes": {...},
  "users": {...},
  "topic_clusters": {...}
}
```

**Resume behavior:** On startup, pipeline auto-detects checkpoint and restores stage data. Completed stages are skipped; in-progress stage loops check `if repo.name not in data` to skip already-collected repos. `--full-refresh` clears checkpoint and starts from scratch.

**Interrupt handling:** `pipeline.py` wraps the entire run body in `try/except (KeyboardInterrupt, Exception)`. On any interrupt, `_flush_on_interrupt()` saves all current partial in-memory data to the checkpoint (preserving `last_stage` of the last *fully* completed stage) and writes a partial `state.json` so dormancy detection works on the next run.

**Rate limit handling:** `rate_limit_sleep(g, on_sleep=callback)` accepts an optional callback invoked before sleeping. Pipeline passes `_on_rate_sleep` which calls `_flush_on_interrupt()` and prints a warning before the process blocks.

### Collectors (`collectors/`)

Each collector returns a dict of data per repo.

#### `repos.py`
Collects repository metadata. Exposes three functions:
- `list_repos(org_obj, max_repos=None)`: Enumerates public repos (uses `itertools.islice` to avoid over-fetching). Called first in pipeline to get a known total for progress reporting.
- `fetch_repo_metadata(repo, org, max_age)`: Fetches metadata + README for a single repo. Called per-repo in pipeline so progress can advance incrementally.
- `collect_repo_metadata(org_obj, org, max_age, max_repos=None)`: Convenience wrapper combining both; used in unit tests.

Metadata fields: name, description, homepage, pushed_at, open_issues_count, forks_count, is_archived, is_fork, has_issues, readme (full text).

#### `commits.py`
Analyzes commit activity using a **6-month bounded window** — a single `get_commits(since=since_6m)` call fetches all commits in the last 180 days, and all metrics are derived from that one result:
- `total_commits`: count of commits in the last 6 months
- `last_commit_at`: timestamp of most recent commit
- `commit_frequency_30d` / `commit_frequency_90d`: subset counts filtered from the 6-month result
- Cached to avoid re-fetching on subsequent runs

#### `users.py`
Collects contributor profiles:
- Per-repo contributor list with commit counts (via `repo.get_contributors()`)
- User bio, company, location, public repos count (via `fetch_user_profile()`)
- Aggregates across org
- `first_commit` / `last_commit` fields are always `None` (removed duplicate `get_commits()` call — commit data is already collected by `commits.py`)

#### `quality.py`
Scans for quality signals using a **single GraphQL query per repo** instead of multiple REST calls:
- Presence of LICENSE, CONTRIBUTING, CODEOWNERS, SECURITY.md, Dependabot config — all checked via `object(expression: "HEAD:<path>")` in one query; missing paths return `null`, no exception
- `licenseInfo { spdxId }` replaces the separate `get_license()` REST call
- GitHub Actions workflows — still 1 REST call via `repo.get_workflows()` (needed for workflow names)
- Issues enabled status — from the PyGithub repo object
- `collect(repo, org, max_age, token)` — `token` is required for the GraphQL call
- **Savings: ~6–8 REST calls per repo replaced by 1 GraphQL query (~35–40% total reduction)**

#### `connections.py`
Analyzes repository relationships:
- Topics (fetched via GraphQL for all repos upfront)
- Fork parent & child forks
- Internal package dependencies (inferred from setup.py, requirements, pyproject.toml)
- Reusable workflow references (.github/workflows/*.yml)
- Builds topic clusters for visualization

For dormant repos, `collect_dormant()` returns topics and connections from the previous report (no API calls).

### Classifiers (`classifiers/`)

#### `local.py`
Keyword/rule-based README classifier. No API key or network access required.

Classifies each repo into one of 13 categories: API / Data Service, CLI Tool, Python Library / SDK, Infrastructure / IaC, Frontend / UI, Design System, Documentation / Reference, Data Pipeline / ETL, ML / AI, Configuration / Shared Tooling, Example / Demo, Archive / Deprecated, Other.

**Algorithm:** Matches repo name, description, GitHub topics, and README text (up to 8000 chars) against per-category keyword lists. Topics count 2× (curator-set signal). Confidence: ≥4 pts → high, ≥2 → medium, else low. Rules checked in order; first-match wins ties.

**Functions:**
- `classify_one(repo_name, readme, description, topics)`: Classify a single repo; returns `{category, summary, confidence}`
- `classify_one_cached(repo_name, readme, description, topics, org, max_age)`: Classify with filesystem cache (key: `readme_class_local`)
- `carry_forward_dormant(dormant_repos, org)`: Load cached classifications for dormant repos

### Reports (`reports/`)

#### `builder.py`
Assembles all collected data into a structured report dict. When a previous report exists, also computes a `delta` section with:
- `repos_added` / `repos_removed` since last run
- `quality_changes`: repos whose quality score changed (with before/after)
- `active_to_dormant` / `dormant_to_active` transitions
- `new_contributors` since last run

**Report Structure:**
```
{
  "org", "generated_at", "prev_run_at",
  "active_repo_count", "dormant_repo_count",
  "users": {...},
  "repos": {
    "repo_name": {
      "dormant", "dormant_since", "activity", "quality",
      "readme_class", "connections", ...
    }
  },
  "connections_summary": {"topic_clusters", "internal_dep_graph"},
  "delta": {   // null on first run
    "repos_added", "repos_removed", "quality_changes",
    "active_to_dormant", "dormant_to_active", "new_contributors"
  }
}
```

#### `render.py`
Generates output files:
- **JSON:** Structured report → `{org}_report.json`
- **Markdown:** Human-readable report with:
  - Table of contents with anchor links
  - Top 5 contributors by commit count in the summary
  - "Changes Since Last Run" section (from `delta`, omitted on first run)
  - Active repos sorted by quality score **ascending** (worst first)
  - "Repos Needing README Attention" callout (category null or confidence low)
  - Dormant repos table sorted alphabetically

#### `csv_export.py`
Exports tabular sections as CSV:
- Repository summary
- Contributors
- Topic clusters
- Quality metrics
- Commit activity
- etc.

## Output Files

After a run, output directory contains:

| File | Format | Purpose |
|------|--------|---------|
| `{org}_report.json` | JSON | Complete structured data, machine-readable |
| `{org}_report.md` | Markdown | Human-readable narrative with tables |
| `{org}_*.csv` | CSV | Tabular sections for spreadsheets/graphing |
| `{org}_state.json` | JSON | Run state; used to detect dormant repos on next run |
| `{org}_checkpoint.json` | JSON | Present only during/after an interrupted run; deleted on clean completion |

## Run Flow

```
1.  CLI: Parse args, load .env
2.  Pipeline: Load previous state + report
3.  GitHub connection
4.  list_repos() → enumerate all public repos (spinner, shows count); --max-repos limits total
5.  fetch_repo_metadata() per repo → X/N progress bar
6.  Fetch all topics via GraphQL (single paginated query)
7.  Classify repos as active/dormant; print newly-dormant repos
8.  Collectors (active repos only, parallel via ThreadPoolExecutor):
    - commits + quality (GraphQL) + connections run per-repo in parallel (--workers, default 4)
    - per-repo errors isolated; failed repos logged, run continues
    - single `collection` checkpoint saved after all futures complete
    - users: contributor profiles (sequential, after collection)
9.  Dormant repos: carry forward connections only (no API calls)
10. Classify READMEs via local keyword classifier
11. Build report structure (including delta vs previous run)
12. Render JSON, Markdown, CSV
13. Save state for next run
14. Print summary with elapsed time and any failed repos
```

## Key Design Patterns

### Incremental Processing
- State tracks repo activity timestamp
- Dormant repos skip expensive collectors
- Cached data respects `max_age` window
- Enables fast subsequent runs on large orgs

### Caching Strategy
- Per-org, per-repo, per-collector cache at `~/.cache/github-organization-profiler`
- `max_age` parameter controls freshness (default 24 hours)
- `--max-age 0` forces re-fetch all
- Collectors check cache before API calls

### README Classification
- Pure keyword/rule-based classifier in `classifiers/local.py` — no API key required
- Matches repo name, description, topics, and README text against per-category keyword rules
- Topics carry 2× weight (curator-set, high signal); README keyword hits carry 1× weight
- Confidence: ≥4 pts → high, ≥2 → medium, else low
- Runs only on active repos; dormant repos reuse cached classification (`readme_class_local` cache key)

### Rate Limiting
- Client monitors GitHub API rate limit via `rl.resources.core` (PyGithub ≥2.3 API)
- Sleeps if remaining < 50; accepts `on_sleep(wait_seconds)` callback invoked before sleeping
- Pipeline passes a callback that saves the checkpoint before any long sleep
- Safe 0.1s sleeps between individual requests

## Dependencies

```toml
PyGithub>=2.3       # REST API wrapper
httpx>=0.27         # GraphQL queries
typer>=0.12         # CLI framework
rich>=13            # Colored output & progress bars
python-dotenv>=1.0  # Environment variable loading
jinja2>=3.1         # Report templating
```

## Environment Variables

**Required:**
- `GITHUB_TOKEN`: GitHub personal access token

## Testing

### Structure
```
tests/
├── conftest.py        # Shared fixtures, CLI option, repo mock helpers
├── fixtures/          # Static JSON fixtures (e.g. sample_report.json)
├── unit/              # Pure unit tests, no API calls
└── integration/       # Tests that hit the real GitHub API
```

### Running Tests

```bash
# Unit tests only (default — integration tests auto-skipped)
uv run pytest tests/unit/

# Integration tests (requires GITHUB_TOKEN, hits real GitHub API)
GITHUB_TOKEN=ghp_... uv run pytest tests/integration/ --run-integration

# All tests, skipping integration
uv run pytest
```

### How Integration Tests Work

Two guards in `conftest.py` protect against accidental live API calls:
1. **`--run-integration` flag** — integration tests are skipped unless explicitly passed
2. **`github_token` fixture** — skips the test if `GITHUB_TOKEN` env var is not set

Default target org is `"github"`, safe to test against without any special setup. Integration tests cap repo fetches at `max_repos=5` to avoid enumerating hundreds of repos.

### Writing Integration Tests

```python
@pytest.mark.integration
def test_something_live(github_token):
    g = get_github(github_token)
    # ... real API calls
```

### Shared Fixtures (`conftest.py`)

- `github_token`: Reads `GITHUB_TOKEN` env var; skips test if absent
- `sample_report`: Loads `tests/fixtures/sample_report.json`
- `mock_repo`: A `MagicMock` repo with `name="test-repo"`, `pushed_at=2026-05-01`
- `make_repo`: Factory function to create custom mock repos

## Notes for Development

1. **State & Dormancy:** Changes to dormancy logic or state structure should be carefully considered; old state files must be handled gracefully.
2. **Cache Location:** Uses `~/.cache/github-organization-profiler`; can grow large on long-running orgs. Users can delete to force full re-fetch.
3. **API Limits:** GitHub allows 5,000 REST calls/hour. Large orgs with many collectors may hit limits; adjust or use token from bot account.
5. **GraphQL Queries:** Topics fetched via GraphQL upfront for all repos; a single query with pagination.
6. **Checkpoint & Resume:** `checkpoint.py` is the single source of truth for stage ordering. Current stages: `repo_metadata → topics → collection → readme → contributors`. Adding a new pipeline stage requires adding it to `_STAGES` in `checkpoint.py` and inserting the corresponding `_save_ckpt()` call in `pipeline.py`. Do not change the order of existing stages without migrating existing checkpoint files. Old checkpoints with `last_stage: "commits"` or `"quality"` will not be recognized (treated as pre-collection), which is safe.
7. **Interrupt Safety:** `_flush_on_interrupt` in `pipeline.py` silently swallows its own exceptions (bare `except Exception: pass`) to avoid masking the original error. Keep this handler minimal.
