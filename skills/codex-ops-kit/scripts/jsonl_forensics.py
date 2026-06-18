#!/usr/bin/env python3
"""Bounded JSONL and raw/canonical forensics for Codex session evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


def iter_files(inputs: list[str], glob: str, max_files: int) -> Iterable[Path]:
    seen: set[Path] = set()
    for raw in inputs:
        path = Path(raw).expanduser()
        candidates = sorted(path.rglob(glob)) if path.is_dir() else [path]
        for candidate in candidates:
            if len(seen) >= max_files:
                return
            if candidate in seen or not candidate.is_file():
                continue
            seen.add(candidate)
            yield candidate


def stable_hash(value: Any) -> str:
    blob = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8", "replace")
    return hashlib.sha1(blob).hexdigest()


def event_type(obj: dict[str, Any]) -> str:
    payload = obj.get("payload")
    if isinstance(payload, dict) and isinstance(payload.get("type"), str):
        return f"{obj.get('type', 'unknown')}:{payload['type']}"
    if isinstance(obj.get("event"), str):
        return f"event:{obj['event']}"
    return str(obj.get("type") or "unknown")


def token_total(obj: dict[str, Any]) -> int | None:
    payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else obj
    info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
    candidates = [
        info.get("last_token_usage"),
        info.get("total_token_usage"),
        info.get("usage"),
        payload.get("last_token_usage"),
        payload.get("token_count"),
        obj.get("token_count"),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict) and isinstance(candidate.get("total_tokens"), int):
            return candidate["total_tokens"]
        if isinstance(candidate, int):
            return candidate
    return None


def scan_file(path: Path, max_lines: int, top: int, sample_chars: int) -> dict[str, Any]:
    events: Counter[str] = Counter()
    parse_errors: list[str] = []
    token_events = 0
    token_total_sum = 0
    token_dedup_sum = 0
    token_seen: set[str] = set()
    consecutive_duplicates = 0
    previous_token_hash: str | None = None
    lines = 0
    try:
        size = path.stat().st_size
    except OSError:
        size = None
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for raw_line in handle:
                if lines >= max_lines:
                    break
                lines += 1
                try:
                    obj = json.loads(raw_line)
                except json.JSONDecodeError as exc:
                    if len(parse_errors) < top:
                        parse_errors.append(f"line {lines}: {exc.msg}: {raw_line[:sample_chars]}")
                    continue
                if not isinstance(obj, dict):
                    events["non_object"] += 1
                    continue
                typ = event_type(obj)
                events[typ] += 1
                if typ.endswith(":token_count"):
                    token_events += 1
                    total = token_total(obj) or 0
                    token_total_sum += total
                    digest = stable_hash(obj.get("payload", obj))
                    if digest not in token_seen:
                        token_seen.add(digest)
                        token_dedup_sum += total
                    if digest == previous_token_hash:
                        consecutive_duplicates += 1
                    previous_token_hash = digest
    except OSError as exc:
        parse_errors.append(f"open failed: {exc}")
    return {
        "path": str(path),
        "bytes": size,
        "lines_scanned": lines,
        "truncated": lines >= max_lines,
        "event_top": events.most_common(top),
        "parse_error_count": len(parse_errors),
        "parse_error_samples": parse_errors,
        "token_count": {
            "events": token_events,
            "unique_payloads": len(token_seen),
            "sum_total_tokens": token_total_sum,
            "dedup_sum_total_tokens": token_dedup_sum,
            "consecutive_duplicates": consecutive_duplicates,
        },
    }


def compare_roots(raw_root: str | None, canonical_root: str | None, glob: str, max_files: int, top: int) -> dict[str, Any] | None:
    if not raw_root or not canonical_root:
        return None
    raw = Path(raw_root).expanduser()
    canonical = Path(canonical_root).expanduser()
    raw_files = {path.relative_to(raw): path for path in sorted(raw.rglob(glob))[:max_files]} if raw.is_dir() else {}
    canonical_files = {path.relative_to(canonical): path for path in sorted(canonical.rglob(glob))[:max_files]} if canonical.is_dir() else {}
    rows: list[dict[str, Any]] = []
    for rel in sorted(set(raw_files) | set(canonical_files)):
        raw_path = raw_files.get(rel)
        canonical_path = canonical_files.get(rel)
        raw_size = raw_path.stat().st_size if raw_path and raw_path.exists() else None
        canonical_size = canonical_path.stat().st_size if canonical_path and canonical_path.exists() else None
        rows.append(
            {
                "relative_path": str(rel),
                "raw_bytes": raw_size,
                "canonical_bytes": canonical_size,
                "state": "both" if raw_path and canonical_path else "raw_only" if raw_path else "canonical_only",
                "ratio": round(raw_size / canonical_size, 3) if raw_size and canonical_size else None,
            }
        )
    rows.sort(key=lambda item: item["raw_bytes"] or item["canonical_bytes"] or 0, reverse=True)
    return {
        "raw_root": str(raw),
        "canonical_root": str(canonical),
        "raw_files_seen": len(raw_files),
        "canonical_files_seen": len(canonical_files),
        "top_differences": rows[:top],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="JSONL files or directories to scan.")
    parser.add_argument("--raw-root", help="Optional raw directory for raw/canonical comparison.")
    parser.add_argument("--canonical-root", help="Optional canonical directory for raw/canonical comparison.")
    parser.add_argument("--glob", default="*.jsonl")
    parser.add_argument("--max-files", type=int, default=500)
    parser.add_argument("--max-lines", type=int, default=200000)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--sample-chars", type=int, default=180)
    parser.add_argument("--jsonl", action="store_true")
    args = parser.parse_args(argv)
    summaries = [scan_file(path, args.max_lines, args.top, args.sample_chars) for path in iter_files(args.paths, args.glob, args.max_files)]
    comparison = compare_roots(args.raw_root, args.canonical_root, args.glob, args.max_files, args.top)
    if args.jsonl:
        for summary in summaries:
            print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        if comparison is not None:
            print(json.dumps({"raw_canonical": comparison}, ensure_ascii=False, sort_keys=True))
    else:
        print(json.dumps({"files": summaries, "raw_canonical": comparison}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
