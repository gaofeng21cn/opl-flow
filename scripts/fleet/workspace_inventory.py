"""Read-only discovery of checkouts; discovery never grants maintenance custody."""
from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit


PRUNED_NAMES = frozenset({
    ".git", ".codegraph", ".venv", "venv", "node_modules", "__pycache__",
    ".build", "build", "dist", "target", ".cache", ".next", "DerivedData",
    "models", "model_cache",
})


def repository_identity(remote: str) -> str | None:
    """Normalize remote transport without retaining credentials, query or fragment."""
    value = remote.strip()
    if not value:
        return None
    if "://" not in value and re.match(r"^[^/]+@[^/:]+:", value):
        value = "ssh://" + value.replace(":", "/", 1)
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").casefold()
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme in {"https", "http", "ssh", "git"} and host:
        if host == "ssh.github.com" and port == 443:
            host, port = "github.com", None
        if port in {None, {"https": 443, "http": 80, "ssh": 22, "git": 9418}[parsed.scheme]}:
            port = None
        path = parsed.path.strip("/").removesuffix(".git")
        if not path or any(part in {"", ".", ".."} for part in path.split("/")):
            return None
        identity = f"{host}{':' + str(port) if port else ''}/{path}"
        return identity.casefold() if host == "github.com" else identity
    if not parsed.scheme and value.startswith(("/", "./", "../", "~")):
        return "local:" + str(Path(value).expanduser().absolute())
    return None


def _git(path: Path, *arguments: str) -> str:
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"}
    result = subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-C", str(path), *arguments],
        capture_output=True, text=True, timeout=20, env=env,
    )
    if result.returncode:
        # Git stderr can contain remote credentials. Keep failure identity only.
        raise ValueError("git_read_failed")
    return result.stdout.strip()


def _redirected(path: Path) -> bool:
    return any(part.is_symlink() for part in (path, *path.parents))


def discover_checkouts(roots: list[Path], *, max_depth: int = 5) -> tuple[list[Path], list[dict]]:
    if not 0 <= max_depth <= 20:
        raise ValueError("max_depth must be between 0 and 20")
    found, seen, issues = set(), {}, []
    for source in roots:
        root = Path(os.path.abspath(source.expanduser()))
        if _redirected(root):
            issues.append({"path": str(root), "state": "SKIPPED_SYMLINK"})
            continue
        if not root.is_dir():
            issues.append({"path": str(root), "state": "MISSING_ROOT"})
            continue
        try:
            device = root.stat().st_dev
        except OSError as exc:
            issues.append({"path": str(root), "state": "READ_FAILED", "reason": type(exc).__name__})
            continue
        pending = [(root, 0)]
        while pending:
            path, depth = pending.pop()
            remaining = max_depth - depth
            if seen.get(path, -1) >= remaining:
                continue
            seen[path] = remaining
            try:
                with os.scandir(path) as entries:
                    children = list(entries)
                if any(entry.name == ".git" for entry in children):
                    found.add(path)
                    continue
                if depth == max_depth:
                    continue
                for entry in children:
                    if entry.name in PRUNED_NAMES or entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False) and entry.stat(follow_symlinks=False).st_dev == device:
                        pending.append((Path(entry.path), depth + 1))
            except OSError as exc:
                issues.append({"path": str(path), "state": "READ_FAILED", "reason": type(exc).__name__})
    return sorted(found), issues


def _checkout(path: Path, *, include_size: bool) -> dict:
    record = {"path": str(path)}
    try:
        if (path / ".git").is_symlink():
            raise ValueError("redirected_git_marker")
        if Path(_git(path, "rev-parse", "--show-toplevel")).resolve() != path.resolve():
            raise ValueError("not_a_checkout_root")
        common = Path(_git(path, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()
        git_dir = Path(_git(path, "rev-parse", "--path-format=absolute", "--git-dir")).resolve()
        try:
            remote = _git(path, "remote", "get-url", "origin")
        except ValueError:
            remote = ""
        dirty = bool(_git(path, "status", "--porcelain", "--untracked-files=normal"))
        record.update(
            state="DIRTY" if dirty else "CLEAN", head=_git(path, "rev-parse", "HEAD"),
            branch=_git(path, "branch", "--show-current") or None,
            repository=repository_identity(str((path / remote).resolve()) if remote.startswith(("./", "../")) else remote), common_dir=str(common),
            linked_worktree=git_dir != common,
        )
        if include_size:
            result = subprocess.run(["du", "-s", "-k", "-x", str(path)], capture_output=True, text=True, timeout=180)
            if result.returncode:
                record["size_state"] = "READ_FAILED"
            else:
                record.update(allocated_bytes=int(result.stdout.split("\t", 1)[0]) * 1024, size_state="MEASURED")
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        record.update(state="READ_FAILED", reason=type(exc).__name__)
    return record


def inventory(
    roots: list[Path], *, managed: dict[str, str] | None = None,
    custody: dict[str, dict] | None = None, include_size: bool = False, max_depth: int = 5,
) -> dict:
    """Report independent clones separately from linked worktrees, without fetch."""
    managed = managed or {}
    custody = custody or {}
    paths, issues = discover_checkouts(roots, max_depth=max_depth)
    with ThreadPoolExecutor(max_workers=6) as pool:
        records = list(pool.map(lambda p: _checkout(p, include_size=include_size), paths))
    by_identity = defaultdict(list)
    for record in records:
        path = record["path"]
        expected = managed.get(path)
        record["declared_repository"] = expected
        record["classification"] = (
            "MANAGED_PRIMARY" if expected else
            "LINKED_WORKTREE" if record.get("linked_worktree") else "UNREGISTERED_CHECKOUT"
        )
        if expected and record.get("repository") != repository_identity("https://github.com/" + expected):
            record["state"] = "REMOTE_MISMATCH" if record["state"] != "READ_FAILED" else record["state"]
        if path in custody:
            # A receipt identifies custody, not proof of live execution.
            record["custody"] = {k: custody[path].get(k) for k in (
                "custody_thread_id", "custody_owner", "objective_ref", "status",
            )}
        if record.get("repository") and record.get("common_dir"):
            by_identity[record["repository"]].append(record)
    duplicates = []
    for identity, rows in sorted(by_identity.items()):
        commons = sorted({r["common_dir"] for r in rows})
        if len(commons) > 1:
            duplicates.append({"repository": identity, "common_directories": commons,
                               "checkouts": [r["path"] for r in rows]})
    discovered = {r["path"] for r in records}
    missing, unscanned = [], []
    for p, repo in sorted(managed.items()):
        if p not in discovered:
            target = unscanned if (Path(p) / ".git").exists() else missing
            target.append({"path": p, "repository": repo})
    complete = not any(r["state"] == "READ_FAILED" or r.get("size_state") == "READ_FAILED" for r in records)
    complete = complete and not issues
    return {
        "schema": "opl_workspace_inventory.v1", "recorded_at": datetime.now(timezone.utc).isoformat(),
        "scan_roots": [str(p) for p in roots], "max_depth": max_depth,
        "checkouts": records, "duplicate_clones": duplicates, "missing_declared": missing,
        "unscanned_declared": unscanned, "issues": issues, "complete": complete,
        "summary": {
            "checkouts": len(records), "managed_primary": sum(bool(r["declared_repository"]) for r in records),
            "linked_worktrees": sum(bool(r.get("linked_worktree")) for r in records),
            "independent_clone_groups": len(duplicates), "missing_declared": len(missing),
        },
        "size_note": "Directory allocations can overlap through hard links or APFS clones; they are not reclaimable-space estimates.",
    }
