from __future__ import annotations

from pathlib import Path

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
    token: str | None = typer.Option(
        None, "--token", envvar="GITHUB_TOKEN", help="GitHub personal access token"
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
    output: Path | None = typer.Option(
        None, "--output", help="Directory for report output files (default: ./output/<org>)"
    ),
    workers: int = typer.Option(
        4, "--workers", help="Number of parallel workers for repo collection (default: 4)"
    ),
    max_repos: int | None = typer.Option(
        None, "--max-repos", help="Limit number of repos processed (useful for testing)"
    ),
    stages: str | None = typer.Option(
        None,
        "--stages",
        help=(
            "Comma-separated list of stages to run: topics,collection,readme,contributors. "
            "Omit to run all stages. repo_metadata always runs. "
            "Requires a previous report to exist for skipped stages."
        ),
    ),
) -> None:
    if not token:
        typer.echo("Error: --token or GITHUB_TOKEN env var is required", err=True)
        raise typer.Exit(1)

    _ALL_SELECTABLE = {"topics", "collection", "readme", "contributors"}

    run_stages: set[str] | None = None
    if stages:
        if full_refresh:
            typer.echo("Error: --stages and --full-refresh are mutually exclusive", err=True)
            raise typer.Exit(1)
        requested = {s.strip() for s in stages.split(",")}
        invalid = requested - _ALL_SELECTABLE
        if invalid:
            typer.echo(
                f"Error: unknown stage(s): {', '.join(sorted(invalid))}. "
                f"Valid: {', '.join(sorted(_ALL_SELECTABLE))}",
                err=True,
            )
            raise typer.Exit(1)
        run_stages = requested

    output_dir = output if output is not None else Path("output") / org

    from github_organization_profiler import pipeline

    pipeline.run(
        org=org,
        token=token,
        full_refresh=full_refresh,
        dormancy_days=dormancy_days,
        max_age=max_age,
        output_dir=output_dir,
        max_workers=workers,
        max_repos=max_repos,
        stages=run_stages,
    )
