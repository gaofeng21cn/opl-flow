#!/usr/bin/env python3
"""Prepare, publish, and activate one first-party OPL Package."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


class ReleaseError(RuntimeError):
    pass


def command(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    input_text: str | None = None,
    timeout: int = 600,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            list(argv),
            cwd=cwd,
            input=input_text,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ReleaseError(f"command not found: {argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ReleaseError(f"command timed out after {timeout}s: {' '.join(argv)}") from exc
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "no output"
        raise ReleaseError(f"command failed ({result.returncode}): {' '.join(argv)}: {detail}")
    return result


def command_json(argv: Sequence[str], *, cwd: Path | None = None, timeout: int = 600) -> Any:
    output = command(argv, cwd=cwd, timeout=timeout).stdout.strip()
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise ReleaseError(f"command returned invalid JSON: {' '.join(argv)}") from exc


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseError(f"cannot read JSON object: {path}") from exc
    if not isinstance(value, dict):
        raise ReleaseError(f"JSON root must be an object: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def git_value(root: Path, *args: str) -> str:
    return command(["git", *args], cwd=root).stdout.strip()


def repo_slug(root: Path) -> str:
    remote = git_value(root, "remote", "get-url", "origin")
    match = re.fullmatch(
        r"(?:https?://github\.com/|git@github\.com:|"
        r"ssh://git@(?:ssh\.)?github\.com(?::\d+)?/)"
        r"([^/]+)/([^/]+?)(?:\.git)?",
        remote,
    )
    if not match:
        raise ReleaseError(f"origin is not a canonical GitHub repository: {remote}")
    return f"{match.group(1)}/{match.group(2)}"


def require_owner_release(owner_root: Path, package_id: str) -> tuple[dict[str, Any], str, str]:
    manifest = read_json(owner_root / "opl-package.json")
    version = str(manifest.get("version") or "")
    if manifest.get("package_id") != package_id or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ReleaseError("owner opl-package.json has an invalid package id or stable SemVer")
    if git_value(owner_root, "status", "--porcelain"):
        raise ReleaseError("owner checkout must be clean before projection")
    command(["git", "fetch", "origin", "main", "--tags", "--quiet"], cwd=owner_root)
    source_commit = git_value(owner_root, "rev-parse", "HEAD")
    if source_commit != git_value(owner_root, "rev-parse", "origin/main"):
        raise ReleaseError("owner HEAD must equal fresh origin/main")
    tag = f"v{version}"
    if git_value(owner_root, "cat-file", "-t", f"refs/tags/{tag}") != "tag":
        raise ReleaseError(f"owner release tag must be annotated: {tag}")
    if git_value(owner_root, "rev-parse", f"{tag}^{{}}") != source_commit:
        raise ReleaseError(f"owner release tag does not select HEAD: {tag}")
    return manifest, version, source_commit


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    owner_root = Path(args.owner_root).resolve()
    framework_root = Path(args.framework_root).resolve()
    owner_manifest, version, source_commit = require_owner_release(
        owner_root, args.package_id
    )
    expected_repo = str(owner_manifest.get("source_repo") or "")
    if expected_repo.removesuffix(".git") != f"https://github.com/{repo_slug(owner_root)}":
        raise ReleaseError("owner source_repo does not match origin")

    package_path = framework_root / "contracts/opl-framework/packages" / f"{args.package_id}.json"
    allowlist_path = (
        framework_root
        / "contracts/opl-framework/package-payload-allowlists"
        / f"{args.package_id}.json"
    )
    catalog_path = framework_root / "contracts/opl-framework/bundled-full-runtime-package-catalog.json"
    package = read_json(package_path)
    codex_surface = package.get("codex_surface")
    if package.get("package_id") != args.package_id or not isinstance(codex_surface, dict):
        raise ReleaseError("Framework package projection has an invalid identity")
    payload_ref = f"payloads/{args.package_id}-{version}.json"
    package["version"] = version
    codex_surface["plugin_payload_manifest_url"] = payload_ref
    codex_surface["carrier_source_commit"] = source_commit
    write_json(package_path, package)

    with tempfile.TemporaryDirectory(prefix="opl-package-cohort-") as temporary:
        cohort_path = Path(temporary) / "owner-cohort-lock.json"
        write_json(
            cohort_path,
            {
                "surface_kind": "opl_package_owner_cohort_lock.v1",
                "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "packages": {
                    args.package_id: {
                        "package_id": args.package_id,
                        "repo_name": repo_slug(owner_root).split("/", 1)[1],
                        "repo_url": expected_repo,
                        "source_commit": source_commit,
                    }
                },
            },
        )
        command(
            [
                "node",
                str(framework_root / "scripts/first-party-package-payload.mjs"),
                "--manifest",
                str(package_path),
                "--allowlist",
                str(allowlist_path),
                "--owner-cohort-lock",
                str(cohort_path),
                "--repo",
                str(owner_root),
                "--source-commit",
                source_commit,
            ],
            cwd=framework_root,
        )

    payload_path = package_path.parent / payload_ref
    catalog = read_json(catalog_path)
    packages = catalog.get("packages")
    entry = packages.get(args.package_id) if isinstance(packages, dict) else None
    if not isinstance(entry, dict):
        raise ReleaseError("Framework bundled catalog has no matching Package entry")
    entry.update(
        package_version=version,
        owner_source_commit=source_commit,
        manifest_sha256=sha256_bytes(package_path.read_bytes()),
        payload_manifest_ref=f"packages/{payload_ref}",
        payload_manifest_sha256=sha256_bytes(payload_path.read_bytes()),
    )
    write_json(catalog_path, catalog)
    return {
        "action": "prepare",
        "status": "projection_ready",
        "package_id": args.package_id,
        "version": version,
        "owner_source_commit": source_commit,
        "updated_files": [
            str(package_path),
            str(payload_path),
            str(catalog_path),
        ],
    }


def oci_descriptor(ref: str) -> dict[str, Any]:
    value = command_json(["oras", "manifest", "fetch", "--descriptor", ref], timeout=120)
    if not isinstance(value, dict) or not re.fullmatch(r"sha256:[0-9a-f]{64}", str(value.get("digest") or "")):
        raise ReleaseError(f"OCI descriptor has no valid digest: {ref}")
    return value


def latest_stable_predecessor(image: str) -> str:
    ref = f"{image}:latest-stable"
    result = command(
        ["oras", "manifest", "fetch", "--descriptor", ref],
        timeout=120,
        check=False,
    )
    if result.returncode == 0:
        try:
            value = json.loads(result.stdout)
            digest = str(value.get("digest") or "")
        except (json.JSONDecodeError, AttributeError) as exc:
            raise ReleaseError(f"latest-stable descriptor is invalid: {ref}") from exc
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise ReleaseError(f"latest-stable descriptor has no valid digest: {ref}")
        return digest
    lowered = f"{result.stdout}\n{result.stderr}".lower()
    if any(token in lowered for token in ("manifest unknown", "name unknown", "not found", "404")):
        return "none"
    raise ReleaseError(f"cannot read latest-stable predecessor: {ref}")


def run_id_from_dispatch(output: str) -> int | None:
    match = re.search(r"/actions/runs/(\d+)", output)
    return int(match.group(1)) if match else None


def find_run_id(repo: str, request_id: str, framework_commit: str) -> int | None:
    runs = command_json(
        [
            "gh",
            "run",
            "list",
            "--repo",
            repo,
            "--workflow",
            "publish-package.yml",
            "--branch",
            "main",
            "--limit",
            "20",
            "--json",
            "databaseId,displayTitle,headSha",
        ]
    )
    if not isinstance(runs, list):
        return None
    matches = [
        item
        for item in runs
        if isinstance(item, dict)
        and request_id in str(item.get("displayTitle") or "")
        and item.get("headSha") == framework_commit
    ]
    if len(matches) > 1:
        raise ReleaseError("publication request id matched more than one workflow run")
    return int(matches[0]["databaseId"]) if matches else None


def wait_for_run_id(repo: str, request_id: str, framework_commit: str) -> int:
    for _ in range(30):
        run_id = find_run_id(repo, request_id, framework_commit)
        if run_id is not None:
            return run_id
        time.sleep(2)
    raise ReleaseError("dispatched publication run did not become visible")


def validate_receipt(
    receipt: dict[str, Any],
    *,
    package_id: str,
    version: str,
    owner_commit: str,
    framework_commit: str,
    request_id: str,
) -> str:
    package = receipt.get("package")
    immutable = receipt.get("immutable")
    latest = receipt.get("latest_stable")
    attestations = receipt.get("attestations")
    if (
        receipt.get("status") != "published_and_verified"
        or receipt.get("publication_request_id") != request_id
        or not isinstance(package, dict)
        or package.get("package_id") != package_id
        or package.get("version") != version
        or package.get("owner_source_commit") != owner_commit
        or package.get("framework_source_commit") != framework_commit
        or not isinstance(immutable, dict)
        or not isinstance(latest, dict)
        or immutable.get("digest") != latest.get("digest")
        or not isinstance(attestations, dict)
        or attestations.get("status") != "verified"
    ):
        raise ReleaseError("publication receipt does not match the requested release")
    digest = str(immutable.get("digest") or "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ReleaseError("publication receipt has an invalid digest")
    return digest


def seconds_between(start: str, end: str) -> float:
    def parsed(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    return round((parsed(end) - parsed(start)).total_seconds(), 3)


def publish(args: argparse.Namespace) -> dict[str, Any]:
    framework_root = Path(args.framework_root).resolve()
    command(["git", "fetch", "origin", "main", "--quiet"], cwd=framework_root)
    framework_commit = git_value(framework_root, "rev-parse", "HEAD")
    if framework_commit != git_value(framework_root, "rev-parse", "origin/main"):
        raise ReleaseError("Framework HEAD must equal fresh origin/main")
    if git_value(framework_root, "status", "--porcelain"):
        raise ReleaseError("Framework checkout must be clean before publication")
    package = read_json(
        framework_root / "contracts/opl-framework/packages" / f"{args.package_id}.json"
    )
    codex_surface = package.get("codex_surface")
    if not isinstance(codex_surface, dict):
        raise ReleaseError("Framework package projection has no codex_surface")
    version = str(package.get("version") or "")
    owner_commit = str(codex_surface.get("carrier_source_commit") or "")
    carrier = codex_surface.get("configured_codex_plugin_carrier")
    publication_ref = carrier.get("publication_ref") if isinstance(carrier, dict) else None
    if not isinstance(publication_ref, str) or not publication_ref.endswith(":latest-stable"):
        raise ReleaseError("Framework Package has no latest-stable publication_ref")
    image = publication_ref.removesuffix(":latest-stable")
    predecessor = latest_stable_predecessor(image)
    request_id = args.request_id or (
        f"{args.package_id}-{version}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-"
        f"{framework_commit[:10]}"
    )
    repo = repo_slug(framework_root)
    dispatch_args = [
        "gh",
        "workflow",
        "run",
        "publish-package.yml",
        "--repo",
        repo,
        "--ref",
        "main",
        "-f",
        f"package_id={args.package_id}",
        "-f",
        f"expected_package_version={version}",
        "-f",
        f"expected_owner_source_commit={owner_commit}",
        "-f",
        f"expected_framework_source_commit={framework_commit}",
        "-f",
        f"expected_latest_stable_predecessor={predecessor}",
        "-f",
        f"publication_request_id={request_id}",
    ]
    dispatched = command(dispatch_args, check=False)
    combined_output = f"{dispatched.stdout}\n{dispatched.stderr}"
    run_id = run_id_from_dispatch(combined_output)
    if dispatched.returncode != 0:
        run_id = find_run_id(repo, request_id, framework_commit)
        if run_id is None:
            raise ReleaseError("publication dispatch failed and no matching run exists")
    if run_id is None:
        run_id = wait_for_run_id(repo, request_id, framework_commit)
    sys.stderr.write(f"Watching Package publication run {run_id}\n")
    watched = subprocess.run(
        [
            "gh",
            "run",
            "watch",
            str(run_id),
            "--repo",
            repo,
            "--compact",
            "--exit-status",
            "--interval",
            "5",
        ],
        text=True,
        stdout=sys.stderr,
        stderr=sys.stderr,
        check=False,
    )
    if watched.returncode != 0:
        raise ReleaseError(f"publication workflow failed: {run_id}")

    run = command_json(
        [
            "gh",
            "run",
            "view",
            str(run_id),
            "--repo",
            repo,
            "--json",
            "jobs,createdAt,updatedAt,conclusion,url,headSha",
        ]
    )
    if not isinstance(run, dict) or run.get("conclusion") != "success":
        raise ReleaseError("publication workflow did not finish successfully")
    with tempfile.TemporaryDirectory(prefix="opl-package-receipt-") as temporary:
        command(
            ["gh", "run", "download", str(run_id), "--repo", repo, "--dir", temporary]
        )
        receipts = list(Path(temporary).rglob("publication-receipt.json"))
        if len(receipts) != 1:
            raise ReleaseError("publication workflow did not expose one receipt")
        receipt = read_json(receipts[0])
    digest = validate_receipt(
        receipt,
        package_id=args.package_id,
        version=version,
        owner_commit=owner_commit,
        framework_commit=framework_commit,
        request_id=request_id,
    )
    immutable_ref = str(receipt["immutable"]["ref"])
    latest_ref = str(receipt["latest_stable"]["ref"])
    if oci_descriptor(immutable_ref)["digest"] != digest:
        raise ReleaseError("immutable OCI readback digest differs from receipt")
    if oci_descriptor(latest_ref)["digest"] != digest:
        raise ReleaseError("latest-stable OCI readback digest differs from receipt")
    attestation = receipt["attestations"]
    for predicate_type in ("slsaprovenance1", "spdxjson"):
        command(
            [
                "cosign",
                "verify-attestation",
                "--type",
                predicate_type,
                "--certificate-identity",
                str(attestation["certificate_identity"]),
                "--certificate-oidc-issuer",
                "https://token.actions.githubusercontent.com",
                str(attestation["subject"]),
            ],
            timeout=120,
        )
    jobs = run.get("jobs") if isinstance(run.get("jobs"), list) else []
    job = jobs[0] if jobs and isinstance(jobs[0], dict) else {}
    timings = {
        "total_seconds": seconds_between(str(run["createdAt"]), str(run["updatedAt"])),
        "queue_seconds": seconds_between(str(run["createdAt"]), str(job["startedAt"])),
        "job_seconds": seconds_between(str(job["startedAt"]), str(job["completedAt"])),
    } if job.get("startedAt") and job.get("completedAt") else {}
    return {
        "action": "publish",
        "status": "published_and_verified",
        "package_id": args.package_id,
        "version": version,
        "owner_source_commit": owner_commit,
        "framework_source_commit": framework_commit,
        "publication_request_id": request_id,
        "run_id": run_id,
        "run_url": run.get("url"),
        "digest": digest,
        "latest_stable_predecessor": predecessor,
        "timings": timings,
    }


def plugin_entry(selector: str, codex_bin: str) -> dict[str, Any] | None:
    readback = command_json([codex_bin, "plugin", "list", "--json"], timeout=120)
    installed = readback.get("installed") if isinstance(readback, dict) else None
    if not isinstance(installed, list):
        raise ReleaseError("Codex plugin list has no installed array")
    matches = [item for item in installed if isinstance(item, dict) and item.get("pluginId") == selector]
    if len(matches) > 1:
        raise ReleaseError(f"Codex reports duplicate configured plugin selector: {selector}")
    return matches[0] if matches else None


def installed_profile(entry: dict[str, Any] | None) -> tuple[str | None, bytes | None]:
    source = entry.get("source") if isinstance(entry, dict) else None
    source_path = source.get("path") if isinstance(source, dict) else None
    if not isinstance(source_path, str):
        return None, None
    root = Path(source_path)
    descriptor = read_json(root / "opl-package.json")
    profile = descriptor.get("profile_surface")
    runtime = profile.get("runtime_profile") if isinstance(profile, dict) else None
    relative = runtime.get("source_path") if isinstance(runtime, dict) else None
    if not isinstance(relative, str):
        return None, None
    path = root / relative
    return str(path), path.read_bytes()


def profile_delta(
    before: tuple[str | None, bytes | None],
    after: tuple[str | None, bytes | None],
    user_path: Path,
) -> dict[str, Any]:
    before_path, before_bytes = before
    after_path, after_bytes = after
    user_bytes = user_path.read_bytes() if user_path.is_file() else None
    changed = before_bytes != after_bytes
    merge_required = changed and user_bytes != after_bytes
    diff = ""
    if changed and before_bytes is not None and after_bytes is not None:
        diff = "".join(
            difflib.unified_diff(
                before_bytes.decode("utf-8").splitlines(keepends=True),
                after_bytes.decode("utf-8").splitlines(keepends=True),
                fromfile=before_path or "previous-default",
                tofile=after_path or "current-default",
            )
        )
    status = (
        "profile_merge_required"
        if merge_required
        else "current"
        if user_bytes == after_bytes
        else "default_profile_unchanged"
    )
    return {
        "status": status,
        "profile_merge_required": merge_required,
        "user_profile_path": str(user_path),
        "user_profile_sha256": sha256_bytes(user_bytes) if user_bytes is not None else None,
        "previous_default_sha256": sha256_bytes(before_bytes) if before_bytes is not None else None,
        "current_default_sha256": sha256_bytes(after_bytes) if after_bytes is not None else None,
        "default_profile_changed": changed,
        "default_profile_diff": diff or None,
        "automatic_write_performed": False,
    }


def activate(args: argparse.Namespace) -> dict[str, Any]:
    framework_root = Path(args.framework_root).resolve()
    package = read_json(
        framework_root / "contracts/opl-framework/packages" / f"{args.package_id}.json"
    )
    codex_surface = package.get("codex_surface")
    carrier = codex_surface.get("configured_codex_plugin_carrier") if isinstance(codex_surface, dict) else None
    selector = carrier.get("plugin_selector") if isinstance(carrier, dict) else None
    required_skills = codex_surface.get("required_skill_ids") if isinstance(codex_surface, dict) else None
    if not isinstance(selector, str) or "@" not in selector or not isinstance(required_skills, list):
        raise ReleaseError("Framework Package has no configured Codex plugin selector")
    expected_version = str(package.get("version") or "")
    before_entry = plugin_entry(selector, args.codex_bin)
    before_profile = installed_profile(before_entry)
    update = command_json(
        [args.opl_bin, "packages", "update", args.package_id, "--json"],
        timeout=args.timeout,
    )
    after_entry = plugin_entry(selector, args.codex_bin)
    if (
        not after_entry
        or after_entry.get("version") != expected_version
        or after_entry.get("enabled") is not True
    ):
        raise ReleaseError("installed Codex Plugin did not reach the expected enabled version")
    source = after_entry.get("source")
    source_path = Path(str(source.get("path"))) if isinstance(source, dict) else None
    missing_skills = [
        skill_id
        for skill_id in required_skills
        if not isinstance(skill_id, str)
        or source_path is None
        or not (source_path / "skills" / skill_id / "SKILL.md").is_file()
    ]
    if missing_skills:
        raise ReleaseError(f"installed Plugin is missing required Skills: {missing_skills}")
    status = command_json(
        [args.opl_bin, "packages", "status", "--package-id", args.package_id, "--json"],
        timeout=args.timeout,
    )
    user_profile = Path(args.user_profile).expanduser().resolve()
    profile = profile_delta(before_profile, installed_profile(after_entry), user_profile)
    return {
        "action": "activate",
        "status": "installed_and_read_back",
        "package_id": args.package_id,
        "version": expected_version,
        "plugin_selector": selector,
        "package_update": update,
        "package_status": status,
        "required_skill_ids": required_skills,
        "missing_skill_ids": missing_skills,
        "profile": profile,
        "fresh_discovery_required": before_entry is None
        or before_entry.get("version") != expected_version,
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="action", required=True)
    prepare_parser = commands.add_parser("prepare", help="generate the Framework projection")
    prepare_parser.add_argument("--package-id", required=True)
    prepare_parser.add_argument("--owner-root", required=True)
    prepare_parser.add_argument("--framework-root", required=True)

    publish_parser = commands.add_parser("publish", help="publish and verify immutable OCI bytes")
    publish_parser.add_argument("--package-id", required=True)
    publish_parser.add_argument("--framework-root", required=True)
    publish_parser.add_argument("--request-id")

    activate_parser = commands.add_parser("activate", help="update the local carrier and read it back")
    activate_parser.add_argument("--package-id", required=True)
    activate_parser.add_argument("--framework-root", required=True)
    activate_parser.add_argument("--codex-bin", default="codex")
    activate_parser.add_argument("--opl-bin", default="opl")
    activate_parser.add_argument("--user-profile", default="~/.codex/AGENTS.md")
    activate_parser.add_argument("--timeout", type=int, default=180)
    return root


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = {"prepare": prepare, "publish": publish, "activate": activate}[args.action](args)
    except ReleaseError as exc:
        print(json.dumps({"status": "failed", "action": args.action, "error": str(exc)}))
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
