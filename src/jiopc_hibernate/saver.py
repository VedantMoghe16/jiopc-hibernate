"""Component B — capture the running session within the time budget.

The save is a strict, bounded pipeline:

    enumerate windows  →  per-window capture (handler-driven)  →  app-wide
    pre-save hooks (e.g. Chrome flush)  →  atomic write of session-state.json

A monotonic deadline (config.save_time_budget_ms, default 10 s) governs the
whole thing. If capture runs long — a wedged /proc, hundreds of windows — we
stop early, write what we have, and flag ``budget_exceeded``. The function is
designed so that *partial* state is always better than none, and so it can
never block the session teardown that called it.

Nothing here raises to the caller: a total failure still returns a (possibly
empty) SessionState that gets written, because "no windows" is itself useful
information to the restore step.
"""

from __future__ import annotations

import socket
import time

from . import state as state_mod
from . import windows as win_mod
from .config import Config
from .handlers import Registry
from .log import get_logger
from .state import SessionState

_log = get_logger()

# Triggers on which the session is genuinely ending, so destructive app-wide
# hooks (Chrome clean-shutdown) are safe to run. A speculative inactivity save
# must NOT kill the user's apps — they may still be sitting at the machine.
_TERMINAL_TRIGGERS = (state_mod.TRIGGER_SESSION_END, state_mod.TRIGGER_USER_DISCONNECT)


def save_session(
    trigger: str,
    cfg: Config | None = None,
    registry: Registry | None = None,
    now: float | None = None,
) -> SessionState:
    """Capture and persist the session. Returns the state that was written."""
    cfg = cfg or Config.load()
    registry = registry or Registry.load()
    started = time.monotonic()
    wall_now = now if now is not None else time.time()
    deadline = started + cfg.save_time_budget_s

    session = SessionState(
        trigger=trigger,
        saved_at=state_mod.utc_now_iso(wall_now),
        hostname=_hostname(),
        time_budget_ms=cfg.save_time_budget_ms,
        display=win_mod.display_geometry(),
    )

    raw_windows = win_mod.enumerate_windows(timeout=min(cfg.save_time_budget_s, 3.0))
    captured: list[win_mod.Window] = []
    budget_exceeded = False

    for win in raw_windows:
        if time.monotonic() > deadline:
            budget_exceeded = True
            _log.warning("save budget exhausted after %d window(s); stopping", len(captured))
            break
        if _is_ignored(win, cfg):
            continue
        try:
            handler = registry.match(win)
            session.windows.append(handler.capture(win))
            captured.append(win)
        except Exception as exc:  # one bad window must not abort the rest
            _log.warning("capture failed for window %s: %s", win.wid, exc)

    # App-wide pre-save hooks (Chrome flush) — only when the session is really
    # ending, and only if time remains, and never on a speculative idle save.
    if trigger in _TERMINAL_TRIGGERS and cfg.chrome_clean_shutdown and time.monotonic() < deadline:
        for hook in registry.pre_save_hooks():
            try:
                hook.pre_save(captured)
            except Exception as exc:
                _log.warning("pre-save hook %s failed: %s", hook.name, exc)

    session.budget_exceeded = budget_exceeded
    session.save_duration_ms = int((time.monotonic() - started) * 1000)

    existing = _recent_non_empty_state_to_keep(session, cfg, now=wall_now)
    if existing is not None:
        _log.info(
            "skipping empty %s save: keeping existing non-empty state with %d window(s)",
            trigger, len(existing.windows),
        )
        return existing

    # History snapshot (bonus) happens before we overwrite the live file.
    try:
        state_mod.rotate_history(cfg.history_depth, epoch=wall_now)
    except Exception as exc:
        _log.warning("history rotation failed: %s", exc)

    try:
        state_mod.write_state(session)
    except Exception as exc:
        _log.error("FAILED to write session state: %s", exc)

    _log.info(
        "save complete: trigger=%s windows=%d duration=%dms budget=%dms exceeded=%s",
        trigger, len(session.windows), session.save_duration_ms,
        cfg.save_time_budget_ms, budget_exceeded,
    )
    return session


def _recent_non_empty_state_to_keep(
    candidate: SessionState,
    cfg: Config,
    now: float,
) -> SessionState | None:
    """Protect a good early logout save from a later empty teardown save.

    The LXQt leave wrapper saves synchronously before windows are closed. A
    guard process can still receive SIGTERM later during session teardown, at
    which point `wmctrl` may see zero windows. That empty terminal save must
    not rotate the good file into history and replace the restore target.
    """
    if candidate.windows:
        return None
    if candidate.trigger not in _TERMINAL_TRIGGERS:
        return None
    existing = state_mod.read_state()
    if existing is None or not existing.windows:
        return None
    if existing.is_stale(cfg.staleness_threshold_s, now=now):
        return None
    return existing


def _hostname() -> str:
    try:
        return socket.gethostname()
    except OSError:
        return ""


def _is_ignored(win: win_mod.Window, cfg: Config) -> bool:
    """Skip our own shell, panels, and desktop-background windows.

    Name-based patterns match wm_class/exec/argv0 only — never the full
    cmdline — so a single-instance app (e.g. pcmanfm-qt, which serves the
    desktop *and* file windows from one PID with a shared `--desktop`
    cmdline) doesn't have its real windows dropped. The desktop-background
    window is filtered separately, by its title.
    """
    argv0 = win.cmdline[0] if win.cmdline else ""
    name_hay = " ".join(filter(None, [win.wm_class, win.exe, argv0])).lower()
    if any(pat.lower() in name_hay for pat in cfg.ignore_patterns):
        return True
    title = (win.title or "").lower()
    if any(pat.lower() in title for pat in cfg.ignore_title_patterns):
        return True
    return False
