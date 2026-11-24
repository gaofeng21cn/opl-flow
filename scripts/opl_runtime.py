"""Shared runtime primitives for OPL Flow scripts (zero Fleet imports).

Consolidates project venv discovery, UTC timestamp helpers, atomic file I/O,
cross-platform FileLock, plistlib XML rendering, python-frontmatter parsing,
tenacity retry helpers, and Pydantic validation adapters.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import os
import plistlib
import shutil
import site
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterator, TypeVar

T = TypeVar("T")

_REQUIRED_THIRD_PARTY_MODULES = ("filelock", "frontmatter", "pydantic", "tenacity", "typer")


def _site_packages_dir(venv_root: Path) -> Path | None:
    if not venv_root.is_dir():
        return None
    ver = f"python{sys.version_info.major}.{sys.version_info.minor}"
    for site_dir in (venv_root / "lib" / ver / "site-packages", venv_root / "Lib" / "site-packages"):
        if site_dir.is_dir():
            return site_dir
    return None


def _all_third_party_modules_available() -> bool:
    for module_name in _REQUIRED_THIRD_PARTY_MODULES:
        try:
            __import__(module_name)
        except ModuleNotFoundError:
            return False
    return True


def _find_uv_binary() -> str | None:
    found = shutil.which("uv")
    if found:
        return found
    for candidate in (
        Path(sys.executable).with_name("uv"),
        Path.home() / ".local" / "bin" / "uv",
        Path("/opt/homebrew/bin/uv"),
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _ensure_cached_uv_venv(repo_root: Path) -> Path | None:
    pyproject = repo_root / "pyproject.toml"
    lockfile = repo_root / "uv.lock"
    if not pyproject.is_file() or not lockfile.is_file():
        return None
    lock_hash = hashlib.sha256(lockfile.read_bytes()).hexdigest()[:12]
    cache_env = os.environ.get("OPL_FLOW_VENV_CACHE_DIR", "").strip()
    cache_root = Path(cache_env).expanduser() if cache_env else (Path.home() / ".cache" / "opl-flow" / "venvs")
    target_venv = cache_root / f"py{sys.version_info.major}.{sys.version_info.minor}-{lock_hash}"
    existing_site = _site_packages_dir(target_venv)
    if existing_site is not None:
        return existing_site
    uv_bin = _find_uv_binary()
    if not uv_bin:
        return None
    cache_root.mkdir(parents=True, exist_ok=True)
    staging_venv = Path(tempfile.mkdtemp(prefix=f".staging-{lock_hash}-", dir=str(cache_root)))
    try:
        synced = False
        for extra_flags in (["--offline"], []):
            env = {**os.environ, "UV_PROJECT_ENVIRONMENT": str(staging_venv)}
            res = subprocess.run(
                [
                    uv_bin,
                    "sync",
                    "--frozen",
                    "--no-dev",
                    "--no-progress",
                    "--python",
                    sys.executable,
                    *extra_flags,
                ],
                cwd=str(repo_root),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=90,
                check=False,
            )
            if res.returncode == 0 and _site_packages_dir(staging_venv) is not None:
                synced = True
                break
        if synced:
            try:
                staging_venv.rename(target_venv)
            except OSError:
                pass
    except (OSError, subprocess.SubprocessError):
        pass
    finally:
        if staging_venv.exists():
            shutil.rmtree(staging_venv, ignore_errors=True)
    return _site_packages_dir(target_venv)


def bootstrap_venv() -> None:
    """Attach a project .venv or uv.lock cached venv site-packages when invoked under bare python3."""
    if _all_third_party_modules_available():
        return
    repo_root = Path(__file__).resolve().parent.parent
    for site_dir in (_site_packages_dir(repo_root / ".venv"), _ensure_cached_uv_venv(repo_root)):
        if site_dir is not None:
            if str(site_dir) not in sys.path:
                site.addsitedir(str(site_dir))
            if _all_third_party_modules_available():
                return


bootstrap_venv()

from filelock import FileLock, Timeout as FileLockTimeout  # noqa: E402
import frontmatter  # noqa: E402
from pydantic import BaseModel, ValidationError  # noqa: E402
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential  # noqa: E402


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso_utc(value: dt.datetime, *, drop_microseconds: bool = False) -> str:
    normalized = value.astimezone(dt.timezone.utc)
    if drop_microseconds:
        normalized = normalized.replace(microsecond=0)
    return normalized.isoformat().replace("+00:00", "Z")


def parse_utc(
    value: Any,
    *,
    error_cls: type[Exception] = ValueError,
    require_timezone: bool = False,
    allow_none: bool = False,
    error_message: str | None = None,
) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        if allow_none:
            return None
        raise error_cls(error_message or "timestamp must be a non-empty ISO-8601 string")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError as exc:
        if allow_none:
            return None
        raise error_cls(error_message or f"invalid ISO-8601 timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        if require_timezone:
            if allow_none:
                return None
            raise error_cls(error_message or "timestamp must include a timezone")
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def chmod_best_effort(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def ensure_private_dir(path: Path, *, mode: int = 0o700) -> None:
    path.mkdir(parents=True, exist_ok=True)
    chmod_best_effort(path, mode)


def atomic_write_text(
    path: Path,
    text: str,
    *,
    mode: int | None = 0o600,
    preserve_mode: bool = False,
    fsync: bool = True,
    fsync_dir: bool = False,
    private_dir: bool = False,
) -> None:
    if private_dir:
        ensure_private_dir(path.parent)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
    effective_mode = mode
    if preserve_mode:
        effective_mode = path.stat().st_mode if path.exists() and not path.is_symlink() else (mode if mode is not None else 0o644)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            if fsync:
                handle.flush()
                os.fsync(handle.fileno())
        if effective_mode is not None:
            os.chmod(temp_path, effective_mode)
        os.replace(temp_path, path)
        if fsync_dir and hasattr(os, "O_RDONLY"):
            try:
                dir_fd = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                pass
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def atomic_write_json(
    path: Path,
    payload: Any,
    *,
    mode: int = 0o600,
    sort_keys: bool = True,
    ensure_ascii: bool = False,
    fsync: bool = True,
    fsync_dir: bool = False,
    private_dir: bool = False,
) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=sort_keys, ensure_ascii=ensure_ascii) + "\n"
    atomic_write_text(
        path,
        rendered,
        mode=mode,
        fsync=fsync,
        fsync_dir=fsync_dir,
        private_dir=private_dir,
    )


def read_json_object(
    path: Path,
    *,
    error_cls: type[Exception] = ValueError,
    label: str | None = None,
) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise error_cls(f"{label or 'JSON file'} is unreadable: {path}") from exc
    if not isinstance(payload, dict):
        raise error_cls(f"expected JSON object: {path}")
    return payload


def run_with_retry(
    fn: Callable[[], T],
    *,
    attempts: int = 4,
    min_wait: float = 0.02,
    max_wait: float = 0.25,
    retry_on: tuple[type[BaseException], ...] = (OSError, sqlite3.OperationalError, FileLockTimeout),
) -> T:
    retrying = Retrying(
        stop=stop_after_attempt(max(1, attempts)),
        wait=wait_exponential(multiplier=min_wait, min=min_wait, max=max_wait),
        retry=retry_if_exception_type(retry_on),
        reraise=True,
    )
    return retrying(fn)


@contextlib.contextmanager
def file_lock(
    lock_path: Path,
    *,
    timeout: float = 30.0,
    private_dir: bool = False,
    mode: int = 0o600,
) -> Iterator[None]:
    """Cross-platform exclusive file lock backed by filelock.FileLock + tenacity."""
    resolved = lock_path.expanduser().resolve()
    if private_dir:
        ensure_private_dir(resolved.parent)
    else:
        resolved.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(resolved), mode=mode, timeout=timeout)
    run_with_retry(
        lambda: lock.acquire(timeout=timeout),
        attempts=3,
        min_wait=0.05,
        max_wait=0.3,
        retry_on=(FileLockTimeout, OSError),
    )
    chmod_best_effort(resolved, mode)
    try:
        yield
    finally:
        lock.release()


def render_plist_xml(payload: dict[str, Any]) -> str:
    """Render an Apple XML property list using stdlib plistlib."""
    return plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=True).decode("utf-8")


def split_frontmatter(text: str) -> tuple[str, str]:
    """Split raw YAML frontmatter prefix and body via python-frontmatter.

    Preserves exact frontmatter text and body formatting while degrading
    gracefully on missing or unclosed frontmatter blocks.
    """
    handler = frontmatter.YAMLHandler()
    if not handler.detect(text):
        return "", text
    try:
        _, content = handler.split(text)
    except ValueError:
        return "", text
    if content.startswith("\r\n"):
        body = content[2:]
    elif content.startswith("\n"):
        body = content[1:]
    else:
        body = content
    prefix_len = len(text) - len(body)
    return text[:prefix_len], body


def strip_frontmatter(text: str) -> str:
    """Return Markdown body without its leading YAML frontmatter block."""
    _, body = split_frontmatter(text)
    return body


def validate_model(
    model_cls: type[BaseModel],
    data: Any,
    *,
    error_cls: type[Exception],
    message: str | None = None,
) -> BaseModel:
    """Validate data against a Pydantic v2 model and map errors to domain exceptions."""
    try:
        return model_cls.model_validate(data)
    except ValidationError as exc:
        if message is not None:
            raise error_cls(message) from exc
        first = exc.errors()[0] if exc.errors() else None
        if first and isinstance(first.get("msg"), str):
            detail = first["msg"].removeprefix("Value error, ")
            raise error_cls(detail) from exc
        raise error_cls(str(exc)) from exc
