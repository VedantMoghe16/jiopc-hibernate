"""Component D — the session-state.json document: schema, I/O, lifecycle.

This module owns the on-disk format and *only* the format. It knows nothing
about wmctrl or notify-send. That separation is what lets the schema be
documented, versioned and tested in isolation (see SCHEMA.md and the tests).

Lifecycle of the file on disk:

    save     ── writes session-state.json atomically (temp + os.replace)
    restore  ── reads it, then renames to session-state-last.json so it
                cannot re-trigger on the next login
    history  ── prior states are kept as session-state-<epoch>.json, newest
                `history_depth` retained (bonus: "restore from an earlier
                session")
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

from . import paths
from .log import get_logger

_log = get_logger()

SCHEMA_VERSION = 1

# Recognised trigger values (Component A). Free-form strings are tolerated on
# read, but the saver only ever writes one of these.
TRIGGER_INACTIVITY = "inactivity_timeout"
TRIGGER_USER_DISCONNECT = "user_disconnect"
TRIGGER_SESSION_END = "session_end"
TRIGGER_MANUAL = "manual"


def utc_now_iso(epoch: float | None = None) -> str:
    """ISO-8601 UTC timestamp (Z-suffixed) for `saved_at`."""
    ts = epoch if epoch is not None else time.time()
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str) -> float | None:
    """Parse a `saved_at` string back to epoch seconds; None if unparseable."""
    try:
        dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, TypeError):
        return None


@dataclass
class WindowState:
    """One captured window — the unit the restore service replays."""
    app_name: str
    exec: str | None
    cmdline: list[str] = field(default_factory=list)
    handler: str = "generic"
    restore_args: list[str] = field(default_factory=list)
    geometry: dict | None = None          # {"x","y","width","height"}
    desktop: int = -1
    wm_class: str = ""
    pid: int = 0
    title: str = ""
    unsaved: bool = False
    restore_supported: bool = False
    extra: dict = field(default_factory=dict)   # handler-specific in-app state

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "WindowState":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class SessionState:
    """The whole captured session — serialises 1:1 to session-state.json."""
    trigger: str
    saved_at: str
    schema_version: int = SCHEMA_VERSION
    hostname: str = ""
    save_duration_ms: int = 0
    time_budget_ms: int = 0
    budget_exceeded: bool = False
    display: dict | None = None
    windows: list[WindowState] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["window_count"] = len(self.windows)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "SessionState":
        wins = [WindowState.from_dict(w) for w in d.get("windows", [])]
        return cls(
            trigger=d.get("trigger", "unknown"),
            saved_at=d.get("saved_at", ""),
            schema_version=d.get("schema_version", SCHEMA_VERSION),
            hostname=d.get("hostname", ""),
            save_duration_ms=d.get("save_duration_ms", 0),
            time_budget_ms=d.get("time_budget_ms", 0),
            budget_exceeded=d.get("budget_exceeded", False),
            display=d.get("display"),
            windows=wins,
        )

    def age_seconds(self, now: float | None = None) -> float | None:
        saved = parse_iso(self.saved_at)
        if saved is None:
            return None
        return (now if now is not None else time.time()) - saved

    def is_stale(self, threshold_s: int, now: float | None = None) -> bool:
        """True if older than the configurable threshold (default 24 h)."""
        age = self.age_seconds(now)
        if age is None:
            return True  # unparseable timestamp → treat as stale, discard
        return age > threshold_s


# --- atomic file I/O --------------------------------------------------------

def write_state(state: SessionState, target: Path | None = None) -> Path:
    """Write the state atomically (temp file + os.replace) so a save that is
    interrupted by session teardown never leaves a half-written file that
    would poison the next restore."""
    paths.ensure_dirs()
    path = target or paths.state_file()
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = json.dumps(state.to_dict(), indent=2, ensure_ascii=False)
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)  # atomic on POSIX within the same filesystem
    _log.info("wrote session state: %d window(s) -> %s", len(state.windows), path)
    return path


def read_state(path: Path | None = None) -> SessionState | None:
    """Read and parse a state file; None if absent or unparseable."""
    path = path or paths.state_file()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        _log.warning("could not read state %s: %s", path, exc)
        return None
    return SessionState.from_dict(raw)


def rotate_history(history_depth: int, epoch: float | None = None) -> None:
    """Snapshot the current state into history and prune to `history_depth`.

    Called by the saver *before* overwriting session-state.json. With
    history_depth <= 1 this is a no-op (history disabled).
    """
    if history_depth <= 1:
        return
    current = paths.state_file()
    if not current.exists():
        return
    stamp = int(epoch if epoch is not None else time.time())
    snapshot = paths.home() / f"session-state-{stamp}.json"
    try:
        snapshot.write_bytes(current.read_bytes())
    except OSError as exc:
        _log.warning("history snapshot failed: %s", exc)
        return
    _prune_history(history_depth)


def list_history() -> list[Path]:
    """Newest-first list of retained history snapshots."""
    try:
        snaps = sorted(
            paths.home().glob("session-state-[0-9]*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return []
    return snaps


def _prune_history(history_depth: int) -> None:
    keep = max(history_depth - 1, 0)  # current file counts as one slot
    for old in list_history()[keep:]:
        try:
            old.unlink()
        except OSError:
            pass


def mark_consumed(path: Path | None = None) -> None:
    """Rename session-state.json → session-state-last.json post-restore so it
    never re-triggers (spec Component E, step 5)."""
    src = path or paths.state_file()
    if not src.exists():
        return
    dst = paths.last_state_file()
    try:
        os.replace(src, dst)
        _log.info("marked state consumed: %s -> %s", src.name, dst.name)
    except OSError as exc:
        _log.warning("could not mark state consumed: %s", exc)
