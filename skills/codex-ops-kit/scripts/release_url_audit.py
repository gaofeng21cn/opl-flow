#!/usr/bin/env python3
"""Bind public GitHub release URLs and install commands to live release truth."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Any


RELEASE_URL = re.compile(
    r"https://github\.com/(?P<owner>[^/\s\"')]+)/(?P<repo>[^/\s\"')]+)/releases/download/(?P<tag>[^/\s\"')]+)/(?P<asset>[^\s\"')]+)"
)


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError as exc:
        return subprocess.CompletedProcess(cmd, 127, "", str(exc))


def canonical_slug(repo: Path) -> tuple[str | None, str | None]:
    result = run(["git", "-C", str(repo), "remote", "get-url", "origin"])
    if result.returncode != 0:
        return None, result.stderr.strip() or "git remote get-url origin failed"
    match = re.search(r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$", result.stdout.strip())
    if not match:
        return None, f"cannot derive GitHub owner/repo from origin URL: {result.stdout.strip()}"
    return f"{match.group('owner')}/{match.group('repo')}", None


def default_paths(repo: Path) -> list[Path]:
    candidates: list[Path] = []
    for pattern in ("README*", "docs/README*", ".github/*release*", "scripts/*install*", "install*"):
        candidates.extend(repo.glob(pattern))
    return sorted({path for path in candidates if path.is_file()})


def scan_urls(paths: list[Path]) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line_number, line in enumerate(text.splitlines(), start=1):
            for match in RELEASE_URL.finditer(line):
                hit = match.groupdict()
                hit.update(path=str(path), line=str(line_number), url=match.group(0))
                hits.append(hit)
    return hits


def read_release(slug: str, tag: str | None) -> dict[str, Any]:
    command = ["gh", "release", "view"]
    if tag:
        command.append(tag)
    command.extend(["--repo", slug, "--json", "tagName,assets,url"])
    result = run(command)
    rendered = " ".join(shlex.quote(part) for part in command)
    if result.returncode != 0:
        return {"command": rendered, "error": result.stderr.strip() or f"exit {result.returncode}"}
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return {"command": rendered, "error": f"invalid gh JSON: {exc}"}
    payload["command"] = rendered
    return payload


def run_install_command(command: str, repo: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="release-install-home-") as home:
        env = os.environ.copy()
        env.update(
            HOME=home,
            XDG_CACHE_HOME=str(Path(home) / ".cache"),
            XDG_CONFIG_HOME=str(Path(home) / ".config"),
            XDG_DATA_HOME=str(Path(home) / ".local" / "share"),
        )
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(repo),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return {
            "command": command,
            "exit_code": result.returncode,
            "stdout_tail": result.stdout[-4000:],
            "stderr_tail": result.stderr[-4000:],
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--paths", nargs="*", help="Files to scan. Defaults to README, release, and installer surfaces.")
    parser.add_argument("--tag", help="Explicit release tag. Otherwise every scanned tag is checked.")
    parser.add_argument("--command", help="Exact public install command to run in a temporary HOME.")
    parser.add_argument("--run-command", action="store_true")
    args = parser.parse_args(argv)

    repo = Path(args.repo).expanduser().resolve()
    slug, slug_error = canonical_slug(repo)
    paths = (
        [Path(path) if Path(path).is_absolute() else repo / path for path in args.paths]
        if args.paths is not None
        else default_paths(repo)
    )
    hits = scan_urls(paths)
    tags = [args.tag] if args.tag else sorted({hit["tag"] for hit in hits})
    release_keys: list[str | None] = tags or [None]
    releases = {(tag or "latest"): read_release(slug, tag) for tag in release_keys} if slug else {}
    errors = [slug_error] if slug_error else []
    if args.paths is not None:
        errors.extend(f"scan path is not a file: {path}" for path in paths if not path.is_file())
    if args.command and not args.run_command:
        errors.append("--command requires --run-command")
    if args.run_command and not args.command:
        errors.append("--run-command requires --command")
    errors.extend(str(payload["error"]) for payload in releases.values() if payload.get("error"))

    mismatches: list[dict[str, str]] = []
    if slug:
        owner, repo_name = slug.split("/", 1)
        for hit in hits:
            if (hit["owner"], hit["repo"]) != (owner, repo_name):
                mismatches.append({**hit, "reason": f"URL repo {hit['owner']}/{hit['repo']} != canonical {slug}"})
                continue
            release = releases.get(hit["tag"], {})
            if release.get("error"):
                continue
            if release.get("tagName") != hit["tag"]:
                mismatches.append({**hit, "reason": f"gh release tag {release.get('tagName')} != URL tag {hit['tag']}"})
            assets = {asset.get("name") for asset in release.get("assets", []) if isinstance(asset, dict)}
            if hit["asset"] not in assets:
                mismatches.append({**hit, "reason": f"asset {hit['asset']} not found in gh release assets"})

    command_result = run_install_command(args.command, repo) if args.command and args.run_command else None
    if command_result and command_result["exit_code"] != 0:
        errors.append(f"install command failed with exit {command_result['exit_code']}")

    ok = not errors and not mismatches
    report = {
        "ok": ok,
        "canonical_repo": slug,
        "scanned_files": [str(path) for path in paths],
        "release_urls": hits,
        "gh_releases": releases,
        "mismatches": mismatches,
        "errors": errors,
        "exact_command_checked": bool(command_result),
        "command_result": command_result,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
