#!/usr/bin/env python3
"""Read-only GitHub patrol snapshot and stable-fold helper."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence


SCHEMA = "opl.github_patrol_snapshot.v1"
GH_JSON = Sequence[str]


@dataclass(frozen=True)
class CommandFailure(Exception):
    argv: tuple[str, ...]
    returncode: int
    stderr: str

    def __str__(self) -> str:
        return f"command failed ({self.returncode}): {' '.join(self.argv)}: {self.stderr}"


def run_text(argv: GH_JSON) -> str:
    try:
        result = subprocess.run(
            list(argv),
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise CommandFailure(tuple(argv), 127, "command not found") from exc
    if result.returncode != 0:
        raise CommandFailure(tuple(argv), result.returncode, result.stderr.strip())
    return result.stdout.strip()


def run_json(argv: GH_JSON) -> Any:
    output = run_text(argv)
    if not output:
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise CommandFailure(tuple(argv), 65, "command returned invalid JSON") from exc


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def error_class(message: str) -> str:
    lowered = message.lower()
    if any(token in lowered for token in ("bad credentials", "http 401", "authentication")):
        return "auth_invalid"
    if "http 403" in lowered or "forbidden" in lowered:
        return "permission_denied"
    if "rate limit" in lowered:
        return "rate_limited"
    if any(token in lowered for token in ("timed out", "timeout", "tls", "could not resolve")):
        return "transport_error"
    return "tooling_or_api_error"


def safe_error(exc: CommandFailure) -> dict[str, Any]:
    message = exc.stderr.splitlines()[-1] if exc.stderr else "command failed"
    return {
        "class": error_class(message),
        "command": list(exc.argv[:3]),
        "returncode": exc.returncode,
        "message": message[:500],
    }


def auth_probe(
    expected_login: str,
    actions_probe_repo: str,
    *,
    attempts: int = 3,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    delays = (0.0, 2.0, 5.0)
    records: list[dict[str, Any]] = []
    for attempt in range(1, attempts + 1):
        if attempt > 1:
            sleep_fn(delays[min(attempt - 1, len(delays) - 1)])
        record: dict[str, Any] = {"attempt": attempt, "errors": []}
        try:
            rest = run_json(["gh", "api", "user"])
            record["rest_login"] = rest.get("login") if isinstance(rest, dict) else None
        except CommandFailure as exc:
            record["errors"].append(safe_error(exc))
        try:
            graphql = run_json(
                [
                    "gh",
                    "api",
                    "graphql",
                    "-f",
                    "query={ viewer { login } }",
                ]
            )
            record["graphql_login"] = (
                graphql.get("data", {}).get("viewer", {}).get("login")
                if isinstance(graphql, dict)
                else None
            )
        except CommandFailure as exc:
            record["errors"].append(safe_error(exc))
        try:
            repos = run_json(
                ["gh", "api", "user/repos?affiliation=owner&per_page=1"]
            )
            record["owner_repo_read"] = isinstance(repos, list)
        except CommandFailure as exc:
            record["errors"].append(safe_error(exc))
        try:
            actions = run_json(
                ["gh", "api", f"repos/{actions_probe_repo}/actions/runs?per_page=1"]
            )
            record["actions_read"] = isinstance(actions, dict) and isinstance(
                actions.get("workflow_runs"), list
            )
        except CommandFailure as exc:
            record["errors"].append(safe_error(exc))

        record["valid"] = (
            not record["errors"]
            and record.get("rest_login") == expected_login
            and record.get("graphql_login") == expected_login
            and record.get("owner_repo_read") is True
            and record.get("actions_read") is True
        )
        records.append(record)
        if record["valid"]:
            return {
                "valid": True,
                "expected_login": expected_login,
                "authenticated_login": expected_login,
                "attempts": records,
                "credential_env_present": sorted(
                    name
                    for name in (
                        "GH_TOKEN",
                        "GITHUB_TOKEN",
                        "GH_ENTERPRISE_TOKEN",
                        "GITHUB_ENTERPRISE_TOKEN",
                        "GH_CONFIG_DIR",
                        "XDG_CONFIG_HOME",
                    )
                    if os.environ.get(name)
                ),
            }
    return {
        "valid": False,
        "expected_login": expected_login,
        "authenticated_login": records[-1].get("rest_login") if records else None,
        "attempts": records,
        "credential_env_present": sorted(
            name
            for name in (
                "GH_TOKEN",
                "GITHUB_TOKEN",
                "GH_ENTERPRISE_TOKEN",
                "GITHUB_ENTERPRISE_TOKEN",
                "GH_CONFIG_DIR",
                "XDG_CONFIG_HOME",
            )
            if os.environ.get(name)
        ),
    }


def repo_inventory(owner: str, selected_repos: list[str]) -> list[dict[str, Any]]:
    fields = (
        "nameWithOwner,defaultBranchRef,isArchived,isPrivate,hasIssuesEnabled,"
        "updatedAt,pushedAt,url"
    )
    if selected_repos:
        repos = [
            run_json(["gh", "repo", "view", repo, "--json", fields])
            for repo in selected_repos
        ]
    else:
        repos = run_json(
            ["gh", "repo", "list", owner, "--limit", "1000", "--json", fields]
        )
    if not isinstance(repos, list) or any(not isinstance(repo, dict) for repo in repos):
        raise CommandFailure(("gh", "repo", "list"), 65, "repository inventory is not a JSON array")
    return sorted(repos, key=lambda repo: str(repo.get("nameWithOwner", "")))


def flatten_pages(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    pages = value if value and all(isinstance(item, list) for item in value) else [value]
    return [item for page in pages for item in page if isinstance(item, dict)]


def paginated(endpoint: str) -> list[dict[str, Any]]:
    return flatten_pages(
        run_json(["gh", "api", "--paginate", "--slurp", endpoint])
    )


def body_digest(body: object) -> str:
    text = body if isinstance(body, str) else ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def latest_default_runs(runs: list[dict[str, Any]], default_branch: str) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for run in runs:
        if run.get("headBranch") != default_branch or run.get("event") == "pull_request":
            continue
        workflow = str(run.get("workflowName") or "")
        if workflow and workflow not in latest:
            latest[workflow] = run
    return [latest[name] for name in sorted(latest)]


def pr_snapshot(repo: str, item: dict[str, Any]) -> dict[str, Any]:
    head = item.get("head", {}) if isinstance(item.get("head"), dict) else {}
    base = item.get("base", {}) if isinstance(item.get("base"), dict) else {}
    head_sha = str(head.get("sha") or "")
    head_runs: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    if head_sha:
        head_runs_raw = run_json(
            [
                "gh",
                "run",
                "list",
                "--repo",
                repo,
                "--commit",
                head_sha,
                "--event",
                "pull_request",
                "--limit",
                "100",
                "--json",
                "databaseId,workflowName,status,conclusion,url,headSha,headBranch,event,createdAt,updatedAt",
            ]
        )
        head_runs = head_runs_raw if isinstance(head_runs_raw, list) else []
        check_payload = run_json(
            ["gh", "api", f"repos/{repo}/commits/{head_sha}/check-runs?per_page=100"]
        )
        raw_checks = check_payload.get("check_runs", []) if isinstance(check_payload, dict) else []
        checks = [
            {
                "id": check.get("id"),
                "name": check.get("name"),
                "status": check.get("status"),
                "conclusion": check.get("conclusion"),
                "details_url": check.get("details_url"),
            }
            for check in raw_checks
            if isinstance(check, dict)
        ]
    return {
        "number": item.get("number"),
        "url": item.get("html_url"),
        "title": item.get("title"),
        "author": (item.get("user") or {}).get("login") if isinstance(item.get("user"), dict) else None,
        "author_association": item.get("author_association"),
        "draft": item.get("draft"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "body_sha256": body_digest(item.get("body")),
        "base": {
            "ref": base.get("ref"),
            "sha": base.get("sha"),
            "repo": (base.get("repo") or {}).get("full_name")
            if isinstance(base.get("repo"), dict)
            else None,
        },
        "head": {
            "ref": head.get("ref"),
            "sha": head_sha,
            "repo": (head.get("repo") or {}).get("full_name")
            if isinstance(head.get("repo"), dict)
            else None,
        },
        "mergeable": item.get("mergeable"),
        "mergeable_state": item.get("mergeable_state"),
        "head_runs": sorted(head_runs, key=lambda run: int(run.get("databaseId") or 0), reverse=True),
        "check_runs": sorted(checks, key=lambda check: (str(check.get("name")), int(check.get("id") or 0))),
    }


def issue_snapshot(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "number": item.get("number"),
        "url": item.get("html_url"),
        "title": item.get("title"),
        "author": (item.get("user") or {}).get("login") if isinstance(item.get("user"), dict) else None,
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "body_sha256": body_digest(item.get("body")),
        "labels": sorted(
            str(label.get("name"))
            for label in item.get("labels", [])
            if isinstance(label, dict) and label.get("name")
        ),
    }


def collect_repo(repo: dict[str, Any], run_limit: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    name = str(repo.get("nameWithOwner") or "")
    default_ref = repo.get("defaultBranchRef") if isinstance(repo.get("defaultBranchRef"), dict) else {}
    default_branch = str(default_ref.get("name") or "")
    errors: list[dict[str, Any]] = []
    result: dict[str, Any] = {
        "name": name,
        "url": repo.get("url"),
        "archived": bool(repo.get("isArchived")),
        "private": bool(repo.get("isPrivate")),
        "issues_enabled": bool(repo.get("hasIssuesEnabled")),
        "default_branch": default_branch,
        "default_sha": None,
        "updated_at": repo.get("updatedAt"),
        "pushed_at": repo.get("pushedAt"),
        "latest_default_runs": [],
        "open_prs": [],
        "open_issues": [],
    }
    if result["archived"]:
        return result, errors

    def capture(surface: str, call: Callable[[], Any], fallback: Any) -> Any:
        try:
            return call()
        except CommandFailure as exc:
            errors.append({"repo": name, "surface": surface, **safe_error(exc)})
            return fallback

    if default_branch:
        commit = capture(
            "default_sha",
            lambda: run_json(["gh", "api", f"repos/{name}/commits/{default_branch}"]),
            {},
        )
        result["default_sha"] = commit.get("sha") if isinstance(commit, dict) else None
    runs = capture(
        "actions",
        lambda: run_json(
            [
                "gh",
                "run",
                "list",
                "--repo",
                name,
                "--limit",
                str(run_limit),
                "--json",
                "databaseId,workflowName,status,conclusion,url,headSha,headBranch,event,createdAt,updatedAt",
            ]
        ),
        [],
    )
    result["latest_default_runs"] = latest_default_runs(
        runs if isinstance(runs, list) else [], default_branch
    )
    pull_items = capture(
        "open_prs",
        lambda: paginated(f"repos/{name}/pulls?state=open&per_page=100"),
        [],
    )
    for item in pull_items:
        try:
            result["open_prs"].append(pr_snapshot(name, item))
        except CommandFailure as exc:
            errors.append(
                {
                    "repo": name,
                    "surface": f"pr_{item.get('number')}_head_evidence",
                    **safe_error(exc),
                }
            )
    result["open_prs"].sort(key=lambda item: int(item.get("number") or 0))
    if result["issues_enabled"]:
        issue_items = capture(
            "open_issues",
            lambda: paginated(f"repos/{name}/issues?state=open&per_page=100"),
            [],
        )
        result["open_issues"] = sorted(
            [issue_snapshot(item) for item in issue_items if "pull_request" not in item],
            key=lambda item: int(item.get("number") or 0),
        )
    return result, errors


def build_snapshot(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    auth = auth_probe(
        args.expected_login,
        args.actions_probe_repo,
        attempts=args.auth_attempts,
    )
    snapshot: dict[str, Any] = {
        "schema": SCHEMA,
        "observed_at": utc_now(),
        "owner": args.owner,
        "auth": auth,
        "repositories": [],
        "read_errors": [],
    }
    if not auth["valid"]:
        return snapshot, 2
    try:
        repos = repo_inventory(args.owner, args.repo)
    except CommandFailure as exc:
        snapshot["read_errors"].append({"surface": "repository_inventory", **safe_error(exc)})
        return snapshot, 3
    for repo in repos:
        value, errors = collect_repo(repo, args.run_limit)
        snapshot["repositories"].append(value)
        snapshot["read_errors"].extend(errors)
    snapshot["summary"] = {
        "repositories": len(snapshot["repositories"]),
        "active_repositories": sum(not repo["archived"] for repo in snapshot["repositories"]),
        "open_prs": sum(len(repo["open_prs"]) for repo in snapshot["repositories"]),
        "open_issues": sum(len(repo["open_issues"]) for repo in snapshot["repositories"]),
        "read_errors": len(snapshot["read_errors"]),
    }
    return snapshot, 3 if snapshot["read_errors"] else 0


def semantic_projection(snapshot: dict[str, Any]) -> dict[str, Any]:
    repositories: list[dict[str, Any]] = []
    for repo in snapshot.get("repositories", []):
        repositories.append(
            {
                "name": repo.get("name"),
                "archived": repo.get("archived"),
                "private": repo.get("private"),
                "issues_enabled": repo.get("issues_enabled"),
                "default_branch": repo.get("default_branch"),
                "default_sha": repo.get("default_sha"),
                "latest_default_runs": repo.get("latest_default_runs", []),
                "open_prs": repo.get("open_prs", []),
                "open_issues": repo.get("open_issues", []),
            }
        )
    return {
        "schema": snapshot.get("schema"),
        "owner": snapshot.get("owner"),
        "auth_valid": snapshot.get("auth", {}).get("valid"),
        "authenticated_login": snapshot.get("auth", {}).get("authenticated_login"),
        "repositories": repositories,
        "read_errors": snapshot.get("read_errors", []),
    }


def canonical_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compare_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_semantic = semantic_projection(before)
    after_semantic = semantic_projection(after)
    before_repos = {repo["name"]: repo for repo in before_semantic["repositories"]}
    after_repos = {repo["name"]: repo for repo in after_semantic["repositories"]}
    changed_repos = sorted(
        name
        for name in set(before_repos) | set(after_repos)
        if before_repos.get(name) != after_repos.get(name)
    )
    stable = before_semantic == after_semantic
    return {
        "schema": "opl.github_patrol_fold.v1",
        "stable": stable,
        "before_digest": canonical_digest(before_semantic),
        "after_digest": canonical_digest(after_semantic),
        "changed_repositories": changed_repos,
        "auth_changed": (
            before_semantic["auth_valid"], before_semantic["authenticated_login"]
        )
        != (after_semantic["auth_valid"], after_semantic["authenticated_login"]),
        "read_errors_changed": before_semantic["read_errors"] != after_semantic["read_errors"],
    }


def write_json(value: Any, output: str) -> None:
    payload = f"{json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True)}\n"
    if output == "-":
        sys.stdout.write(payload)
        return
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    auth = commands.add_parser("auth", help="run the bounded authenticated identity probe")
    auth.add_argument("--expected-login", required=True)
    auth.add_argument("--actions-probe-repo", required=True)
    auth.add_argument("--attempts", type=int, default=3, choices=(1, 2, 3))
    auth.add_argument("--output", default="-")

    snapshot = commands.add_parser("snapshot", help="write a normalized read-only patrol snapshot")
    snapshot.add_argument("--owner", required=True)
    snapshot.add_argument("--expected-login", required=True)
    snapshot.add_argument("--actions-probe-repo", required=True)
    snapshot.add_argument("--repo", action="append", default=[])
    snapshot.add_argument("--run-limit", type=int, default=20)
    snapshot.add_argument("--auth-attempts", type=int, default=3, choices=(1, 2, 3))
    snapshot.add_argument("--output", default="-")

    compare = commands.add_parser("compare", help="compare two normalized patrol snapshots")
    compare.add_argument("--before", required=True)
    compare.add_argument("--after", required=True)
    compare.add_argument("--output", default="-")
    return root


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "auth":
        result = auth_probe(
            args.expected_login,
            args.actions_probe_repo,
            attempts=args.attempts,
        )
        write_json(result, args.output)
        return 0 if result["valid"] else 2
    if args.command == "snapshot":
        result, code = build_snapshot(args)
        write_json(result, args.output)
        return code
    before = json.loads(Path(args.before).read_text(encoding="utf-8"))
    after = json.loads(Path(args.after).read_text(encoding="utf-8"))
    result = compare_snapshots(before, after)
    write_json(result, args.output)
    return 0 if result["stable"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
