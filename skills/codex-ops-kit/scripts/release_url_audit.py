#!/usr/bin/env python3
"""Audit public GitHub release URLs against the canonical remote and gh release truth."""

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


def run(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError as exc:
        return subprocess.CompletedProcess(cmd, 127, "", str(exc))


def canonical_slug(repo: Path) -> str:
    proc = run(["git", "-C", str(repo), "remote", "get-url", "origin"])
    if proc.returncode != 0:
        raise SystemExit(f"git remote get-url origin failed: {proc.stderr.strip()}")
    url = proc.stdout.strip()
    patterns = [
        r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$",
        r"https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return f"{match.group('owner')}/{match.group('repo')}"
    raise SystemExit(f"cannot derive GitHub owner/repo from origin URL: {url}")


def default_paths(repo: Path) -> list[Path]:
    candidates: list[Path] = []
    for pattern in ("README*", "docs/README*", ".github/*release*", "scripts/*install*", "install*"):
        candidates.extend(repo.glob(pattern))
    return sorted({path for path in candidates if path.is_file()})


def scan_urls(paths: list[Path]) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for match in RELEASE_URL.finditer(line):
                item = match.groupdict()
                item["path"] = str(path)
                item["line"] = str(lineno)
                item["url"] = match.group(0)
                hits.append(item)
    return hits


def gh_release(slug: str, tag: str | None) -> dict[str, Any] | None:
    args = ["gh", "release", "view", "--repo", slug, "--json", "tagName,assets,url"] if not tag else [
        "gh",
        "release",
        "view",
        tag,
        "--repo",
        slug,
        "--json",
        "tagName,assets,url",
    ]
    proc = run(args)
    if proc.returncode != 0:
        return {"error": proc.stderr.strip(), "command": " ".join(shlex.quote(arg) for arg in args)}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {"error": f"invalid gh JSON: {exc}", "raw": proc.stdout}


def run_exact_command(command: str, repo: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="release-install-home-") as home:
        env = os.environ.copy()
        env.update(
            {
                "HOME": home,
                "XDG_CACHE_HOME": str(Path(home) / ".cache"),
                "XDG_CONFIG_HOME": str(Path(home) / ".config"),
                "XDG_DATA_HOME": str(Path(home) / ".local" / "share"),
            }
        )
        proc = subprocess.run(command, shell=True, cwd=str(repo), env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return {
            "command": command,
            "temporary_home_prefix": "release-install-home-",
            "exit_code": proc.returncode,
            "stdout_tail": proc.stdout[-4000:],
            "stderr_tail": proc.stderr[-4000:],
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--paths", nargs="*", help="Files to scan. Defaults to README, release, and installer surfaces.")
    parser.add_argument("--tag", help="Release tag to check. Defaults to the first scanned tag or latest gh release.")
    parser.add_argument("--command", help="Exact public install command to run in a temporary HOME.")
    parser.add_argument("--run-command", action="store_true", help="Actually execute --command.")
    args = parser.parse_args(argv)

    repo = Path(args.repo).expanduser().resolve()
    slug = canonical_slug(repo)
    paths = [Path(path) if Path(path).is_absolute() else repo / path for path in args.paths] if args.paths else default_paths(repo)
    hits = scan_urls(paths)
    scanned_tags = sorted({hit["tag"] for hit in hits})
    tag = args.tag or (scanned_tags[0] if len(scanned_tags) == 1 else None)
    gh = gh_release(slug, tag)
    gh_assets = set()
    gh_tag = None
    if isinstance(gh, dict) and not gh.get("error"):
        gh_tag = gh.get("tagName")
        for asset in gh.get("assets", []) or []:
            if isinstance(asset, dict) and asset.get("name"):
                gh_assets.add(asset["name"])

    mismatches: list[dict[str, str]] = []
    owner, repo_name = slug.split("/", 1)
    for hit in hits:
        if hit["owner"] != owner or hit["repo"] != repo_name:
            mismatches.append({**hit, "reason": f"URL repo {hit['owner']}/{hit['repo']} != canonical {slug}"})
        if gh_tag and hit["tag"] != gh_tag:
            mismatches.append({**hit, "reason": f"URL tag {hit['tag']} != gh release tag {gh_tag}"})
        if gh_assets and hit["asset"] not in gh_assets:
            mismatches.append({**hit, "reason": f"asset {hit['asset']} not found in gh release assets"})

    command_result = None
    if args.command and args.run_command:
        command_result = run_exact_command(args.command, repo)

    report = {
        "canonical_repo": slug,
        "scanned_files": [str(path) for path in paths],
        "release_urls": hits,
        "scanned_tags": scanned_tags,
        "gh_release": gh,
        "mismatches": mismatches,
        "exact_command_checked": bool(args.command and args.run_command),
        "command_result": command_result,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if mismatches:
        return 2
    if args.command and args.run_command and command_result and command_result["exit_code"] != 0:
        return command_result["exit_code"] or 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
