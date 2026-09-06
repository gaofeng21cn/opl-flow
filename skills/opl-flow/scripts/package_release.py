#!/usr/bin/env python3
"""Prepare, publish, and activate one first-party OPL Package."""

from __future__ import annotations

import argparse
import copy
import difflib
import hashlib
import json
import os
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


def safe_owner_ref(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or Path(value).is_absolute() or ".." in Path(value).parts:
        raise ReleaseError(f"invalid {label}: expected a checkout-relative path")
    return value


def committed_json(root: Path, commit: str, relative: str) -> dict[str, Any]:
    safe_owner_ref(relative, "owner ref")
    try:
        value = json.loads(git_value(root, "show", f"{commit}:{relative}"))
    except json.JSONDecodeError as exc:
        raise ReleaseError(f"committed owner ref is not JSON: {relative}") from exc
    if not isinstance(value, dict):
        raise ReleaseError(f"committed owner ref is not an object: {relative}")
    return value


def require_owner_release(
    owner_root: Path, package_id: str, *, owner_manifest_ref: str,
    source_root: str, workflow_profile: bool = False,
) -> tuple[dict[str, Any], str, str]:
    safe_owner_ref(owner_manifest_ref, "owner manifest ref")
    safe_owner_ref(source_root, "payload source root")
    if git_value(owner_root, "status", "--porcelain"):
        raise ReleaseError("owner checkout must be clean before projection")
    command(["git", "fetch", "origin", "main", "--tags", "--quiet"], cwd=owner_root)
    source_commit = git_value(owner_root, "rev-parse", "HEAD")
    if source_commit != git_value(owner_root, "rev-parse", "origin/main"):
        raise ReleaseError("owner HEAD must equal fresh origin/main")
    canonical = committed_json(owner_root, source_commit, owner_manifest_ref)
    descriptor_ref = (Path(source_root) / "opl-package.json").as_posix()
    descriptor = committed_json(owner_root, source_commit, descriptor_ref)
    manifest = descriptor if workflow_profile else canonical
    version = str(manifest.get("version") or "")
    if manifest.get("package_id") != package_id or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ReleaseError("owner opl-package.json has an invalid package id or stable SemVer")
    tag = f"v{version}"
    if git_value(owner_root, "cat-file", "-t", f"refs/tags/{tag}") != "tag":
        raise ReleaseError(f"owner release tag must be annotated: {tag}")
    if git_value(owner_root, "rev-parse", f"{tag}^{{}}") != source_commit:
        raise ReleaseError(f"owner release tag does not select HEAD: {tag}")
    owner_identity = canonical.get("package") if workflow_profile else canonical
    if not isinstance(owner_identity, dict) or (
        owner_identity.get("package_id", owner_identity.get("id")) != package_id
        or owner_identity.get("version") != version
    ):
        raise ReleaseError("canonical owner manifest identity differs from the carrier descriptor")
    descriptors = [descriptor]
    if source_root != "." and (owner_root / "opl-package.json").is_file():
        descriptors.append(committed_json(owner_root, source_commit, "opl-package.json"))
    surface = manifest.get("codex_surface", {})
    for candidate in descriptors:
        candidate_surface = candidate.get("codex_surface", {})
        if (
            candidate.get("package_id") != package_id or candidate.get("version") != version
            or candidate_surface.get("plugin_id") != surface.get("plugin_id")
            or candidate_surface.get("configured_codex_plugin_carrier") != surface.get("configured_codex_plugin_carrier")
        ):
            raise ReleaseError("owner and carrier descriptor identity or version differ")
    plugin_refs = [(Path(source_root) / ".codex-plugin/plugin.json").as_posix()]
    if source_root != "." and (owner_root / ".codex-plugin/plugin.json").is_file():
        plugin_refs.append(".codex-plugin/plugin.json")
    for relative in plugin_refs:
        plugin = committed_json(owner_root, source_commit, relative)
        if plugin.get("name") != surface.get("plugin_id") or plugin.get("version") != version:
            raise ReleaseError("committed carrier plugin identity or version differs from owner")
    return manifest, version, source_commit


def package_skill_ids(package: dict[str, Any]) -> list[str]:
    exports = package.get("exports")
    surface = package.get("codex_surface")
    skills = exports.get("core_skill_ids") if isinstance(exports, dict) else (
        surface.get("required_skill_ids") if isinstance(surface, dict) else None
    )
    if not isinstance(skills, list) or any(
        not isinstance(skill, str) or not re.fullmatch(r"[a-z0-9][a-z0-9.-]*", skill)
        for skill in skills
    ):
        raise ReleaseError("Package must declare required or core skill ids")
    return skills


def owner_projection(
    owner: dict[str, Any], previous: dict[str, Any], owner_root: Path
) -> dict[str, Any]:
    # Only Framework registration and carrier metadata survives from the old projection.
    framework_fields = (
        "registry_entry", "source", "source_repo", "schema_ref",
        "publication_projection_order", "publication_source", "publication_channel_admission",
        "compatibility_projection", "owner_package_manifest_ref", "owner_package_descriptor_ref",
        "source_manifest_ref", "package_core", "runtime_source_carrier", "carrier_adapters",
        "opl_managed_surface", "managed_shell",
    )
    projected = copy.deepcopy(owner)
    for field in framework_fields:
        if field in previous:
            projected[field] = copy.deepcopy(previous[field])
    if "machine_boundary" not in projected and "machine_boundary" in previous:
        projected["machine_boundary"] = previous["machine_boundary"]
    if "standard_agent_descriptor_projection" in previous:
        registration = copy.deepcopy(previous["standard_agent_descriptor_projection"])
        relative = owner.get("domain_descriptor_ref", registration.get("source_ref"))
        if not isinstance(relative, str):
            raise ReleaseError("standard Agent owner has no domain_descriptor_ref")
        descriptor_path = (owner_root / relative).resolve()
        if not descriptor_path.is_relative_to(owner_root):
            raise ReleaseError("owner domain descriptor escapes the checkout")
        descriptor = read_json(descriptor_path)
        interface = descriptor.get("standard_agent_interface")
        if not isinstance(interface, dict):
            raise ReleaseError("owner domain descriptor has no standard Agent interface")
        interface_ref = f"{relative}#/standard_agent_interface"
        if interface.get("ref_kind") == "repo_json_pointer":
            interface_ref = interface.get("ref")
            if not isinstance(interface_ref, str) or "#/" not in interface_ref:
                raise ReleaseError("owner standard Agent interface has no JSON pointer ref")
            filename, pointer = interface_ref.split("#", 1)
            safe_owner_ref(filename, "standard Agent interface ref")
            interface_path = (owner_root / filename).resolve()
            if not interface_path.is_relative_to(owner_root):
                raise ReleaseError("owner standard Agent interface escapes the checkout")
            interface = read_json(interface_path)
            for segment in pointer[1:].split("/"):
                segment = segment.replace("~1", "/").replace("~0", "~")
                interface = interface.get(segment) if isinstance(interface, dict) else None
            if not isinstance(interface, dict):
                raise ReleaseError("owner standard Agent interface JSON pointer is unresolved")
        registration.update(
            source_ref=relative,
            interface_source_ref=interface_ref,
            domain_id=descriptor.get("domain_id"),
            runtime_domain_id=interface.get("runtime", {}).get("runtime_domain_id"),
            explicit_aliases=interface.get("routing", {}).get("explicit_aliases"),
        )
        projected["standard_agent_descriptor_projection"] = registration
    package_skill_ids(projected)
    return projected


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    owner_root = Path(args.owner_root).resolve()
    framework_root = Path(args.framework_root).resolve()
    package_path = framework_root / "contracts/opl-framework/packages" / f"{args.package_id}.json"
    allowlist_path = (
        framework_root
        / "contracts/opl-framework/package-payload-allowlists"
        / f"{args.package_id}.json"
    )
    previous = read_json(package_path)
    allowlist = read_json(allowlist_path)
    publication_source = previous.get("publication_source")
    if not isinstance(publication_source, dict):
        raise ReleaseError("Framework projection has no owner publication source")
    owner_manifest, version, source_commit = require_owner_release(
        owner_root, args.package_id,
        owner_manifest_ref=publication_source.get("owner_package_manifest_ref"),
        source_root=allowlist.get("source_root"),
        workflow_profile=previous.get("surface_kind") == "opl_workflow_profile_package_manifest.v1",
    )
    expected_repo = str(allowlist.get("source_repo") or "")
    origin_repo = f"https://github.com/{repo_slug(owner_root)}"
    for label, value in (
        ("payload allowlist", expected_repo),
        ("Framework projection", previous.get("source_repo")),
        ("owner", owner_manifest.get("source_repo", expected_repo)),
    ):
        if not isinstance(value, str) or value.removesuffix(".git") != origin_repo:
            raise ReleaseError(f"{label} source_repo does not match origin")
    owner_codex_surface = owner_manifest.get("codex_surface")
    if (
        previous.get("package_id") != args.package_id
        or previous.get("surface_kind") != owner_manifest.get("surface_kind")
        or allowlist.get("package_id") != args.package_id
        or not isinstance(owner_codex_surface, dict)
        or allowlist.get("plugin_id") != owner_codex_surface.get("plugin_id")
    ):
        raise ReleaseError("Framework package projection has an invalid identity")
    package = owner_projection(owner_manifest, previous, owner_root)
    package["source_repo"] = expected_repo
    codex_surface = package["codex_surface"]
    payload_ref = f"payloads/{args.package_id}-{version}.json"
    package["version"] = version
    if "source_commit" in previous or "source_commit" in package:
        package["source_commit"] = source_commit
    codex_surface["plugin_payload_manifest_url"] = payload_ref
    codex_surface["carrier_source_commit"] = source_commit
    payload_path = package_path.parent / payload_ref
    content_lock = package.get("content_lock")
    if isinstance(content_lock, dict):
        paths = content_lock.get("paths")
        if not isinstance(paths, list):
            raise ReleaseError("owner content_lock has no paths array")
        allowlist["paths"] = copy.deepcopy(paths)
        descriptor_ref = package.get("owner_package_descriptor_ref")
        if isinstance(descriptor_ref, str) and descriptor_ref not in paths:
            allowlist["paths"].append(descriptor_ref)

    with tempfile.TemporaryDirectory(prefix="opl-package-cohort-") as temporary:
        temporary_root = Path(temporary)
        cohort_path = temporary_root / "owner-cohort-lock.json"
        staged_package = temporary_root / "packages" / package_path.name
        staged_allowlist = temporary_root / "allowlists" / allowlist_path.name
        staged_package.parent.mkdir()
        staged_allowlist.parent.mkdir()
        write_json(staged_package, package)
        write_json(staged_allowlist, allowlist)
        staged_payload = staged_package.parent / payload_ref
        if payload_path.exists() or payload_path.is_symlink():
            if payload_path.is_symlink() or not payload_path.is_file():
                raise ReleaseError("immutable payload path must be a regular file")
            staged_payload.parent.mkdir()
            staged_payload.write_bytes(payload_path.read_bytes())
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
                str(staged_package),
                "--allowlist",
                str(staged_allowlist),
                "--owner-cohort-lock",
                str(cohort_path),
                "--repo",
                str(owner_root),
                "--source-commit",
                source_commit,
            ],
            cwd=framework_root,
        )
        payload = read_json(staged_payload)
        if (
            payload.get("package_id") != args.package_id
            or payload.get("package_version") != version
            or payload.get("source_commit") != source_commit
        ):
            raise ReleaseError("generated Framework payload projection has an invalid identity")
        payload_bytes = staged_payload.read_bytes()
    payload_path.parent.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=payload_path.parent, prefix=f".{payload_path.name}.") as output:
        output.write(payload_bytes)
        output.flush()
        os.fsync(output.fileno())
        os.chmod(output.name, 0o644)
        try:
            os.link(output.name, payload_path)
        except FileExistsError:
            if payload_path.is_symlink() or not payload_path.is_file() or payload_path.read_bytes() != payload_bytes:
                raise ReleaseError("same-version immutable payload bytes differ")
    write_json(package_path, package)
    updated_files = [str(package_path), str(payload_path)]
    if allowlist != read_json(allowlist_path):
        write_json(allowlist_path, allowlist)
        updated_files.append(str(allowlist_path))
    return {
        "action": "prepare",
        "status": "projection_ready",
        "package_id": args.package_id,
        "version": version,
        "owner_source_commit": source_commit,
        "updated_files": updated_files,
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


def approve_release_environment(repo: str, run_id: int, request_id: str) -> dict[str, Any]:
    endpoint = f"repos/{repo}/actions/runs/{run_id}/pending_deployments"
    last_status = ""
    for _ in range(15):
        pending = command_json(["gh", "api", endpoint], timeout=30)
        if not isinstance(pending, list):
            raise ReleaseError("GitHub pending deployments readback is invalid")
        if pending:
            matches = [
                item
                for item in pending
                if isinstance(item, dict)
                and isinstance(item.get("environment"), dict)
                and item["environment"].get("name") == "release-stable"
            ]
            if len(pending) != 1 or len(matches) != 1:
                raise ReleaseError("publication has an unexpected pending deployment set")
            deployment = matches[0]
            environment_id = deployment["environment"].get("id")
            if not isinstance(environment_id, int) or deployment.get("current_user_can_approve") is not True:
                raise ReleaseError("current GitHub identity cannot approve release-stable")
            command_json(
                [
                    "gh", "api", "--method", "POST", endpoint,
                    "-F", f"environment_ids[]={environment_id}",
                    "-f", "state=approved",
                    "-f", f"comment=Authorized OPL Package publication {request_id}",
                ],
                timeout=30,
            )
            return {
                "status": "approved",
                "environment": "release-stable",
                "environment_id": environment_id,
            }
        run = command_json(
            ["gh", "run", "view", str(run_id), "--repo", repo, "--json", "status"],
            timeout=30,
        )
        last_status = str(run.get("status") or "") if isinstance(run, dict) else ""
        if last_status not in ("queued", "waiting"):
            return {"status": "not_required", "environment": None, "environment_id": None}
        time.sleep(1)
    if last_status == "waiting":
        raise ReleaseError("release-stable approval did not become available within 15s")
    return {"status": "not_required", "environment": None, "environment_id": None}


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
    environment_approval = approve_release_environment(repo, run_id, request_id)
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
        "environment_approval": environment_approval,
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


def installed_package_evidence(
    status: dict[str, Any], package: dict[str, Any]
) -> dict[str, Any]:
    package_id = package["package_id"]
    carrier = status.get("configured_carrier")
    native = status.get("installed_carrier_readback")
    readiness = status.get("installed_readiness")
    codex_surface = package.get("codex_surface", {})
    headless = codex_surface.get("interaction_mode") == "headless_internal"
    if (
        status.get("package_id") != package_id
        or status.get("installed_package_count") != 1
        or not isinstance(native, dict)
        or native.get("lifecycle_authority") != "carrier_owned"
        or native.get("version") != package["version"]
        or not isinstance(carrier, dict)
        or carrier.get("package_id") != package_id
        or carrier.get("status") != "installed"
        or carrier.get("installed_version") != package["version"]
        or carrier.get("enabled") is not (not headless)
        or not isinstance(readiness, dict)
        or readiness.get("installed") is not True
        or readiness.get("physical_status") != "available"
        or readiness.get("projection_callability", readiness.get("callability")) != "callable"
    ):
        raise ReleaseError(f"installed Package identity, version, exposure or callability is unverified: {package_id}")
    source = carrier.get("plugin_source_path")
    if not isinstance(source, str) or not source:
        raise ReleaseError(f"installed Package has no source path: {package_id}")
    root = Path(source).resolve()
    descriptor = read_json(root / "opl-package.json")
    if descriptor.get("package_id") != package_id or descriptor.get("version") != package["version"]:
        raise ReleaseError(f"installed owner descriptor identity differs: {package_id}")
    skills = package_skill_ids(package)
    missing_skills = [skill for skill in skills if not (root / "skills" / skill / "SKILL.md").is_file()]
    if missing_skills:
        raise ReleaseError(f"installed Package is missing required Skills: {missing_skills}")
    content_lock = package.get("content_lock")
    content_digest = None
    if isinstance(content_lock, dict):
        if (
            descriptor.get("content_lock") != content_lock
            or content_lock.get("algorithm") != "sha256"
            or content_lock.get("canonicalization") != "ordered_path_length_file_length_bytes"
            or not isinstance(content_lock.get("paths"), list)
        ):
            raise ReleaseError(f"installed Package content lock differs: {package_id}")
        digest = hashlib.sha256()
        for relative in content_lock["paths"]:
            if not isinstance(relative, str) or not (root / relative).resolve().is_relative_to(root):
                raise ReleaseError(f"installed Package content path is invalid: {package_id}")
            try:
                data = (root / relative).read_bytes()
            except OSError as exc:
                raise ReleaseError(f"installed Package content is unavailable: {relative}") from exc
            encoded = relative.encode("utf-8")
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
            digest.update(len(data).to_bytes(8, "big"))
            digest.update(data)
        content_digest = f"sha256:{digest.hexdigest()}"
        if content_digest != content_lock.get("digest"):
            raise ReleaseError(f"installed Package content bytes differ from its lock: {package_id}")
    return {
        "package_id": package_id,
        "version": descriptor["version"],
        "source_path": str(root),
        "interaction_mode": "headless_internal" if headless else "interactive",
        "installed_readiness": readiness,
        "installed_carrier_readback": native,
        "content_digest": content_digest,
        "required_skill_ids": skills,
        "missing_skill_ids": missing_skills,
    }


def package_status(args: argparse.Namespace, package_id: str) -> dict[str, Any]:
    readback = command_json(
        [args.opl_bin, "packages", "status", "--package-id", package_id, "--json"],
        timeout=args.timeout,
    )
    surface = readback.get("opl_agent_package_status") if isinstance(readback, dict) else None
    if not isinstance(surface, dict) or surface.get("package_id") != package_id:
        raise ReleaseError(f"Framework Package status returned no matching status surface: {package_id}")
    return surface


def package_action(args: argparse.Namespace, action: str, package_id: str) -> dict[str, Any]:
    readback = command_json(
        [args.opl_bin, "packages", action, "--package-id", package_id, "--json"],
        timeout=args.timeout,
    )
    surface = readback.get(f"opl_agent_package_{action}") if isinstance(readback, dict) else None
    if not isinstance(surface, dict):
        raise ReleaseError(f"Framework Package {action} returned no action surface: {package_id}")
    return surface


def activate(args: argparse.Namespace) -> dict[str, Any]:
    framework_root = Path(args.framework_root).resolve()
    package = read_json(
        framework_root / "contracts/opl-framework/packages" / f"{args.package_id}.json"
    )
    codex_surface = package.get("codex_surface")
    carrier = codex_surface.get("configured_codex_plugin_carrier") if isinstance(codex_surface, dict) else None
    selector = carrier.get("plugin_selector") if isinstance(carrier, dict) else None
    if package.get("package_id") != args.package_id or not isinstance(selector, str) or "@" not in selector:
        raise ReleaseError("Framework Package has no configured Codex plugin selector")
    required_skills = package_skill_ids(package)
    headless = codex_surface.get("interaction_mode") == "headless_internal"
    has_profile = isinstance(package.get("profile_surface"), dict)
    expected_version = str(package.get("version") or "")
    before_entry = None if headless else plugin_entry(selector, args.codex_bin)
    before_profile = installed_profile(before_entry) if has_profile else (None, None)
    before_status = package_status(args, args.package_id)
    lifecycle_action = "update" if isinstance(before_status.get("installed_carrier_readback"), dict) else "install"
    update_surface = package_action(args, lifecycle_action, args.package_id)
    after_entry = None if headless else plugin_entry(selector, args.codex_bin)
    if not headless and (
        not after_entry or after_entry.get("version") != expected_version or after_entry.get("enabled") is not True
    ):
        raise ReleaseError("installed Codex Plugin did not reach the expected enabled version")
    status_surface = package_status(args, args.package_id)
    installed = installed_package_evidence(status_surface, package)
    dependency_evidence = []
    dependencies = package.get("capability_dependencies", [])
    for dependency in dependencies:
        if not isinstance(dependency, dict) or dependency.get("required") is not True:
            continue
        dependency_id = dependency.get("package_id")
        if not isinstance(dependency_id, str) or not dependency_id:
            raise ReleaseError("required Package dependency has no package id")
        provider_surface = package_status(args, dependency_id)
        provider_install = None
        if not isinstance(provider_surface.get("installed_carrier_readback"), dict):
            provider_install = package_action(args, "install", dependency_id)
            provider_surface = package_status(args, dependency_id)
            status_surface = package_status(args, args.package_id)
        dependency_readiness = status_surface.get("package_dependency_readiness")
        rows = dependency_readiness.get("dependencies", []) if isinstance(dependency_readiness, dict) else []
        matching = [row for row in rows if isinstance(row, dict) and row.get("package_id") == dependency_id]
        if len(matching) != 1 or matching[0].get("status") != "current":
            raise ReleaseError(f"required Package dependency is not callable for this consumer: {dependency_id}")
        provider_carrier = provider_surface.get("configured_carrier")
        provider_source = provider_carrier.get("plugin_source_path") if isinstance(provider_carrier, dict) else None
        if not isinstance(provider_source, str) or not provider_source:
            raise ReleaseError(f"required Package dependency has no installed source: {dependency_id}")
        provider = read_json(Path(provider_source) / "opl-package.json")
        if provider.get("package_id") != dependency_id or provider.get("version") != matching[0].get("installed_version"):
            raise ReleaseError(f"installed dependency differs from the consumer binding: {dependency_id}")
        dependency_evidence.append({
            **installed_package_evidence(provider_surface, provider),
            "consumer_binding": matching[0],
            "package_install": provider_install,
            "operational_ready": provider_surface.get("operational_ready"),
        })
    managed_policy = status_surface.get("managed_policy_currentness")
    user_profile = Path(args.user_profile).expanduser().resolve()
    profile = profile_delta(before_profile, installed_profile(after_entry), user_profile) if has_profile else None
    return {
        "action": "activate",
        "status": "installed_and_read_back" if status_surface.get("operational_ready") is True
        else "installed_with_readiness_debt",
        "package_id": args.package_id,
        "version": expected_version,
        "plugin_selector": selector,
        "lifecycle_action": lifecycle_action,
        "package_update": {
            "status": update_surface.get("status"),
            "target_version": update_surface.get("target_version"),
            "observed_version": update_surface.get("observed_version"),
            "release_catalog_digest": update_surface.get("release_catalog_digest"),
        },
        "package_status": {
            "status": status_surface.get("status"),
            "installed_package_count": status_surface.get("installed_package_count"),
            "operational_ready": status_surface.get("operational_ready"),
            "launch_state": status_surface.get("launch_state"),
            "managed_policy_currentness": (
                managed_policy.get("status") if isinstance(managed_policy, dict) else None
            ),
        },
        "required_skill_ids": required_skills,
        "missing_skill_ids": installed["missing_skill_ids"],
        "installed_evidence": installed,
        "package_dependency_readiness": status_surface.get("package_dependency_readiness"),
        "installed_dependency_evidence": dependency_evidence,
        "profile": profile,
        "fresh_discovery_required": not headless and (
            before_entry is None or before_entry.get("version") != expected_version
        ),
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
