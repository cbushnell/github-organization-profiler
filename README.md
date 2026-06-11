# gh-org-profile

Profile all public repositories in a GitHub organization — commit activity, quality signals, LLM-classified READMEs, and multi-format reports.

## Features

- Collects metadata, commit frequency, quality signals, topics, fork graph, and contributor profiles for every public repo
- Classifies READMEs into 13 categories via Claude Haiku (API/CLI/Library/Infrastructure/etc.)
- Incremental: dormant repos (no push activity since last run) skip expensive re-collection
- Interrupt-safe: checkpoints after each stage; resumes automatically on next run
- Outputs JSON, Markdown, and CSV reports
- Parallel collection via configurable worker threads

## Requirements

- Python ≥ 3.11
- A GitHub personal access token (PAT) with `repo:read` or `public_repo` scope
- An Anthropic API key (optional — only needed for LLM README classification)

## Installation

```bash
pip install gh-org-profile
# or with uv:
uv tool install gh-org-profile
```

## Configuration

Environment variables (can also use a `.env` file):

```
GITHUB_TOKEN=ghp_...
ANTHROPIC_API_KEY=sk-ant-...   # optional — skip with --no-llm
```

## Usage

```bash
gh-org-profile --org <name>
```

Common examples:

```bash
# Skip LLM classification (faster, no Anthropic key needed)
gh-org-profile --org <name> --no-llm

# Force full re-collection (ignore dormancy + discard checkpoint)
gh-org-profile --org <name> --full-refresh

# Re-run only README classification (fix stale null classifications)
gh-org-profile --org <name> --reclassify-readme

# Write reports to a custom directory
gh-org-profile --org <name> --output ./reports

# Limit repos processed (useful for testing)
gh-org-profile --org <name> --max-repos 10
```

## Options

| Option | Default | Description |
|--------|---------|-------------|
| `--org` | *(required)* | GitHub organization name |
| `--token` | `$GITHUB_TOKEN` | GitHub personal access token |
| `--no-llm` | off | Skip LLM README classification |
| `--full-refresh` | off | Re-collect all repos; discard checkpoint |
| `--reclassify-readme` | off | Evict null cached README classifications and re-run LLM |
| `--dormancy-days` | `90` | Days without a push to mark a repo dormant |
| `--max-age` | `24` | Cache max age in hours (0 = always re-fetch) |
| `--output` | `./output` | Directory for report files |
| `--workers` | `4` | Parallel worker threads for repo collection |
| `--max-repos` | *(none)* | Cap on number of repos processed |

## Output Files

| File | Format | Description |
|------|--------|-------------|
| `{org}_report.json` | JSON | Complete structured data, machine-readable |
| `{org}_report.md` | Markdown | Human-readable report with tables, delta section, quality rankings |
| `{org}_*.csv` | CSV | Tabular exports (repos, contributors, topics, quality, commits) |
| `{org}_state.json` | JSON | Run state; used for dormancy detection on next run |

## License

CC0 1.0 — public domain. See `LICENSE`.
