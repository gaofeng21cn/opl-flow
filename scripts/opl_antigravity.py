#!/usr/bin/env python3
"""Direct AntiGravity baseline doctor and safe template configurator for OPL Flow."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    from . import opl_runtime as runtime
except ImportError:  # Direct script execution.
    import opl_runtime as runtime


def flow_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_gemini_home() -> Path:
    env_home = os.environ.get("GEMINI_HOME", "").strip()
    if env_home:
        return Path(env_home).expanduser().resolve()
    return (Path.home() / ".gemini").resolve()


def default_agents_home(gemini_home: Path) -> Path:
    return gemini_home.parent / ".agents"


def load_baseline_manifest(root: Path | None = None) -> dict[str, Any]:
    base = root or flow_root()
    path = base / "templates" / "antigravity" / "baseline-manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != "opl_flow_antigravity_baseline.v1":
        raise ValueError(f"invalid AntiGravity baseline manifest: {path}")
    return data


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def split_frontmatter(text: str) -> tuple[str, str]:
    return runtime.split_frontmatter(text)


def _normalize_heading(line: str) -> str:
    stripped = line.strip()
    without_paren = re.sub(r"\s*[\(（][^\)）]*[\)）]\s*$", "", stripped)
    return re.sub(r"\s+", " ", without_paren).casefold()


def extract_headings(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^#{1,3}\s+\S", stripped):
            out[_normalize_heading(stripped)] = stripped
    return out


def merge_managed_block(
    existing: str | None,
    template: str,
    *,
    start_marker: str,
    end_marker: str,
) -> tuple[str, str, list[str]]:
    """Safely merge a managed baseline block while preserving user content.

    Returns (action, candidate_text, overlapping_headings):
      - "create": target did not exist
      - "update_managed_block": existing markers updated in place
      - "append_managed_block": existing unmarked file preserved, block appended
      - "unchanged": resulting text equals existing text
      - "merge_required": existing unmarked file already contains overlapping headings
    """
    tpl_fm, tpl_body = split_frontmatter(template)
    managed_block = f"{start_marker}\n{tpl_body.strip()}\n{end_marker}\n"

    if existing is None or not existing.strip():
        candidate = f"{tpl_fm}{managed_block}"
        if existing is not None and candidate == existing:
            return "unchanged", existing, []
        return "create", candidate, []

    pattern = re.compile(
        rf"{re.escape(start_marker)}[\s\S]*?{re.escape(end_marker)}\r?\n?",
        re.MULTILINE,
    )
    if pattern.search(existing):
        candidate = pattern.sub(lambda _: managed_block, existing, count=1)
        if not candidate.endswith("\n"):
            candidate += "\n"
        if candidate == existing:
            return "unchanged", existing, []
        return "update_managed_block", candidate, []

    # Existing unmarked file: preserve user content; never silently duplicate overlapping sections.
    existing_fm, existing_body = split_frontmatter(existing)
    if existing.strip() == template.strip():
        return "unchanged", existing, []

    tpl_headings = extract_headings(tpl_body)
    existing_headings = extract_headings(existing_body)
    overlap = sorted(existing_headings[key] for key in (set(tpl_headings) & set(existing_headings)))
    if overlap:
        return "merge_required", existing, overlap

    fm_prefix = existing_fm if existing_fm else tpl_fm
    body_clean = existing_body.rstrip()
    separator = "\n\n" if body_clean else ""
    candidate = f"{fm_prefix}{body_clean}{separator}{managed_block}"
    if candidate == existing:
        return "unchanged", existing, []
    return "append_managed_block", candidate, []


def backup_file(target: Path, gemini_home: Path, backup_root: Path) -> Path:
    try:
        rel = target.resolve().relative_to(gemini_home.resolve())
    except ValueError:
        rel = Path(target.name)
    dst = backup_root / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, dst)
    return dst


def atomic_write_text(target: Path, content: str) -> None:
    runtime.atomic_write_text(target, content, mode=0o644, preserve_mode=True, fsync=True)


def _parse_iso(value: Any) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _decode_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for key, val in raw.items():
        if isinstance(val, str) and val.strip()[:1] in "{[\"":
            try:
                out[key] = json.loads(val)
            except Exception:
                out[key] = val
        else:
            out[key] = val
    return out


def inspect_recent_telemetry(gemini_home: Path, days: int) -> dict[str, Any]:
    brain_dir = gemini_home / "antigravity" / "brain"
    now = datetime.datetime.now(datetime.timezone.utc).timestamp()
    cutoff = now - days * 86400

    by_role: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "convs": 0,
            "turns": 0,
            "tools": 0,
            "ops": 0,
            "agy_calls": 0,
            "agy_ops": 0,
            "cli_calls": 0,
            "spills": 0,
            "img_reads": 0,
            "user_media": 0,
            "multi_edit": 0,
        }
    )
    bs_queries: list[int] = []
    ae_files: list[int] = []
    ae_hunks: list[int] = []
    ae_best_effort = 0
    ae_verify = 0
    ae_mismatch = 0
    ae_verify_fail = 0
    rc_cmds: list[int] = []
    rc_full = 0
    rc_compact = 0
    rc_trunc = 0
    qo_paths: list[int] = []
    snap_new_main = 0
    snap_hit = 0
    skills_read: Counter[str] = Counter()
    errors: Counter[str] = Counter()

    if days <= 0 or not brain_dir.is_dir():
        return {"days": days, "scanned": False, "roles": {}}

    for entry in brain_dir.iterdir():
        if not entry.is_dir() or entry.name == "tempmediaStorage":
            continue
        logs_dir = entry / ".system_generated" / "logs"
        full_log = logs_dir / "transcript_full.jsonl"
        compact_log = logs_dir / "transcript.jsonl"
        transcript = full_log if full_log.is_file() else compact_log
        if not transcript.is_file():
            continue
        try:
            if transcript.stat().st_mtime < cutoff:
                continue
        except OSError:
            continue

        steps: list[dict[str, Any]] = []
        with transcript.open("r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    parsed = json.loads(line)
                    if isinstance(parsed, dict):
                        steps.append(parsed)
                except Exception:
                    continue
        if not steps:
            continue

        ts_all = [t for t in (_parse_iso(s.get("created_at")) for s in steps) if t is not None]
        if not ts_all or max(ts_all) < cutoff:
            continue

        has_user = any(s.get("type") == "USER_INPUT" for s in steps)
        all_tools = {
            str(tc.get("name", ""))
            for s in steps
            for tc in (s.get("tool_calls") or [])
            if isinstance(tc, dict)
        }
        if has_user:
            role = "main"
        elif "read_board" in all_tools or "post_message" in all_tools:
            role = "swarm_worker"
        elif any(tn.startswith("mcp_agy-fast_") for tn in all_tools):
            role = "sub_mcp"
        else:
            role = "sub_other"

        st = by_role[role]
        st["convs"] += 1

        if role == "main" and min(ts_all) >= cutoff:
            snap_new_main += 1
            if any(
                s.get("type") == "SYSTEM_MESSAGE" and "[agy-fast" in str(s.get("content") or "")
                for s in steps[:5]
            ):
                snap_hit += 1

        for idx, step in enumerate(steps):
            s_ts = _parse_iso(step.get("created_at")) or 0.0
            if s_ts < cutoff:
                continue
            stype = step.get("type")
            if stype == "USER_INPUT" and isinstance(step.get("media"), list) and step["media"]:
                st["user_media"] += len(step["media"])
                continue
            if stype == "ERROR_MESSAGE":
                err_txt = str(step.get("error") or step.get("content") or "").lower()
                if "stream was interrupted" in err_txt:
                    errors["stream_interrupted"] += 1
                elif "stream idle timeout" in err_txt:
                    errors["stream_idle_timeout"] += 1
                elif "api error" in err_txt:
                    errors["api_retry_error"] += 1
                else:
                    errors["other_error"] += 1
                continue
            if stype != "PLANNER_RESPONSE":
                continue

            st["turns"] += 1
            tcs = [tc for tc in (step.get("tool_calls") or []) if isinstance(tc, dict)]
            results: list[dict[str, Any]] = []
            j = idx + 1
            while j < len(steps) and steps[j].get("type") in ("GENERIC", "SYSTEM_MESSAGE"):
                if steps[j].get("type") == "GENERIC":
                    results.append(steps[j])
                j += 1

            names = [str(tc.get("name", "")) for tc in tcs]
            if names.count("edit_file") >= 2:
                st["multi_edit"] += 1

            for c_idx, tc in enumerate(tcs):
                name = str(tc.get("name", ""))
                args = _decode_args(tc.get("args"))
                rc = str(results[c_idx].get("content") or "") if c_idx < len(results) else ""
                st["tools"] += 1
                if "output was truncated" in rc:
                    st["spills"] += 1

                ops = 1
                if name == "mcp_agy-fast_fast_batch_search":
                    qs = args.get("queries")
                    ops = len(qs) if isinstance(qs, list) and qs else 1
                    bs_queries.append(ops)
                    st["agy_calls"] += 1
                    st["agy_ops"] += ops
                elif name == "mcp_agy-fast_fast_apply_edits":
                    eds = args.get("edits")
                    nf = len(eds) if isinstance(eds, list) else 0
                    nh = 0
                    if isinstance(eds, list):
                        for item in eds:
                            if isinstance(item, dict):
                                if item.get("create") is not None:
                                    nh += 1
                                else:
                                    nh += max(1, len(item.get("hunks") or []))
                    has_verify = bool(args.get("verify"))
                    ops = max(1, nh) + (1 if has_verify else 0)
                    ae_files.append(nf)
                    ae_hunks.append(nh)
                    if args.get("bestEffort"):
                        ae_best_effort += 1
                    if has_verify:
                        ae_verify += 1
                    if "Partial edit applied" in rc or "Atomic edit aborted" in rc:
                        ae_mismatch += 1
                    elif "Verify [FAIL" in rc or "Verify [TIMEOUT" in rc:
                        ae_verify_fail += 1
                    st["agy_calls"] += 1
                    st["agy_ops"] += ops
                elif name == "mcp_agy-fast_fast_quick_outline":
                    ps = args.get("paths")
                    ops = len(ps) if isinstance(ps, list) and ps else 1
                    qo_paths.append(ops)
                    st["agy_calls"] += 1
                    st["agy_ops"] += ops
                elif name == "mcp_agy-fast_fast_read_slices":
                    o = args.get("outlines") or []
                    sl = args.get("slices") or []
                    lr = args.get("lineRanges") or []
                    ops = max(
                        1,
                        (len(o) if isinstance(o, list) else 0)
                        + (len(sl) if isinstance(sl, list) else 0)
                        + (len(lr) if isinstance(lr, list) else 0),
                    )
                    st["agy_calls"] += 1
                    st["agy_ops"] += ops
                elif name == "mcp_agy-fast_fast_run_checks":
                    cs = args.get("commands")
                    ops = len(cs) if isinstance(cs, list) and cs else 1
                    rc_cmds.append(ops)
                    if str(args.get("outputMode") or "compact") == "full":
                        rc_full += 1
                    else:
                        rc_compact += 1
                    if "[truncated:" in rc:
                        rc_trunc += 1
                    st["agy_calls"] += 1
                    st["agy_ops"] += ops
                elif name == "read_file":
                    fpath = str(args.get("Path") or "")
                    if fpath.endswith("SKILL.md"):
                        m = re.search(r"skills/([^/]+)/SKILL\.md", fpath)
                        skills_read[m.group(1) if m else Path(fpath).parent.name] += 1
                    if re.search(r"\.(png|jpg|jpeg|webp|gif)$", fpath, re.I):
                        st["img_reads"] += 1
                elif name == "run_command":
                    cmd = str(args.get("CommandLine") or "")
                    if "mcp-server.mjs" in cmd and "--cli" in cmd:
                        st["cli_calls"] += 1
                st["ops"] += ops

    roles_out: dict[str, Any] = {}
    for role, st in by_role.items():
        roles_out[role] = {
            **st,
            "turns_per_10_ops": round(10 * st["turns"] / max(1, st["ops"]), 2),
            "agy_avg_packing": round(st["agy_ops"] / st["agy_calls"], 2) if st["agy_calls"] else 0.0,
        }

    return {
        "days": days,
        "scanned": True,
        "roles": roles_out,
        "agy_fast": {
            "batch_search": {
                "calls": len(bs_queries),
                "avg_queries": round(sum(bs_queries) / len(bs_queries), 2) if bs_queries else 0.0,
                "single_query_calls": sum(1 for x in bs_queries if x == 1),
            },
            "apply_edits": {
                "calls": len(ae_files),
                "avg_files": round(sum(ae_files) / len(ae_files), 2) if ae_files else 0.0,
                "avg_hunks": round(sum(ae_hunks) / len(ae_hunks), 2) if ae_hunks else 0.0,
                "best_effort_calls": ae_best_effort,
                "verify_calls": ae_verify,
                "mismatch_calls": ae_mismatch,
                "verify_fail_calls": ae_verify_fail,
            },
            "run_checks": {
                "calls": len(rc_cmds),
                "avg_commands": round(sum(rc_cmds) / len(rc_cmds), 2) if rc_cmds else 0.0,
                "single_command_calls": sum(1 for x in rc_cmds if x == 1),
                "full_mode_calls": rc_full,
                "compact_mode_calls": rc_compact,
                "budget_truncated_calls": rc_trunc,
            },
            "quick_outline": {
                "calls": len(qo_paths),
                "avg_paths": round(sum(qo_paths) / len(qo_paths), 2) if qo_paths else 0.0,
            },
            "session_start_new_main_hit": snap_hit,
            "session_start_new_main_total": snap_new_main,
        },
        "skills_read": dict(skills_read),
        "errors": dict(errors),
    }


def _inspect_rule_budgets(gemini_home: Path, cap: int, warn: int) -> list[dict[str, Any]]:
    items: list[tuple[str, Path]] = [
        ("global:GEMINI.md", gemini_home / "GEMINI.md"),
        ("agy-fast:AGENTS.md", gemini_home / "config/plugins/agy-fast/rules/AGENTS.md"),
        ("agy-fast:AGENTS.local.md", gemini_home / "config/plugins/agy-fast/rules/AGENTS.local.md"),
    ]
    projects_dir = gemini_home / "config" / "projects"
    if projects_dir.is_dir():
        for pfile in sorted(projects_dir.glob("*.json")):
            try:
                pdata = json.loads(pfile.read_text(encoding="utf-8"))
            except Exception:
                continue
            pname = str(pdata.get("name") or pfile.stem)
            for res in (pdata.get("projectResources") or {}).get("resources", []):
                if not isinstance(res, dict):
                    continue
                uri = str((res.get("gitFolder") or res.get("folder") or {}).get("folderUri") or "")
                if uri.startswith("file://"):
                    root = Path(urllib.parse.unquote(uri[7:]))
                    for rname in ("AGENTS.md", "GEMINI.md"):
                        candidate = root / rname
                        if candidate.is_file():
                            items.append((f"{pname}:{rname}", candidate))

    seen: set[Path] = set()
    rows: list[dict[str, Any]] = []
    for label, path in items:
        if not path.is_file():
            continue
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        size = path.stat().st_size
        status = "over_cap" if size > cap else ("warn" if size > warn else "ok")
        rows.append(
            {
                "label": label,
                "path": str(path),
                "bytes": size,
                "cap_ratio": round(size / cap, 3),
                "status": status,
            }
        )
    rows.sort(key=lambda r: -r["bytes"])
    return rows


def _run_agy_fast_doctor(doctor_script: Path) -> dict[str, Any]:
    if not doctor_script.is_file():
        return {"available": False, "ok": False}
    node = shutil.which("node")
    if not node:
        return {"available": True, "ok": False, "error": "node not found in PATH"}
    proc = subprocess.run(
        [node, str(doctor_script), "doctor"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=20,
    )
    return {
        "available": True,
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "summary": (proc.stdout or proc.stderr).strip()[:600],
    }


def antigravity_doctor(
    *,
    gemini_home: Path | None = None,
    agents_home: Path | None = None,
    root: Path | None = None,
    agy_bin: str | None = None,
    days: int = 7,
    run_plugin_doctor: bool = True,
) -> dict[str, Any]:
    base = root or flow_root()
    ghome = (gemini_home or default_gemini_home()).resolve()
    ahome = (agents_home or default_agents_home(ghome)).resolve()
    manifest = load_baseline_manifest(base)
    markers = manifest["managed_markers"]
    budgets = manifest["rule_budgets"]

    agy_exec = agy_bin or shutil.which("agy")
    config_path = ghome / "config" / "config.json"
    config_data: dict[str, Any] = {}
    if config_path.is_file():
        try:
            parsed = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                config_data = parsed
        except Exception:
            config_data = {}

    plugins_cfg = config_data.get("plugins") if isinstance(config_data.get("plugins"), dict) else {}
    enabled_plugins = sorted(
        k for k, v in plugins_cfg.items() if isinstance(v, dict) and v.get("enabled", True)
    )
    disabled_plugins = sorted(
        k for k, v in plugins_cfg.items() if isinstance(v, dict) and not v.get("enabled", True)
    )

    agy_fast_dir = ghome / "config" / "plugins" / "agy-fast"
    agy_fast_installed = (agy_fast_dir / "plugin.json").is_file()
    agy_fast_enabled = agy_fast_installed and (
        "agy-fast" not in plugins_cfg
        or bool(isinstance(plugins_cfg.get("agy-fast"), dict) and plugins_cfg["agy-fast"].get("enabled", True))
    )
    agy_fast_doctor = (
        _run_agy_fast_doctor(agy_fast_dir / "scripts" / "install.mjs")
        if run_plugin_doctor and agy_fast_installed
        else {"available": agy_fast_installed, "ok": None}
    )

    # Rules status
    rules_state: dict[str, Any] = {}
    for rule in manifest["rules"]:
        target = ghome / rule["target_rel"]
        tpl = (base / rule["template_path"]).read_text(encoding="utf-8")
        if target.is_file():
            content = target.read_text(encoding="utf-8")
            action, _, overlap = merge_managed_block(
                content,
                tpl,
                start_marker=markers["start"],
                end_marker=markers["end"],
            )
            has_markers = markers["start"] in content and markers["end"] in content
            rules_state[rule["id"]] = {
                "path": str(target),
                "present": True,
                "bytes": target.stat().st_size,
                "managed_markers": has_markers,
                "sync_status": action,
                "overlapping_headings": overlap,
            }
        else:
            rules_state[rule["id"]] = {
                "path": str(target),
                "present": False,
                "bytes": 0,
                "managed_markers": False,
                "sync_status": "missing",
                "overlapping_headings": [],
            }

    # Global skills & duplicate check
    skills_dir = ghome / "config" / "skills"
    installed_skills = sorted(p.name for p in skills_dir.iterdir()) if skills_dir.is_dir() else []
    duplicates: list[dict[str, str]] = []
    for dup in manifest.get("avoid_duplicates", []):
        if dup["skill_id"] in installed_skills and dup["plugin_id"] in enabled_plugins:
            duplicates.append(dup)

    impeccable_shared = (ahome / "skills" / "impeccable").exists()
    impeccable_installed = (skills_dir / "impeccable").exists()
    swarm_skill_installed = (skills_dir / "swarm-code-worker-brief" / "SKILL.md").is_file()

    # Optional weekly audit sidecar
    audit_cfg = manifest["optional_weekly_audit"]
    sidecar_path = ghome / "config" / "sidecars" / audit_cfg["sidecar_id"] / "sidecar.json"
    audit_script_path = ghome / audit_cfg["script_target_rel"]

    rule_budgets = _inspect_rule_budgets(ghome, budgets["per_file_bytes_cap"], budgets["warn_bytes"])
    rule_budget_health = (
        "over_cap"
        if any(r["status"] == "over_cap" for r in rule_budgets)
        else ("warn" if any(r["status"] == "warn" for r in rule_budgets) else "ok")
    )

    telemetry = inspect_recent_telemetry(ghome, days)

    findings: list[str] = []
    recommended_actions: list[str] = []
    if not agy_fast_installed:
        findings.append("Core plugin 'agy-fast' is not installed.")
        recommended_actions.append(
            "Install agy-fast via `python3 scripts/opl_workflow.py antigravity apply --install-plugins --json` or its official installer."
        )
    elif not agy_fast_enabled:
        findings.append("Core plugin 'agy-fast' is installed but disabled in config.json.")
        recommended_actions.append("Enable 'agy-fast' in AntiGravity Plugins Manager or `agy plugin enable agy-fast`.")
    elif not rules_state["agy_fast_local_overrides"]["present"]:
        findings.append("Missing agy-fast empirical overrides (rules/AGENTS.local.md).")
        recommended_actions.append("Run `python3 scripts/opl_workflow.py antigravity apply --json` to materialize AGENTS.local.md.")

    if not rules_state["global_gemini_rules"]["present"]:
        findings.append("Global GEMINI.md baseline is missing.")
        recommended_actions.append("Run `python3 scripts/opl_workflow.py antigravity apply --json` to create GEMINI.md.")
    elif rules_state["global_gemini_rules"]["sync_status"] == "append_managed_block":
        findings.append("Global GEMINI.md does not yet include the OPL Flow AntiGravity baseline block.")
        recommended_actions.append("Run `python3 scripts/opl_workflow.py antigravity apply --json` to append the managed block safely.")

    if not swarm_skill_installed:
        findings.append("Bundled global Skill 'swarm-code-worker-brief' is not installed.")
        recommended_actions.append("Run `python3 scripts/opl_workflow.py antigravity apply --json` to install swarm-code-worker-brief.")

    for dup in duplicates:
        findings.append(
            f"Duplicate web guidance detected: skill '{dup['skill_id']}' is linked while plugin '{dup['plugin_id']}' is enabled."
        )
        recommended_actions.append(
            f"Remove the standalone symlink under {skills_dir / dup['skill_id']} to avoid double-loading."
        )

    if impeccable_shared and not impeccable_installed:
        recommended_actions.append(
            "Run `python3 scripts/opl_workflow.py antigravity apply --json` to link shared ~/.agents/skills/impeccable."
        )

    for row in rule_budgets:
        if row["status"] != "ok":
            findings.append(f"Rule file {row['label']} is {row['bytes']} B ({row['status']} vs 24KB cap).")

    baseline_degraded = (
        not agy_fast_enabled
        or not rules_state["global_gemini_rules"]["present"]
        or not swarm_skill_installed
        or (agy_fast_installed and not rules_state["agy_fast_local_overrides"]["present"])
        or bool(duplicates)
    )

    return {
        "schema": "opl_flow_antigravity_doctor.v1",
        "gemini_home": str(ghome),
        "status": "degraded" if baseline_degraded else "ready",
        "planes": {
            "runtime_surface": {
                "agy_cli": agy_exec,
                "config_json_present": config_path.is_file(),
                "enabled_plugins": enabled_plugins,
                "disabled_plugins": disabled_plugins,
            },
            "experience_baseline": {
                "status": "degraded" if baseline_degraded else "ready",
                "agy_fast_installed": agy_fast_installed,
                "agy_fast_enabled": agy_fast_enabled,
                "agy_fast_doctor": agy_fast_doctor,
                "rules": rules_state,
                "swarm_code_worker_brief_installed": swarm_skill_installed,
                "duplicates": duplicates,
            },
            "optional_enhancements": {
                "modern_web_guidance_plugin_enabled": "modern-web-guidance-plugin" in enabled_plugins,
                "impeccable_installed": impeccable_installed,
                "impeccable_shared_available": impeccable_shared,
                "weekly_audit_sidecar_present": sidecar_path.is_file(),
                "weekly_audit_script_present": audit_script_path.is_file(),
            },
            "rule_budget_health": {
                "status": rule_budget_health,
                "cap_bytes": budgets["per_file_bytes_cap"],
                "warn_bytes": budgets["warn_bytes"],
                "files": rule_budgets,
            },
        },
        "installed_global_skills": installed_skills,
        "telemetry": telemetry,
        "findings": findings,
        "recommended_actions": recommended_actions,
    }


def _install_agy_fast_plugin(gemini_home: Path) -> dict[str, Any]:
    git_bin = shutil.which("git")
    node_bin = shutil.which("node")
    if not git_bin or not node_bin:
        return {"status": "failed", "reason": "git and node are required to install agy-fast"}
    env = {
        **os.environ,
        "GEMINI_HOME": str(gemini_home),
        "GIT_TERMINAL_PROMPT": "0",
        "GCM_INTERACTIVE": "never",
    }
    with tempfile.TemporaryDirectory(prefix="opl-flow-agy-fast-") as tmp_dir:
        clone = subprocess.run(
            [git_bin, "clone", "--depth", "1", "https://github.com/INK-Q/agy-fast.git", tmp_dir],
            env=env,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=90,
        )
        if clone.returncode != 0:
            return {"status": "failed", "step": "git_clone", "stderr": clone.stderr.strip()[:400]}
        inst = subprocess.run(
            [node_bin, str(Path(tmp_dir) / "scripts" / "install.mjs"), "install"],
            env=env,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
        )
        if inst.returncode != 0:
            return {"status": "failed", "step": "install", "stderr": (inst.stderr or inst.stdout).strip()[:400]}
        return {"status": "installed", "output": inst.stdout.strip()[:400]}


def _build_weekly_audit_sidecar(
    *,
    gemini_home: Path,
    script_path: Path,
    cron_tz: str,
    schedule: str,
    display_name: str,
) -> dict[str, Any]:
    doctor_script = gemini_home / "config/plugins/agy-fast/scripts/install.mjs"
    bench_script = gemini_home / "config/plugins/agy-fast/dist/benchmark.mjs"
    gemini_md = gemini_home / "GEMINI.md"
    config_json = gemini_home / "config/config.json"
    agy_rules = gemini_home / "config/plugins/agy-fast/rules/AGENTS.md"
    agy_local = gemini_home / "config/plugins/agy-fast/rules/AGENTS.local.md"
    prompt = (
        "Run a strictly read-only weekly AntiGravity environment audit and community practice review. "
        "Do NOT modify local configuration, rules, or plugins, and do NOT open GitHub issues/PRs automatically. "
        "Run each read-only command as a separate run_command call (never chain with &&) so minimal allowlists match:\n"
        f"1. `python3 {script_path} --days 7`\n"
        f"2. `node {doctor_script} doctor`\n"
        f"3. `node {bench_script} analyze --local --recent 40 --split-usage`\n"
        "4. `gh release list -R INK-Q/agy-fast --limit 5`\n"
        f"5. Read `{gemini_md}`, `{config_json}`, and `{agy_local}` (if present) to verify rule budgets (<24KB) and active plugins.\n"
        "6. Search the web for recent official Google Antigravity and agy-fast updates, filtering out outdated hacks.\n"
        "Output a concise scorecard and at most 3-5 prioritized proposals (keep / tune / remove / upstream) awaiting user approval."
    )
    return {
        "builtin": "schedule",
        "args": [
            f"CRON_TZ={cron_tz} {schedule}",
            "agentapi",
            "new-conversation",
            "--",
            prompt,
        ],
        "restart_policy": "always",
        "display_name": display_name,
        "description": (
            f"Runs on '{schedule}' ({cron_tz}) for a read-only weekly AntiGravity telemetry, "
            "rule-budget, skill/plugin, and upstream practice digest without mutating local configs."
        ),
        "agent_permissions": {
            "access_grants": [
                f"command(python3 {script_path})",
                f"command(node {doctor_script} doctor)",
                f"command(node {bench_script} analyze)",
                "command(gh release list)",
                f"read_file({gemini_md})",
                f"read_file({config_json})",
                f"read_file({agy_rules})",
                f"read_file({agy_local})",
            ]
        },
    }


def _standalone_weekly_audit_script(gemini_home: Path) -> str:
    return (
        "#!/usr/bin/env python3\n"
        '"""Read-only weekly AntiGravity audit entrypoint materialized by OPL Flow."""\n'
        "from __future__ import annotations\n"
        "import argparse, json, sys\n"
        "from pathlib import Path\n\n"
        f"FLOW_SCRIPTS = Path({str(flow_root() / 'scripts')!r})\n"
        "if str(FLOW_SCRIPTS) not in sys.path:\n"
        "    sys.path.insert(0, str(FLOW_SCRIPTS))\n"
        "import opl_antigravity  # noqa: E402\n\n"
        "def main() -> int:\n"
        "    ap = argparse.ArgumentParser()\n"
        "    ap.add_argument('--days', type=int, default=7)\n"
        "    args = ap.parse_args()\n"
        f"    report = opl_antigravity.antigravity_doctor(gemini_home=Path({str(gemini_home)!r}), days=args.days, run_plugin_doctor=False)\n"
        "    print(json.dumps(report, ensure_ascii=False, indent=2))\n"
        "    return 0\n\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main())\n"
    )


def antigravity_apply(
    *,
    gemini_home: Path | None = None,
    agents_home: Path | None = None,
    root: Path | None = None,
    dry_run: bool = False,
    install_plugins: bool = False,
    with_weekly_audit: bool = False,
    cron_tz: str | None = None,
    schedule: str | None = None,
    run_plugin_doctor: bool = True,
) -> dict[str, Any]:
    base = root or flow_root()
    ghome = (gemini_home or default_gemini_home()).resolve()
    ahome = (agents_home or default_agents_home(ghome)).resolve()
    manifest = load_baseline_manifest(base)
    markers = manifest["managed_markers"]

    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_root = ghome / ".opl-flow-backups" / ts
    backups: list[str] = []
    actions: list[dict[str, Any]] = []

    def maybe_backup(target: Path) -> None:
        if not dry_run and target.exists() and not target.is_symlink():
            bpath = backup_file(target, ghome, backup_root)
            backups.append(str(bpath))

    # 1. Optional owner-supported agy-fast installation
    agy_fast_dir = ghome / "config" / "plugins" / "agy-fast"
    if install_plugins:
        if (agy_fast_dir / "plugin.json").is_file():
            actions.append({"target": "plugin:agy-fast", "action": "unchanged", "path": str(agy_fast_dir)})
        elif dry_run:
            actions.append({"target": "plugin:agy-fast", "action": "would_install", "path": str(agy_fast_dir)})
        else:
            res = _install_agy_fast_plugin(ghome)
            actions.append({"target": "plugin:agy-fast", "action": res["status"], "detail": res})

    # 2. Rules (GEMINI.md + agy-fast AGENTS.local.md when plugin installed)
    for rule in manifest["rules"]:
        req_plugin = rule.get("requires_plugin")
        if req_plugin:
            plugin_present = (ghome / "config" / "plugins" / req_plugin / "plugin.json").is_file()
            if not plugin_present and not (dry_run and install_plugins and req_plugin == "agy-fast"):
                actions.append(
                    {
                        "target": f"rule:{rule['id']}",
                        "action": "skipped_plugin_absent",
                        "requires_plugin": req_plugin,
                        "path": str(ghome / rule["target_rel"]),
                    }
                )
                continue

        target = ghome / rule["target_rel"]
        tpl = (base / rule["template_path"]).read_text(encoding="utf-8")
        existing = target.read_text(encoding="utf-8") if target.is_file() else None
        action, candidate, overlap = merge_managed_block(
            existing,
            tpl,
            start_marker=markers["start"],
            end_marker=markers["end"],
        )
        entry: dict[str, Any] = {
            "target": f"rule:{rule['id']}",
            "action": action,
            "path": str(target),
        }
        if overlap:
            entry["overlapping_headings"] = overlap
            entry["note"] = "Existing unmarked rule already contains overlapping sections; preserved untouched for semantic review."
        elif action != "unchanged" and not dry_run:
            maybe_backup(target)
            atomic_write_text(target, candidate)
        actions.append(entry)

    # 3. Skills (bundled swarm-code-worker-brief + optional impeccable symlink)
    for skill in manifest["skills"]:
        if skill["source"] == "bundled_template":
            target = ghome / skill["target_rel"]
            tpl = (base / skill["template_path"]).read_text(encoding="utf-8")
            existing = target.read_text(encoding="utf-8") if target.is_file() else None
            if existing == tpl:
                actions.append({"target": f"skill:{skill['id']}", "action": "unchanged", "path": str(target)})
            else:
                if not dry_run:
                    maybe_backup(target)
                    atomic_write_text(target, tpl)
                actions.append(
                    {
                        "target": f"skill:{skill['id']}",
                        "action": "create" if existing is None else "update",
                        "path": str(target),
                    }
                )
        elif skill["source"] == "external_owner_or_shared_agents_dir":
            shared_src = ahome / Path(skill["shared_agents_rel"]).relative_to(".agents")
            target = ghome / skill["target_rel"]
            if target.exists() or target.is_symlink():
                actions.append({"target": f"skill:{skill['id']}", "action": "unchanged", "path": str(target)})
            elif shared_src.exists():
                if not dry_run:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    os.symlink(shared_src, target)
                actions.append(
                    {
                        "target": f"skill:{skill['id']}",
                        "action": "symlink_create",
                        "source": str(shared_src),
                        "path": str(target),
                    }
                )
            else:
                actions.append(
                    {
                        "target": f"skill:{skill['id']}",
                        "action": "absent_optional",
                        "install_hint": skill.get("install_hint"),
                    }
                )

    # 4. Optional weekly read-only audit sidecar (never auto-enabled in config.json)
    if with_weekly_audit:
        audit_cfg = manifest["optional_weekly_audit"]
        eff_tz = cron_tz or audit_cfg["default_cron_tz"]
        eff_sched = schedule or audit_cfg["default_schedule"]
        script_path = ghome / audit_cfg["script_target_rel"]
        sidecar_path = ghome / "config" / "sidecars" / audit_cfg["sidecar_id"] / "sidecar.json"

        script_text = _standalone_weekly_audit_script(ghome)
        if script_path.is_file() and script_path.read_text(encoding="utf-8") == script_text:
            actions.append({"target": "weekly_audit:script", "action": "unchanged", "path": str(script_path)})
        else:
            if not dry_run:
                maybe_backup(script_path)
                atomic_write_text(script_path, script_text)
                os.chmod(script_path, 0o755)
            actions.append(
                {
                    "target": "weekly_audit:script",
                    "action": "create" if not script_path.is_file() else "update",
                    "path": str(script_path),
                }
            )

        sidecar_payload = json.dumps(
            _build_weekly_audit_sidecar(
                gemini_home=ghome,
                script_path=script_path,
                cron_tz=eff_tz,
                schedule=eff_sched,
                display_name=audit_cfg["display_name"],
            ),
            ensure_ascii=False,
            indent=2,
        ) + "\n"
        if sidecar_path.is_file() and sidecar_path.read_text(encoding="utf-8") == sidecar_payload:
            actions.append({"target": "weekly_audit:sidecar", "action": "unchanged", "path": str(sidecar_path)})
        else:
            if not dry_run:
                maybe_backup(sidecar_path)
                atomic_write_text(sidecar_path, sidecar_payload)
            actions.append(
                {
                    "target": "weekly_audit:sidecar",
                    "action": "create" if not sidecar_path.is_file() else "update",
                    "path": str(sidecar_path),
                    "auto_enabled": False,
                    "note": "Enable manually in AntiGravity Automations dashboard (sidecar://dashboard).",
                }
            )

    readback = antigravity_doctor(
        gemini_home=ghome,
        agents_home=ahome,
        root=base,
        days=0,
        run_plugin_doctor=run_plugin_doctor and not dry_run,
    )
    return {
        "schema": "opl_flow_antigravity_apply_receipt.v1",
        "dry_run": dry_run,
        "gemini_home": str(ghome),
        "backup_dir": str(backup_root) if backups else None,
        "backups": backups,
        "actions": actions,
        "doctor_readback": readback,
    }


def add_antigravity_subparser(subparsers: Any) -> None:
    ag = subparsers.add_parser(
        "antigravity",
        help="inspect or configure the AntiGravity experience baseline",
    )
    ag_sub = ag.add_subparsers(dest="antigravity_action", required=True)

    doc = ag_sub.add_parser("doctor", help="inspect AntiGravity plugins, rules, skills, and telemetry")
    doc.add_argument("--gemini-home", type=Path)
    doc.add_argument("--agents-home", type=Path)
    doc.add_argument("--agy-bin")
    doc.add_argument("--days", type=int, default=7)
    doc.add_argument("--skip-plugin-doctor", action="store_true")
    doc.add_argument("--json", action="store_true", help="emit JSON output (default)")

    app = ag_sub.add_parser("apply", help="safely apply the OPL Flow AntiGravity baseline templates")
    app.add_argument("--gemini-home", type=Path)
    app.add_argument("--agents-home", type=Path)
    app.add_argument("--dry-run", action="store_true")
    app.add_argument("--install-plugins", action="store_true")
    app.add_argument("--with-weekly-audit", action="store_true")
    app.add_argument("--tz", dest="cron_tz")
    app.add_argument("--schedule")
    app.add_argument("--skip-plugin-doctor", action="store_true")
    app.add_argument("--json", action="store_true", help="emit JSON output (default)")


def dispatch_antigravity(args: argparse.Namespace) -> dict[str, Any]:
    if args.antigravity_action == "doctor":
        return antigravity_doctor(
            gemini_home=args.gemini_home,
            agents_home=args.agents_home,
            agy_bin=args.agy_bin,
            days=args.days,
            run_plugin_doctor=not args.skip_plugin_doctor,
        )
    if args.antigravity_action == "apply":
        return antigravity_apply(
            gemini_home=args.gemini_home,
            agents_home=args.agents_home,
            dry_run=args.dry_run,
            install_plugins=args.install_plugins,
            with_weekly_audit=args.with_weekly_audit,
            cron_tz=args.cron_tz,
            schedule=args.schedule,
            run_plugin_doctor=not args.skip_plugin_doctor,
        )
    raise ValueError(f"unsupported antigravity action: {args.antigravity_action}")


def main(argv: list[str] | None = None) -> int:
    root_parser = argparse.ArgumentParser(description=__doc__)
    sub = root_parser.add_subparsers(dest="command", required=True)
    add_antigravity_subparser(sub)
    ns = root_parser.parse_args(["antigravity", *(argv if argv is not None else sys.argv[1:])])
    result = dispatch_antigravity(ns)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
