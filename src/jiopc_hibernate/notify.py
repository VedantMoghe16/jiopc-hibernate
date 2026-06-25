"""User-facing notifications — the "Restore your previous session?" prompt.

The spec requires a notification with a [Yes]/[Dismiss] choice *before* any
app is relaunched, and that an unattended login never hangs or relaunches
without consent. We implement a degradation ladder:

  1. ``notify-send --wait --action`` (libnotify ≥ 0.8, the LxQt notification
     daemon) — a native desktop notification with action buttons; the chosen
     action id comes back on stdout.
  2. ``zenity`` / ``kdialog`` question dialog — a graphical fallback.
  3. headless / nothing available — default to **dismiss** (never relaunch
     without an explicit yes; never block).

`info()` is the fire-and-forget channel for the post-restore summary report.
"""

from __future__ import annotations

from enum import Enum

from . import system
from .log import get_logger

_log = get_logger()

_APP = "JioPC Session Hibernate"
_ICON = "document-open-recent"


class Choice(str, Enum):
    YES = "yes"
    DISMISS = "dismiss"


def ask_restore(summary: str, body: str, timeout_s: int) -> Choice:
    """Show the restore prompt and return the user's choice (default DISMISS)."""
    for backend in (_ask_notify_send, _ask_zenity, _ask_kdialog):
        result = backend(summary, body, timeout_s)
        if result is not None:
            _log.info("restore prompt answered via %s: %s", backend.__name__, result.value)
            return result
    _log.info("no interactive prompt backend available; defaulting to dismiss")
    return Choice.DISMISS


def info(summary: str, body: str = "") -> None:
    """Fire-and-forget desktop notification (the partial-restore report)."""
    if system.have("notify-send"):
        system.run(["notify-send", "-a", _APP, "-i", _ICON, summary, body], timeout=3.0)
    else:
        _log.info("notify: %s — %s", summary, body)


# --- backends ---------------------------------------------------------------

def _ask_notify_send(summary: str, body: str, timeout_s: int) -> Choice | None:
    if not system.have("notify-send"):
        return None
    argv = [
        "notify-send", "--wait", "-a", _APP, "-i", _ICON,
        "--action=yes=Restore", "--action=dismiss=Dismiss",
        "--expire-time", str(timeout_s * 1000),
        summary, body,
    ]
    # +5s so our subprocess timeout outlives notify-send's own expiry.
    res = system.run(argv, timeout=timeout_s + 5)
    if not res.ok:
        # Old notify-send lacks --action/--wait → signal "try next backend".
        if "action" in res.stderr.lower() or res.code == 127 or "wait" in res.stderr.lower():
            return None
        return Choice.DISMISS
    return Choice.YES if res.stdout.strip() == "yes" else Choice.DISMISS


def _ask_zenity(summary: str, body: str, timeout_s: int) -> Choice | None:
    if not system.have("zenity"):
        return None
    argv = [
        "zenity", "--question", "--title", _APP,
        "--text", f"{summary}\n\n{body}",
        "--ok-label=Restore", "--cancel-label=Dismiss",
        "--timeout", str(timeout_s),
    ]
    res = system.run(argv, timeout=timeout_s + 5)
    # zenity: exit 0 = OK/Restore, 1 = cancel, 5 = timeout.
    return Choice.YES if res.code == 0 else Choice.DISMISS


def _ask_kdialog(summary: str, body: str, timeout_s: int) -> Choice | None:
    if not system.have("kdialog"):
        return None
    argv = ["kdialog", "--title", _APP, "--yesno", f"{summary}\n\n{body}",
            "--yes-label", "Restore", "--no-label", "Dismiss"]
    res = system.run(argv, timeout=timeout_s + 5)
    return Choice.YES if res.code == 0 else Choice.DISMISS
