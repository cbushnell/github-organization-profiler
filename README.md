# github-organization-profiler

[![CI](https://github.com/cbushnell/github-organization-profiler/actions/workflows/ci.yml/badge.svg)](https://github.com/cbushnell/github-organization-profiler/actions/workflows/ci.yml)
[![CodeQL](https://github.com/cbushnell/github-organization-profiler/actions/workflows/codeql.yml/badge.svg)](https://github.com/cbushnell/github-organization-profiler/actions/workflows/codeql.yml)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: CC0-1.0](https://img.shields.io/badge/License-CC0_1.0-lightgrey.svg)](http://creativecommons.org/publicdomain/zero/1.0/)

Profile all public repositories in a GitHub organization — commit activity, quality signals, keyword-classified READMEs, and multi-format reports.

## Features

- Collects metadata, commit frequency, quality signals, topics, fork graph, and contributor profiles for every public repo
- Classifies READMEs into 13 categories using a local keyword classifier (API/CLI/Library/Infrastructure/etc.)
- Selective stage execution: re-run only the parts you need (e.g. `--stages readme` or `--stages contributors`)
- Incremental: dormant repos (no push activity since last run) skip expensive re-collection
- Interrupt-safe: checkpoints after each stage; resumes automatically on next run
- Outputs JSON, Markdown, and CSV reports
- Parallel collection via configurable worker threads

## Requirements

- Python ≥ 3.11
- A GitHub personal access token (PAT) with `repo:read` or `public_repo` scope

## Installation

```bash
pip install github-organization-profiler
# or with uv:
uv tool install github-organization-profiler
```

## Configuration

Environment variables (can also use a `.env` file):

```
GITHUB_TOKEN=ghp_...
```

## Usage

```bash
github-organization-profiler --org <name>
```

Common examples:

```bash
# Force full re-collection (ignore dormancy + discard checkpoint)
github-organization-profiler --org <name> --full-refresh

# Re-run only README classification (fast, no API needed)
github-organization-profiler --org <name> --stages readme

# Refresh contributor profiles only
github-organization-profiler --org <name> --stages contributors

# Refresh commit metrics and re-classify READMEs
github-organization-profiler --org <name> --stages collection,readme

# Write reports to a custom directory
github-organization-profiler --org <name> --output ./reports

# Limit repos processed (useful for testing)
github-organization-profiler --org <name> --max-repos 10
```

## Options

| Option | Default | Description |
|--------|---------|-------------|
| `--org` | *(required)* | GitHub organization name |
| `--token` | `$GITHUB_TOKEN` | GitHub personal access token |
| `--full-refresh` | off | Re-collect all repos; discard checkpoint |
| `--stages` | *(all)* | Comma-separated stages to run: `topics,collection,readme,contributors`. Omit to run all. Mutually exclusive with `--full-refresh`. |
| `--dormancy-days` | `90` | Days without a push to mark a repo dormant |
| `--max-age` | `24` | Cache max age in hours (0 = always re-fetch) |
| `--output` | `./<org>` | Directory for report files |
| `--workers` | `4` | Parallel worker threads for repo collection |
| `--max-repos` | *(none)* | Cap on number of repos processed |

## Output Files

| File | Format | Description |
|------|--------|-------------|
| `{org}_report.json` | JSON | Complete structured data, machine-readable |
| `{org}_report.md` | Markdown | Human-readable report with tables, delta section, quality rankings |
| `{org}_*.csv` | CSV | Tabular exports (repos, contributors, topics, quality, commits) |
| `{org}_state.json` | JSON | Run state; used for dormancy detection on next run |

See [REPORT_SCHEMA.md](REPORT_SCHEMA.md) for a full breakdown of every field in the JSON report and CSV tables.

## License

CC0 1.0 — public domain. See `LICENSE`.
