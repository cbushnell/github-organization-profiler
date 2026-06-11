from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn

console = Console()


def _collect_repo(repo, org, max_age, commits_mod, quality_mod, connections_mod, token):
    """Run commits, quality, and connections collectors for one repo. Called from worker threads."""
    return (
        repo.name,
        commits_mod.collect(repo, org, max_age),
        quality_mod.collect(repo, org, max_age, token),
        connections_mod.collect_active(repo, token, org, max_age),
    )


def run(
    org: str,
    token: str,
    no_llm: bool,
    full_refresh: bool,
    dormancy_days: int,
    max_age: int,
    output_dir: Path,
    max_workers: int = 4,
    max_repos: int | None = None,
    reclassify_readme: bool = False,
) -> None:
    from gh_org_profile import cache
    from gh_org_profile import checkpoint as checkpoint_mod
    from gh_org_profile import state as state_mod
    from gh_org_profile.client import get_github, get_org, rate_limit_sleep
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
    start_time = time.monotonic()

    # --- Checkpoint ---
    ckpt = checkpoint_mod.load(output_dir, org)
    if full_refresh and ckpt:
        checkpoint_mod.delete(output_dir, org)
        ckpt = None
        console.print("[yellow]Full refresh: cleared existing checkpoint.")
    if ckpt:
        console.print(f"[yellow]Resuming from checkpoint (last completed stage: {ckpt['last_stage']})")

    # Aggregated data — restored from checkpoint or empty
    repo_data: dict = (ckpt or {}).get("repo_data") or {}
    commit_data: dict = (ckpt or {}).get("commit_data") or {}
    quality_data: dict = (ckpt or {}).get("quality_data") or {}
    connections_data: dict = (ckpt or {}).get("connections_data") or {}
    readme_classes: dict = (ckpt or {}).get("readme_classes") or {}
    users: dict = (ckpt or {}).get("users") or {}
    topic_clusters: dict = (ckpt or {}).get("topic_clusters") or {}
    repos: list = []
    active_repos: list = []
    dormant_repos: list = []
    failed_repos: dict = {}

    def _save_ckpt(stage: str, **data: Any) -> None:
        checkpoint_mod.save(output_dir, org, stage, **data)

    def _flush_on_interrupt() -> None:
        """Persist all in-memory data collected so far and save partial state."""
        try:
            existing = checkpoint_mod.load(output_dir, org) or {}
            last_completed = existing.get("last_stage", "none")
            flush_data = {
                k: v for k, v in {
                    "repo_data": repo_data,
                    "commit_data": commit_data,
                    "quality_data": quality_data,
                    "connections_data": connections_data,
                    "readme_classes": readme_classes,
                    "users": users,
                    "topic_clusters": topic_clusters,
                }.items() if v
            }
            checkpoint_mod.save(output_dir, org, last_completed, **flush_data)
            if repos:
                state_mod.save_state(output_dir, org, repos)
            ckpt_path = checkpoint_mod.path(output_dir, org)
            console.print(
                f"\n[yellow]Interrupted. Checkpoint saved to "
                f"[bold]{ckpt_path.name}[/bold] — re-run to resume."
            )
        except Exception:
            pass

    try:
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

        # --- Enumerate repos (always required for PyGithub objects) ---
        console.print(f"[cyan]Fetching repository list for [bold]{org}[/bold]...")
        with console.status("[bold green]Enumerating repositories..."):
            repos = repos_mod.list_repos(org_obj, max_repos=max_repos)
        console.print(f"[cyan]Found [bold]{len(repos)}[/bold] public repos.")

        # --- Stage: repo_metadata ---
        if checkpoint_mod.is_complete(ckpt, "repo_metadata"):
            console.print(f"[yellow]repo_metadata: restored {len(repo_data)} repos from checkpoint.")
        else:
            console.print("Fetching metadata...")
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
            _save_ckpt("repo_metadata", repo_data=repo_data)

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
            # B4: report repos that went dormant since the previous run
            if prev_report:
                prev_repos = prev_report.get("repos", {})
                newly_dormant = [
                    r for r in dormant_repos
                    if r.name in prev_repos and not prev_repos[r.name].get("dormant", True)
                ]
                if newly_dormant:
                    names = ", ".join(r.name for r in newly_dormant[:5])
                    suffix = " ..." if len(newly_dormant) > 5 else ""
                    console.print(
                        f"[yellow]  Newly dormant ({len(newly_dormant)}): {names}{suffix}"
                    )

        # --- Stage: topics ---
        if checkpoint_mod.is_complete(ckpt, "topics"):
            console.print(f"[yellow]topics: restored {len(topic_clusters)} clusters from checkpoint.")
        else:
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
            for name, topics in repo_topics.items():
                repo_data.setdefault(name, {})["topics"] = topics
            # Save repo_data again so restored checkpoints include merged topics
            _save_ckpt("topics", topic_clusters=topic_clusters, repo_data=repo_data)

        # --- Collectors for active repos ---
        if active_repos:
            def _on_rate_sleep(wait: float) -> None:
                _flush_on_interrupt()
                console.print(f"[yellow]Rate limit reached — sleeping {wait:.0f}s (checkpoint saved).")

            # Stage: collection (commits + quality + connections in parallel)
            if checkpoint_mod.is_complete(ckpt, "collection"):
                console.print(
                    f"[yellow]collection: restored {len(commit_data)} repos from checkpoint."
                )
            else:
                rate_limit_sleep(g, on_sleep=_on_rate_sleep)
                repos_to_collect = [r for r in active_repos if r.name not in commit_data]
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    MofNCompleteColumn(),
                    console=console,
                ) as progress:
                    task = progress.add_task(
                        f"[green]Collecting ({len(repos_to_collect)} repos, {max_workers} workers)...",
                        total=len(repos_to_collect),
                    )
                    with ThreadPoolExecutor(max_workers=max_workers) as pool:
                        futures = {
                            pool.submit(
                                _collect_repo, repo, org, max_age,
                                commits_mod, quality_mod, connections_mod, token,
                            ): repo
                            for repo in repos_to_collect
                        }
                        for future in as_completed(futures):
                            repo = futures[future]
                            try:
                                name, cd, qd, cod = future.result()
                                commit_data[name] = cd
                                quality_data[name] = qd
                                connections_data[name] = cod
                            except Exception as exc:
                                failed_repos[repo.name] = str(exc)
                                console.print(f"[red]  {repo.name}: collection failed — {exc}[/red]")
                            progress.advance(task)
                _save_ckpt("collection", commit_data=commit_data,
                           quality_data=quality_data, connections_data=connections_data)

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

        # --- Stage: readme ---
        if reclassify_readme:
            n = cache.evict_null_readme_classes(org)
            console.print(f"[cyan]--reclassify-readme: evicted {n} null readme_class cache entries.")
        if checkpoint_mod.is_complete(ckpt, "readme"):
            console.print(f"[yellow]readme: restored {len(readme_classes)} repos from checkpoint.")
        elif no_llm:
            console.print("[cyan]Classifying READMEs (skipped — --no-llm)")
            readme_classes = {r.name: {"category": None, "summary": None, "confidence": "n/a"} for r in active_repos}
            _save_ckpt("readme", readme_classes=readme_classes)
        else:
            llm_client = readme_mod.make_client()
            if not llm_client:
                console.print("[yellow]Skipping README classification (ANTHROPIC_API_KEY not set)")
                readme_classes = {r.name: {"category": None, "summary": None, "confidence": "n/a"} for r in active_repos}
                _save_ckpt("readme", readme_classes=readme_classes)
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
                        if repo.name not in readme_classes:
                            readme = (repo_data.get(repo.name) or {}).get("readme") or ""
                            readme_classes[repo.name] = readme_mod.classify_one_cached(
                                llm_client, repo.name, readme, org, max_age
                            )
                        progress.advance(task)
                _save_ckpt("readme", readme_classes=readme_classes)
        readme_classes_dormant = readme_mod.carry_forward_dormant(dormant_repos, org)
        readme_classes.update(readme_classes_dormant)

        # --- Stage: contributors ---
        if checkpoint_mod.is_complete(ckpt, "contributors"):
            console.print(f"[yellow]contributors: restored {len(users)} unique users from checkpoint.")
        elif active_repos:
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
            _save_ckpt("contributors", users=users)

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

        # --- Save state and clean up checkpoint ---
        state_mod.save_state(output_dir, org, repos)
        checkpoint_mod.delete(output_dir, org)

        # --- Summary ---
        elapsed = time.monotonic() - start_time
        mins, secs = divmod(int(elapsed), 60)
        console.print()
        console.print(f"[bold green]Done![/bold green] Reports written to [bold]{output_dir}[/bold]:")
        console.print(f"  [blue]{json_path.name}[/blue]")
        console.print(f"  [blue]{md_path.name}[/blue]")
        for p in csv_paths:
            console.print(f"  [blue]{p.name}[/blue]")
        if failed_repos:
            names = ", ".join(list(failed_repos)[:5])
            suffix = " ..." if len(failed_repos) > 5 else ""
            console.print(f"[yellow]  {len(failed_repos)} repos failed collection: {names}{suffix}")
        console.print(f"[dim]Done in {mins}m {secs}s[/dim]")

    except (KeyboardInterrupt, Exception):
        _flush_on_interrupt()
        raise
