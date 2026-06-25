"""Component E — the restore flow that runs at login (XDG autostart).

Sequence (spec §1.1 Component E and §1 steps 5-7):

    1. read session-state.json
    2. absent          → nothing to do, exit 0
    3. stale (>thresh) → discard silently, no prompt
    4. recent          → notify "Restore previous session? [Restore][Dismiss]"
    5. dismiss         → relaunch nothing
    6. restore         → relaunch each app with its handler + best-effort
                         geometry, staggered, collecting a per-app report
    7. always          → rename the file to session-state-last.json so it
                         cannot re-trigger; show a partial-restore summary

The cardinal rule: **the desktop session must never crash.** Every app
relaunch is independently guarded; one failure is logged and recorded in the
report, and the flow continues to the next app.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import geometry, notify, state as state_mod
from .config import Config
from .handlers import Registry
from .log import get_logger
from .notify import Choice
from .state import SessionState, WindowState

_log = get_logger()


@dataclass
class AppResult:
    app_name: str
    handler: str
    launched: bool
    in_app_restore: bool
    geometry_applied: bool
    detail: str = ""


@dataclass
class RestoreReport:
    outcome: str                       # restored | dismissed | stale | empty | absent
    total: int = 0
    launched: int = 0
    failed: int = 0
    results: list[AppResult] = field(default_factory=list)

    def summary_line(self) -> str:
        if self.outcome == "restored":
            msg = f"Restored {self.launched} of {self.total} app(s)."
            if self.failed:
                names = ", ".join(r.app_name for r in self.results if not r.launched)
                msg += f" Could not reopen: {names} — please reopen manually."
            return msg
        return {
            "dismissed": "Previous session was not restored.",
            "stale": "Previous session was too old to restore.",
            "empty": "No applications to restore.",
            "absent": "No saved session found.",
        }.get(self.outcome, "Restore finished.")


def run_restore(
    cfg: Config | None = None,
    registry: Registry | None = None,
    auto_yes: bool = False,
    now: float | None = None,
) -> RestoreReport:
    """Entry point for the autostart restore service. Never raises."""
    cfg = cfg or Config.load()
    registry = registry or Registry.load()

    session = state_mod.read_state()
    if session is None:
        _log.info("no session-state.json present; nothing to restore")
        return RestoreReport(outcome="absent")

    # Stale → discard silently (no prompt), but still consume so it can't linger.
    if session.is_stale(cfg.staleness_threshold_s, now=now):
        age = session.age_seconds(now)
        _log.info("session state is stale (age=%.0fs > %ds); discarding silently",
                  age or -1, cfg.staleness_threshold_s)
        state_mod.mark_consumed()
        return RestoreReport(outcome="stale")

    if not session.windows:
        state_mod.mark_consumed()
        return RestoreReport(outcome="empty")

    # Confirmation gate (spec: a prompt must appear before any relaunch).
    if not auto_yes:
        choice = notify.ask_restore(
            summary="Restore your previous session?",
            body=_prompt_body(session),
            timeout_s=cfg.restore_prompt_timeout_s,
        )
        if choice is not Choice.YES:
            _log.info("user dismissed restore; relaunching nothing")
            state_mod.mark_consumed()
            return RestoreReport(outcome="dismissed", total=len(session.windows))

    report = _relaunch_all(session, cfg, registry)

    # Consume the file last, so a crash mid-restore still leaves it for a retry.
    state_mod.mark_consumed()
    notify.info("JioPC — session restored", report.summary_line())
    _log.info("restore complete: %s", report.summary_line())
    return report


def _relaunch_all(session: SessionState, cfg: Config, registry: Registry) -> RestoreReport:
    from . import windows as win_mod
    report = RestoreReport(outcome="restored", total=len(session.windows))
    claimed = geometry.current_window_ids() if cfg.restore_geometry else set()
    # Read the *current* screen once — geometry is clamped to it (the new VM
    # may run at a different resolution than the one we saved on).
    screen = win_mod.display_geometry() if cfg.restore_geometry else None

    for ws in session.windows:
        result = _relaunch_one(ws, cfg, registry, claimed, screen)
        report.results.append(result)
        if result.launched:
            report.launched += 1
        else:
            report.failed += 1
        if cfg.relaunch_stagger_ms:
            time.sleep(cfg.relaunch_stagger_ms / 1000.0)

    return report


def _relaunch_one(ws: WindowState, cfg: Config, registry: Registry,
                  claimed: set, screen: dict | None) -> AppResult:
    """Relaunch a single app under guard; record exactly what happened."""
    from . import system
    handler = registry.restore_handler_for(ws.handler)
    try:
        argv = handler.restore_command(ws)
    except Exception as exc:
        argv = None
        _log.warning("handler %s failed building command for %s: %s", ws.handler, ws.app_name, exc)

    if not argv:
        _log.info("skipping %s: nothing to launch (no exec path)", ws.app_name)
        return AppResult(ws.app_name, ws.handler, False, False, False, "no executable")

    pid = system.spawn(argv, cwd=ws.extra.get("cwd"))
    if pid is None:
        return AppResult(ws.app_name, ws.handler, False, ws.restore_supported, False, "spawn failed")

    geo_applied = False
    if cfg.restore_geometry and ws.geometry:
        wid = geometry.find_window(ws.wm_class, claimed, timeout=4.0)
        if wid:
            claimed.add(wid)
            geo_applied = geometry.move_resize(wid, ws.geometry, screen=screen)

    _log.info("relaunched %s (handler=%s, in-app=%s, geometry=%s)",
              ws.app_name, ws.handler, ws.restore_supported, geo_applied)
    return AppResult(ws.app_name, ws.handler, True, ws.restore_supported, geo_applied)


def _prompt_body(session: SessionState) -> str:
    n = len(session.windows)
    apps = ", ".join(dict.fromkeys(w.app_name for w in session.windows))
    unsaved = sum(1 for w in session.windows if w.unsaved)
    body = f"{n} app(s) from your last session: {apps}."
    if unsaved:
        body += f" ({unsaved} had unsaved work.)"
    return body
