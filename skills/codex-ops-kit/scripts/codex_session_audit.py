#!/usr/bin/env python3
"""Stream Codex rollout JSONL into compact per-file or per-day metrics."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, TextIO


def iter_paths(paths: list[str], glob: str, max_files: int) -> Iterable[Path]:
    seen = 0
    for raw in paths:
        path = Path(raw).expanduser()
        candidates = sorted(path.rglob(glob)) if path.is_dir() else [path]
        for candidate in candidates:
            if seen >= max_files:
                return
            if candidate.is_file():
                seen += 1
                yield candidate


def payload(obj: dict[str, Any]) -> dict[str, Any]:
    value = obj.get("payload")
    return value if isinstance(value, dict) else {}


def token_total(obj: dict[str, Any]) -> int | None:
    info = payload(obj).get("info")
    if not isinstance(info, dict):
        return None
    for key in ("last_token_usage", "total_token_usage"):
        usage = info.get(key)
        if isinstance(usage, dict) and isinstance(usage.get("total_tokens"), int):
            return usage["total_tokens"]
    return None


def add(counter: Counter[str], value: Any) -> None:
    if isinstance(value, str) and value:
        counter[value] += 1


def scan_stream(name: str, handle: TextIO, max_lines: int, keywords: list[str]) -> dict[str, Any]:
    counters: dict[str, Counter[str]] = defaultdict(Counter)
    keyword_hits: Counter[str] = Counter()
    token_events = 0
    token_sum = 0
    token_dedup_sum = 0
    token_seen: set[str] = set()
    parse_errors = 0
    lines = 0
    for raw_line in handle:
        if lines >= max_lines:
            break
        lines += 1
        try:
            obj = json.loads(raw_line)
        except json.JSONDecodeError:
            parse_errors += 1
            continue
        if not isinstance(obj, dict):
            continue
        p = payload(obj)
        add(counters["event"], obj.get("type") or obj.get("event"))
        add(counters["payload_type"], p.get("type"))
        for key in ("cwd", "forked_from_id", "root", "turn_id", "agent_role", "agent_nickname"):
            add(counters[key], p.get(key) or obj.get(key))
        lower_line = raw_line.lower()
        for keyword in keywords:
            if keyword and keyword in lower_line:
                keyword_hits[keyword] += 1
        if p.get("type") == "token_count":
            token_events += 1
            total = token_total(obj) or 0
            token_sum += total
            canonical = json.dumps(p.get("info"), sort_keys=True, separators=(",", ":"))
            if canonical not in token_seen:
                token_seen.add(canonical)
                token_dedup_sum += total
    return {
        "name": name,
        "lines": lines,
        "truncated": lines >= max_lines,
        "parse_errors": parse_errors,
        "token_events": token_events,
        "token_unique": len(token_seen),
        "token_sum": token_sum,
        "token_dedup_sum": token_dedup_sum,
        "top": {key: value.most_common(5) for key, value in counters.items()},
        "keyword_hits": keyword_hits.most_common(),
    }


def summarize_file(path: Path, max_lines: int, keywords: list[str]) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            result = scan_stream(str(path), handle, max_lines, keywords)
        stat = path.stat()
        result["bytes"] = stat.st_size
        result["day"] = path.parent.name if path.parent.name.isdigit() else ""
        return result
    except OSError as exc:
        return {"name": str(path), "error": str(exc), "bytes": None, "day": ""}


def compact(items: list[tuple[str, int]], limit: int) -> str:
    return ",".join(f"{key}:{value}" for key, value in items[:limit])


def group_by_day(rows: list[dict[str, Any]], top: int) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    sizes: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        day = row.get("day") or "unknown"
        target = grouped.setdefault(
            day,
            {
                "name": day,
                "bytes": 0,
                "files": 0,
                "lines": 0,
                "token_sum": 0,
                "token_dedup_sum": 0,
                "token_events": 0,
                "top": defaultdict(Counter),
                "keyword_hits": Counter(),
                "parse_errors": 0,
                "truncated": False,
            },
        )
        target["files"] += 1
        target["bytes"] += row.get("bytes") or 0
        target["lines"] += row.get("lines") or 0
        target["token_sum"] += row.get("token_sum") or 0
        target["token_dedup_sum"] += row.get("token_dedup_sum") or 0
        target["token_events"] += row.get("token_events") or 0
        target["parse_errors"] += row.get("parse_errors") or 0
        target["truncated"] = target["truncated"] or bool(row.get("truncated"))
        if row.get("bytes"):
            sizes[day].append(row["bytes"])
        for key, values in row.get("top", {}).items():
            target["top"][key].update(dict(values))
        target["keyword_hits"].update(dict(row.get("keyword_hits", [])))
    output = []
    for day, row in sorted(grouped.items()):
        byte_sizes = sizes.get(day, [])
        row["p50_bytes"] = int(statistics.median(byte_sizes)) if byte_sizes else 0
        row["max_bytes"] = max(byte_sizes) if byte_sizes else 0
        row["top"] = {key: counter.most_common(top) for key, counter in row["top"].items()}
        row["keyword_hits"] = row["keyword_hits"].most_common(top)
        output.append(row)
    return output


def emit_tsv(rows: list[dict[str, Any]], top: int) -> None:
    print("name\tbytes\tlines\ttokens\tdedup_tokens\ttoken_events\tcwd\tfork\trole\tkeywords\tflags")
    for row in rows:
        flags = []
        if row.get("truncated"):
            flags.append("truncated")
        if row.get("parse_errors"):
            flags.append(f"parse_errors={row['parse_errors']}")
        if row.get("error"):
            flags.append(f"error={row['error']}")
        top_map = row.get("top", {})
        print(
            "\t".join(
                [
                    str(row.get("name", ""))[:120],
                    str(row.get("bytes", "")),
                    str(row.get("lines", "")),
                    str(row.get("token_sum", "")),
                    str(row.get("token_dedup_sum", "")),
                    str(row.get("token_events", "")),
                    compact(top_map.get("cwd", []), top)[:180],
                    compact(top_map.get("forked_from_id", []), top)[:180],
                    compact(top_map.get("agent_role", []), top)[:120],
                    compact(row.get("keyword_hits", []), top)[:120],
                    ",".join(flags),
                ]
            )
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="Files or directories; if omitted, read stdin.")
    parser.add_argument("--glob", default="rollout*.jsonl")
    parser.add_argument("--max-files", type=int, default=1000)
    parser.add_argument("--max-lines", type=int, default=200000)
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--keywords", default="", help="Comma-separated case-insensitive keywords.")
    parser.add_argument("--format", choices=["tsv", "jsonl"], default="tsv")
    parser.add_argument("--group", choices=["file", "day"], default="file")
    args = parser.parse_args(argv)
    keywords = [item.strip().lower() for item in args.keywords.split(",") if item.strip()]
    if args.paths:
        rows = [summarize_file(path, args.max_lines, keywords) for path in iter_paths(args.paths, args.glob, args.max_files)]
    else:
        rows = [scan_stream("stdin", sys.stdin, args.max_lines, keywords)]
    if args.group == "day":
        rows = group_by_day(rows, args.top)
    if args.format == "jsonl":
        for row in rows:
            print(json.dumps(row, ensure_ascii=False, sort_keys=True))
    else:
        emit_tsv(rows, args.top)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
