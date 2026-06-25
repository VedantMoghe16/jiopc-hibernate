"""The OS seam — every external interaction funnels through here.

Centralising subprocess calls, tool discovery and /proc reads in one module
gives us three things the architecture depends on:

  * **Graceful degradation** — a missing tool (wmctrl, xprintidle, notify-send)
    returns an empty / None result instead of raising. The system narrows what
    it can do; it never falls over.
  * **A strict time discipline** — `run()` always takes a timeout and treats a
    timeout the same as a failure. Nothing here can block the save budget.
  * **Testability off-target** — tests (and the `--fake` demo mode) monkeypatch
    this one module to simulate a Linux/X11 box from a Mac.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .log import get_logger

_log = get_logger()


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def have(tool: str) -> bool:
    """True if *tool* is on PATH."""
    return shutil.which(tool) is not None


@dataclass
class RunResult:
    ok: bool
    code: int
    stdout: str
    stderr: str

    @property
    def lines(self) -> list[str]:
        return self.stdout.splitlines()


def run(argv: list[str], timeout: float = 5.0, check: bool = False) -> RunResult:
    """Run a command, returning a RunResult. Never raises (unless check=True).

    A missing binary, a non-zero exit, or a timeout all produce ``ok=False``
    with the error captured. This is the workhorse for wmctrl/xdotool/notify.
    """
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        result = RunResult(proc.returncode == 0, proc.returncode, proc.stdout, proc.stderr)
    except FileNotFoundError:
        result = RunResult(False, 127, "", f"{argv[0]}: not found")
    except subprocess.TimeoutExpired:
        result = RunResult(False, 124, "", f"{argv[0]}: timed out after {timeout}s")
    except OSError as exc:  # permission, ENOMEM, etc.
        result = RunResult(False, 1, "", f"{argv[0]}: {exc}")
    if check and not result.ok:
        raise RuntimeError(f"command failed: {' '.join(argv)} :: {result.stderr.strip()}")
    return result


def spawn(argv: list[str], cwd: str | None = None) -> int | None:
    """Detach-launch a GUI app for restore. Returns the child PID or None.

    Uses start_new_session so the launched app survives the restore process
    exiting, and never inherits our stdio. Failure is logged, not raised — a
    single app that won't relaunch must not abort the restore of the others.
    """
    try:
        proc = subprocess.Popen(
            argv,
            cwd=cwd if (cwd and Path(cwd).is_dir()) else None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return proc.pid
    except (OSError, ValueError) as exc:
        _log.warning("spawn failed for %s: %s", argv[:1], exc)
        return None


# --- /proc introspection ----------------------------------------------------
# Recovers exec path, command line and working directory for a PID without
# root. All readers tolerate a Linux-only /proc being absent (returns None),
# which is what lets the unit tests and the macOS dev loop run.

def proc_cmdline(pid: int) -> list[str] | None:
    """The exact argv of a process, from /proc/<pid>/cmdline (NUL-separated)."""
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return None
    parts = [p.decode("utf-8", "replace") for p in raw.split(b"\x00") if p]
    return parts or None


def proc_exe(pid: int) -> str | None:
    """The executable path, resolved from the /proc/<pid>/exe symlink."""
    try:
        return os.readlink(f"/proc/{pid}/exe")
    except OSError:
        return None


def proc_cwd(pid: int) -> str | None:
    """The working directory, from the /proc/<pid>/cwd symlink.

    This is how a terminal's cwd is recovered for restore — no root needed,
    because a process can always read its own (and same-uid) /proc entries.
    """
    try:
        return os.readlink(f"/proc/{pid}/cwd")
    except OSError:
        return None
