# GitHub Org Profiler — Architecture Reference

## Overview

`gh-org-profile` is a CLI tool that profiles GitHub organizations by collecting structured data about repositories and generating multi-format reports (JSON, Markdown, CSV). The tool is designed to be **incremental**: it skips detailed collection for dormant repos on subsequent runs, only updating lightweight metrics.

## Project Structure

```
src/gh_org_profile/
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
├── classifiers/       # LLM-based analysis
│   └── readme.py      # README classification via Anthropic API
└── reports/           # Report generation
    ├── builder.py     # Assemble structured report data
    ├── render.py      # Output JSON & Markdown
    └── csv_export.py  # Export CSV tables
```

## Key Components

### CLI (`cli.py`)

**Entrypoint:** `gh-org-profile --org <name> [options]`

**Options:**
- `--org` (required): GitHub organization name
- `--token`: GitHub PAT; fallback to `GITHUB_TOKEN` env var
- `--no-llm`: Skip LLM README classification (faster, reduced API calls)
- `--full-refresh`: Treat all repos as active (ignore dormancy state)
- `--dormancy-days`: Days without push to mark repo dormant (default: 90)
- `--max-age`: Cache max age in hours; 0 = always re-fetch (default: 24)
- `--output`: Output directory for reports (default: `./output`)

### Pipeline (`pipeline.py`)

Main orchestration that:
1. Loads previous run state from `{org}_state.json`
2. Connects to GitHub
3. Enumerates repos via `list_repos()` (shows count before fetching metadata)
4. Fetches per-repo metadata + READMEs with a live `X/N` progress bar
5. Classifies repos as active (changed) or dormant (unchanged since last run)
6. For **active repos**: runs full collectors (commits, quality, connections, contributors)
7. For **dormant repos**: carries forward connections data only (lightweight)
8. Classifies all READMEs via LLM (unless `--no-llm`)
9. Builds, renders, and exports reports

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

Filesystem cache at `~/.cache/gh-org-profile/{org}/{repo}/{collector}.json`

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
`repo_metadata` → `topics` → `commits` → `quality` → `connections` → `readme` → `contributors`

**Checkpoint schema:**
```json
{
  "org": "...",
  "last_stage": "commits",
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
- Per-repo contributor list with commit counts
- User bio, company, location, public repos count
- Aggregates across org

#### `quality.py`
Scans for quality signals:
- Presence of LICENSE, CONTRIBUTING, CODEOWNERS, SECURITY.md
- GitHub Actions workflows
- Dependabot configuration
- Issues enabled status
- Computes quality_score (0-7 based on presence flags)

#### `connections.py`
Analyzes repository relationships:
- Topics (fetched via GraphQL for all repos upfront)
- Fork parent & child forks
- Internal package dependencies (inferred from setup.py, requirements, pyproject.toml)
- Reusable workflow references (.github/workflows/*.yml)
- Builds topic clusters for visualization

For dormant repos, `collect_dormant()` returns topics and connections from the previous report (no API calls).

### Classifiers (`classifiers/`)

#### `readme.py`
Uses Anthropic API to classify README content:

**LLM Prompt:** System role instructs Claude Haiku to categorize repo into one of 13 categories (API, CLI, Library, Infrastructure, Frontend, Design System, Documentation, Data Pipeline, ML/AI, Configuration, Example, Archive, Other).

**Functions:**
- `classify_active(active_repos, repo_data, org, max_age, no_llm)`: Classify active repos via LLM or return empty
- `carry_forward_dormant(dormant_repos, org)`: Load cached classifications from previous report
- Uses cache to avoid redundant LLM calls

### Reports (`reports/`)

#### `builder.py`
Assembles all collected data into a structured report dict:

**Report Structure:**
```
{
  "metadata": {org, run_at, ...},
  "summary": {active_count, dormant_count, contributor_count, ...},
  "repositories": {
    "repo_name": {
      "url", "description", "activity", "quality",
      "readme_class", "topics", "connections", ...
    }
  },
  "contributors": {...},
  "topic_clusters": {...},
}
```

#### `render.py`
Generates output files:
- **JSON:** Structured report → `{org}_report.json`
- **Markdown:** Human-readable narrative with embedded tables → `{org}_report.md`

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
4.  list_repos() → enumerate all public repos (spinner, shows count)
5.  fetch_repo_metadata() per repo → X/N progress bar
6.  Fetch all topics via GraphQL (single paginated query)
7.  Classify repos as active/dormant
8.  Collectors (active repos only, X/N progress per collector):
    - commits: 6-month bounded window, all metrics derived from one fetch
    - quality: CI, license, CODEOWNERS, dependabot
    - connections: forks, deps, workflow refs
    - users: contributor profiles
9.  Dormant repos: carry forward connections only (no API calls)
10. Classify READMEs via LLM (or skip with --no-llm)
11. Build report structure
12. Render JSON, Markdown, CSV
13. Save state for next run
14. Print summary
```

## Key Design Patterns

### Incremental Processing
- State tracks repo activity timestamp
- Dormant repos skip expensive collectors
- Cached data respects `max_age` window
- Enables fast subsequent runs on large orgs

### Caching Strategy
- Per-org, per-repo, per-collector cache at `~/.cache/gh-org-profile`
- `max_age` parameter controls freshness (default 24 hours)
- `--max-age 0` forces re-fetch all
- Collectors check cache before API calls

### LLM Classification
- Uses Anthropic API (Claude Haiku) for README classification
- Runs only on active repos; dormant repos reuse previous classification
- `--no-llm` flag disables for faster runs

### Rate Limiting
- Client monitors GitHub API rate limit via `rl.resources.core` (PyGithub ≥2.3 API)
- Sleeps if remaining < 50; accepts `on_sleep(wait_seconds)` callback invoked before sleeping
- Pipeline passes a callback that saves the checkpoint before any long sleep
- Safe 0.1s sleeps between individual requests

## Dependencies

```toml
PyGithub>=2.3       # REST API wrapper
httpx>=0.27         # GraphQL queries
anthropic>=0.28     # LLM classification
typer>=0.12         # CLI framework
rich>=13            # Colored output & progress bars
python-dotenv>=1.0  # Environment variable loading
jinja2>=3.1         # Report templating
```

## Environment Variables

**Required:**
- `GITHUB_TOKEN`: GitHub personal access token

**Optional:**
- `ANTHROPIC_API_KEY`: Anthropic API key (required if LLM classification enabled)

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
2. **Cache Location:** Uses `~/.cache/gh-org-profile`; can grow large on long-running orgs. Users can delete to force full re-fetch.
3. **LLM Cost:** Each active repo runs through LLM; consider cost on large orgs. Use `--no-llm` for cost-sensitive runs.
4. **API Limits:** GitHub allows 5,000 REST calls/hour. Large orgs with many collectors may hit limits; adjust or use token from bot account.
5. **GraphQL Queries:** Topics fetched via GraphQL upfront for all repos; a single query with pagination.
6. **Checkpoint & Resume:** `checkpoint.py` is the single source of truth for stage ordering. Adding a new pipeline stage requires adding it to `_STAGES` in `checkpoint.py` and inserting the corresponding `_save_ckpt()` call in `pipeline.py`. Do not change the order of existing stages without migrating existing checkpoint files.
7. **Interrupt Safety:** `_flush_on_interrupt` in `pipeline.py` silently swallows its own exceptions (bare `except Exception: pass`) to avoid masking the original error. Keep this handler minimal.
