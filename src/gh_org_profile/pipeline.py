from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn

console = Console()


def run(
    org: str,
    token: str,
    no_llm: bool,
    full_refresh: bool,
    dormancy_days: int,
    max_age: int,
    output_dir: Path,
) -> None:
    from gh_org_profile import state as state_mod
    from gh_org_profile.client import get_github, get_org
    from gh_org_profile.collectors import repos as repos_mod
    from gh_org_profile.collectors import commits as commits_mod
    from gh_org_profile.collectors import users as users_mod
    from gh_org_profile.collectors import quality as quality_mod
    from gh_org_profile.collectors import connections as connections_mod
    from gh_org_profile.classifiers import readme as readme_mod
    from gh_org_profile.reports import builder as builder_mod
    from gh_org_profile.reports import render as render_mod
    from gh_org_profile.reports import csv_export

    run_at = datetime.now(timezone.utc).isoformat()

    # --- Load previous state and report ---
    prev_state = state_mod.load_state(output_dir, org)
    report_path = output_dir / f"{org}_report.json"
    prev_report: dict | None = None
    if report_path.exists():
        try:
            prev_report = json.loads(report_path.read_text())
        except Exception:
            pass

    # --- GitHub client ---
    with console.status("[bold green]Connecting to GitHub..."):
        g = get_github(token)
        org_obj = get_org(g, org)

    # --- Fetch all repo metadata ---
    console.print(f"[cyan]Fetching repository list for [bold]{org}[/bold]...")
    with console.status("[bold green]Enumerating repositories..."):
        repos = repos_mod.list_repos(org_obj)
    console.print(f"[cyan]Found [bold]{len(repos)}[/bold] public repos. Fetching metadata...")
    repo_data: dict = {}
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Fetching repo metadata...", total=len(repos))
        for repo in repos:
            repo_data[repo.name] = repos_mod.fetch_repo_metadata(repo, org, max_age)
            progress.advance(task)

    # --- Classify active vs dormant ---
    if full_refresh:
        active_repos, dormant_repos = repos, []
        console.print(f"[yellow]Full refresh: treating all {len(repos)} repos as active.")
    else:
        active_repos, dormant_repos = state_mod.classify_repos(repos, prev_state, dormancy_days)
        console.print(
            f"[green]{len(active_repos)} active[/green] / "
            f"[yellow]{len(dormant_repos)} dormant[/yellow] repos"
        )

    # --- Fetch all topics via GraphQL (all repos) ---
    try:
        with console.status("[bold green]Fetching topics via GraphQL... (0 repos)") as status:
            def _on_page(count: int) -> None:
                status.update(f"[bold green]Fetching topics via GraphQL... ({count} repos)")
            repo_topics = connections_mod.fetch_all_topics(token, org, on_page=_on_page)
        console.print(f"[cyan]Topics fetched for [bold]{len(repo_topics)}[/bold] repos.")
    except Exception:
        repo_topics = {}
        console.print("[yellow]Warning: topic fetch failed, skipping.")
    topic_clusters = connections_mod.build_topic_clusters(repo_topics)
    # Merge topics into repo_data
    for name, topics in repo_topics.items():
        if name in repo_data:
            repo_data[name]["topics"] = topics
        else:
            repo_data[name] = {"topics": topics}

    # --- Collectors for active repos ---
    commit_data: dict = {}
    quality_data: dict = {}
    connections_data: dict = {}

    if active_repos:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"[green]Commits ({len(active_repos)} active)...", total=len(active_repos)
            )
            for repo in active_repos:
                commit_data[repo.name] = commits_mod.collect(repo, org, max_age)
                progress.advance(task)

            task = progress.add_task(
                f"[green]Quality ({len(active_repos)} active)...", total=len(active_repos)
            )
            for repo in active_repos:
                quality_data[repo.name] = quality_mod.collect(repo, org, max_age)
                progress.advance(task)

            task = progress.add_task(
                f"[green]Connections ({len(active_repos)} active)...", total=len(active_repos)
            )
            for repo in active_repos:
                connections_data[repo.name] = connections_mod.collect_active(repo, token, org, max_age)
                progress.advance(task)

    # --- Carry-forward connections for dormant repos ---
    if dormant_repos:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task(
                f"[yellow]Carrying forward dormant ({len(dormant_repos)})...",
                total=len(dormant_repos),
            )
            for repo in dormant_repos:
                connections_data[repo.name] = connections_mod.collect_dormant(repo, org)
                progress.advance(task)

    # --- README classification ---
    readme_classes: dict = {}
    if no_llm:
        console.print("[cyan]Classifying READMEs (skipped — --no-llm)")
        readme_classes = {r.name: {"category": None, "summary": None, "confidence": "n/a"} for r in active_repos}
    else:
        llm_client = readme_mod.make_client()
        if not llm_client:
            console.print("[yellow]Skipping README classification (ANTHROPIC_API_KEY not set)")
            readme_classes = {r.name: {"category": None, "summary": None, "confidence": "n/a"} for r in active_repos}
        else:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                console=console,
            ) as progress:
                task = progress.add_task(
                    f"[green]Classifying READMEs ({len(active_repos)} active)...",
                    total=len(active_repos),
                )
                for repo in active_repos:
                    readme = (repo_data.get(repo.name) or {}).get("readme") or ""
                    readme_classes[repo.name] = readme_mod.classify_one_cached(
                        llm_client, repo.name, readme, org, max_age
                    )
                    progress.advance(task)
    readme_classes_dormant = readme_mod.carry_forward_dormant(dormant_repos, org)
    readme_classes.update(readme_classes_dormant)

    # --- Contributors ---
    users: dict = {}
    if active_repos:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"[green]Contributors ({len(active_repos)} repos)...", total=len(active_repos)
            )
            for repo in active_repos:
                users_mod.collect_repo_contributors(repo, users, org, max_age)
                progress.advance(task)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"[green]User profiles ({len(users)} unique)...", total=len(users)
            )
            for login in list(users):
                users_mod.fetch_user_profile(login, users, g, org, max_age)
                progress.advance(task)

    # --- Build report ---
    console.print("[cyan]Building report...")
    report = builder_mod.build_report(
        org=org,
        run_at=run_at,
        prev_report=prev_report,
        active_repos=active_repos,
        dormant_repos=dormant_repos,
        repo_data=repo_data,
        commit_data=commit_data,
        quality_data=quality_data,
        connections_data=connections_data,
        readme_classes=readme_classes,
        users=users,
        topic_clusters=topic_clusters,
    )

    # --- Render + CSV ---
    console.print("[cyan]Writing reports...")
    csv_paths = csv_export.export_all(report, output_dir, org)
    output_files = [str(p.name) for p in csv_paths] + [
        f"{org}_report.json",
        f"{org}_report.md",
    ]
    json_path, md_path = render_mod.render(report, output_dir, org, output_files)

    # --- Save state ---
    state_mod.save_state(output_dir, org, repos)

    # --- Summary ---
    console.print()
    console.print(f"[bold green]Done![/bold green] Reports written to [bold]{output_dir}[/bold]:")
    console.print(f"  [blue]{json_path.name}[/blue]")
    console.print(f"  [blue]{md_path.name}[/blue]")
    for p in csv_paths:
        console.print(f"  [blue]{p.name}[/blue]")
