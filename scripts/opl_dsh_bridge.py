#!/usr/bin/env python3
"""OPL DSH bridge reusing OPL DSH public control CLI for bounded worker slices.

Zero Fleet imports. Never writes raw credentials or invents a second DSH agent loop.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

try:
    from . import opl_runtime as runtime
    from . import opl_execution
    from . import opl_bridge_common as bridge_common
    from . import opl_session_discovery as session_discovery
except ImportError:  # Direct script execution.
    import opl_runtime as runtime
    import opl_execution
    import opl_bridge_common as bridge_common
    import opl_session_discovery as session_discovery


BridgeError = bridge_common.BridgeError
flow_root = bridge_common.flow_root


def resolve_dsh_control_script(explicit: str | None = None) -> Path:
    """Locate OPL DSH public `control.mjs` entrypoint."""
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    if os.environ.get("OPL_DSH_CONTROL_SCRIPT"):
        candidates.append(Path(os.environ["OPL_DSH_CONTROL_SCRIPT"]).expanduser())
    codex_home = session_discovery.default_codex_home()
    candidates.extend(
        [
            codex_home / "skills" / "opl-dsh-official" / "control.mjs",
            Path.home() / ".agents" / "skills" / "opl-dsh-official" / "control.mjs",
        ]
    )
    for candidate in candidates:
        resolved = candidate.resolve() if candidate.exists() else candidate
        if resolved.is_file():
            return resolved
    raise BridgeError("OPL DSH public control script (opl-dsh-official/control.mjs) is unavailable")


def resolve_node_bin(explicit: str | None = None) -> str:
    candidate = explicit or os.environ.get("OPL_NODE_BIN") or shutil.which("node")
    if not candidate:
        raise BridgeError("node runtime is unavailable for OPL DSH bridge")
    path = Path(candidate).expanduser()
    if path.is_absolute() and not os.access(path, os.X_OK):
        raise BridgeError(f"node runtime is not executable: {path}")
    return str(path)


def probe_dsh_surface(
    *,
    dsh_control: str | None = None,
    dsh_home: Path | None = None,
    node_bin: str | None = None,
) -> dict[str, Any]:
    """Read-only probe of OPL DSH public delegation script and local execution catalog."""
    catalog = session_discovery.discover_dsh_catalog(dsh_home=dsh_home)
    node_path = node_bin or os.environ.get("OPL_NODE_BIN") or shutil.which("node")
    try:
        ctrl_path = str(resolve_dsh_control_script(dsh_control))
    except BridgeError:
        ctrl_path = None
    enabled_combos = [c for c in catalog.get("combinations", []) if c.get("enabled", True)]
    return {
        "available": bool(ctrl_path and node_path),
        "control_script": ctrl_path,
        "node_available": bool(node_path),
        "catalog_present": bool(catalog.get("present")),
        "harnesses": [h.get("id") for h in catalog.get("harnesses", []) if h.get("id")],
        "enabled_combinations": len(enabled_combos),
        "combinations": enabled_combos,
    }


def run_worker_slice(
    handoff: dict[str, Any],
    *,
    context_manifest: dict[str, Any] | None = None,
    cwd: Path | None = None,
    dsh_control: str | None = None,
    combination: str | None = None,
    model: str | None = None,
    sandbox: str | None = None,
    node_bin: str | None = None,
    timeout_seconds: int = 900,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Dispatch a bounded worker slice to OPL DSH via its public `control.mjs` CLI."""
    try:
        validated_handoff = opl_execution.validate_handoff(handoff)
        opl_execution.enforce_pre_execution_envelope(validated_handoff)
        binding = opl_execution.handoff_binding(validated_handoff)
    except opl_execution.ExecutionError as exc:
        raise BridgeError(str(exc)) from exc

    resolved_sandbox = bridge_common.resolve_sandbox_mode(validated_handoff, explicit_sandbox=sandbox)
    envelope = validated_handoff.get("envelope") or {}
    effective_timeout = int(timeout_seconds)
    if "max_duration_seconds" in envelope:
        effective_timeout = min(effective_timeout, int(envelope["max_duration_seconds"]))

    resolved_cwd = (cwd or flow_root()).expanduser().resolve()
    prompt = bridge_common.worker_prompt(validated_handoff, binding, context_manifest)

    node_exec = node_bin if dry_run and node_bin else ("node" if dry_run else resolve_node_bin(node_bin))
    if dry_run:
        try:
            ctrl_path = resolve_dsh_control_script(dsh_control)
        except BridgeError:
            ctrl_path = Path(dsh_control) if dsh_control else Path("opl-dsh-official/control.mjs")
    else:
        ctrl_path = resolve_dsh_control_script(dsh_control)

    subcommand = "delegate" if (combination or model) else "dispatch"

    with tempfile.TemporaryDirectory(prefix="opl-dsh-worker-") as tmp:
        prompt_file = (Path(tmp) / "prompt.txt").resolve()
        prompt_file.write_text(prompt, encoding="utf-8")
        argv = [
            node_exec,
            str(ctrl_path),
            subcommand,
            "--task",
            validated_handoff["objective_id"],
            "--operation",
            validated_handoff["attempt_id"],
            "--cwd",
            str(resolved_cwd),
            "--prompt-file",
            str(prompt_file),
            *(["--combination", combination] if combination and subcommand == "delegate" else []),
            *(["--model", model] if model and subcommand == "delegate" else []),
        ]
        if dry_run:
            return {
                "schema": "opl_dsh_bridge_dry_run.v1",
                "mode": "worker",
                "subcommand": subcommand,
                "argv": argv,
                "cwd": str(resolved_cwd),
                "sandbox": resolved_sandbox,
                "combination": combination,
                "binding": binding,
                "prompt": prompt,
            }

        try:
            proc = runtime.run_with_retry(
                lambda: subprocess.run(
                    argv,
                    cwd=resolved_cwd,
                    capture_output=True,
                    text=True,
                    timeout=effective_timeout,
                    check=False,
                ),
                attempts=2,
                min_wait=0.05,
                max_wait=0.25,
                retry_on=(BlockingIOError, InterruptedError),
            )
        except subprocess.TimeoutExpired as exc:
            raise BridgeError(f"OPL DSH control dispatch timed out after {effective_timeout}s") from exc
        except OSError as exc:
            raise BridgeError(f"OPL DSH control dispatch failed to start: {exc}") from exc

        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()
            raise BridgeError(f"OPL DSH control dispatch failed: {detail}")

        raw_out = (proc.stdout or "").strip()
        if not raw_out:
            raise BridgeError("OPL DSH control dispatch produced empty output")
        try:
            receipt = json.loads(raw_out)
        except json.JSONDecodeError as exc:
            raise BridgeError("OPL DSH control dispatch output is not valid JSON") from exc
        if not isinstance(receipt, dict):
            raise BridgeError("OPL DSH control dispatch output must be a JSON object")

        if subcommand == "dispatch" and receipt.get("accepted") is False:
            raise BridgeError("OPL DSH dispatch was not accepted")

        task_ref = str(
            receipt.get("taskId")
            or receipt.get("requestId")
            or receipt.get("sessionId")
            or receipt.get("id")
            or validated_handoff["attempt_id"]
        )
        session_id = receipt.get("sessionId") or receipt.get("id")
        checkpoint_refs = [f"dsh:task:{task_ref}"]
        if isinstance(session_id, str) and session_id.strip():
            checkpoint_refs.append(f"dsh:session:{session_id.strip()}")

        candidate_result = {
            "schema": "opl_worker_result.v1",
            "binding": binding,
            "outcome": "checkpoint",
            "artifact_refs": [],
            "checkpoint_refs": checkpoint_refs,
            "remaining": [validated_handoff["scope"]],
            "next_action": "Await DSH task_feedback completion receipt and verify workspace artifacts",
        }
        try:
            validated_result = opl_execution.validate_result(candidate_result, validated_handoff)
            opl_execution.evaluate_budget_usage(validated_handoff, validated_result)
        except opl_execution.ExecutionError as exc:
            raise BridgeError(str(exc)) from exc
        return validated_result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="mode", required=True)

    cat = subparsers.add_parser("catalog", help="probe available DSH control script and combinations")
    cat.add_argument("--dsh-control")
    cat.add_argument("--dsh-home", type=Path)

    wrk = subparsers.add_parser("worker", help="dispatch bounded worker slice via OPL DSH")
    wrk.add_argument("--handoff-json")
    wrk.add_argument("--dsh-control")
    wrk.add_argument("--combination")
    wrk.add_argument("--model")
    wrk.add_argument("--sandbox", choices=bridge_common.SANDBOX_MODES)
    wrk.add_argument("--node-bin")
    wrk.add_argument("--cwd", type=Path)
    wrk.add_argument("--timeout-seconds", type=int, default=900)
    wrk.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.mode == "catalog":
            result = probe_dsh_surface(dsh_control=args.dsh_control, dsh_home=args.dsh_home)
        else:
            handoff = bridge_common.load_json_arg(args.handoff_json, env_var="OPL_HANDOFF_PATH")
            manifest = None
            if os.environ.get("OPL_CONTEXT_MANIFEST"):
                m_path = Path(os.environ["OPL_CONTEXT_MANIFEST"])
                if m_path.is_file():
                    manifest = json.loads(m_path.read_text(encoding="utf-8"))
            result = run_worker_slice(
                handoff,
                context_manifest=manifest,
                cwd=args.cwd,
                dsh_control=args.dsh_control,
                combination=args.combination,
                model=args.model,
                sandbox=args.sandbox,
                node_bin=args.node_bin,
                timeout_seconds=args.timeout_seconds,
                dry_run=args.dry_run,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except BridgeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
