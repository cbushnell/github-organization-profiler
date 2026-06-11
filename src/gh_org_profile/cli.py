from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv

load_dotenv()

app = typer.Typer(
    help=(
        "Profile all public repositories in a GitHub organization.\n\n"
        "If a previous run was interrupted, a checkpoint file is detected automatically "
        "and the pipeline resumes from the last completed stage. "
        "Use --full-refresh to discard any existing checkpoint and start from scratch."
    )
)


@app.command()
def main(
    org: str = typer.Option(..., "--org", help="GitHub organization name"),
    token: Optional[str] = typer.Option(
        None, "--token", envvar="GITHUB_TOKEN", help="GitHub personal access token"
    ),
    no_llm: bool = typer.Option(
        False, "--no-llm", help="Skip LLM README classification"
    ),
    full_refresh: bool = typer.Option(
        False, "--full-refresh", help="Re-collect all repos regardless of state"
    ),
    dormancy_days: int = typer.Option(
        90, "--dormancy-days", help="Days without a push to consider a repo dormant"
    ),
    max_age: int = typer.Option(
        24, "--max-age", help="Cache max age in hours (0 = always re-fetch)"
    ),
    output: Path = typer.Option(
        Path("output"), "--output", help="Directory for report output files"
    ),
    workers: int = typer.Option(
        4, "--workers", help="Number of parallel workers for repo collection (default: 4)"
    ),
    max_repos: Optional[int] = typer.Option(
        None, "--max-repos", help="Limit number of repos processed (useful for testing)"
    ),
    reclassify_readme: bool = typer.Option(
        False, "--reclassify-readme",
        help="Clear cached null README classifications and re-run LLM classification only"
    ),
) -> None:
    if not token:
        typer.echo("Error: --token or GITHUB_TOKEN env var is required", err=True)
        raise typer.Exit(1)

    output.mkdir(parents=True, exist_ok=True)

    from gh_org_profile import pipeline
    pipeline.run(
        org=org,
        token=token,
        no_llm=no_llm,
        full_refresh=full_refresh,
        dormancy_days=dormancy_days,
        max_age=max_age,
        output_dir=output,
        max_workers=workers,
        max_repos=max_repos,
        reclassify_readme=reclassify_readme,
    )
