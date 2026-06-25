"""Filesystem locations — XDG-compliant, home-directory-only, roams across VMs.

Every path the system touches lives under the user's *persistent* home
directory so it survives VM reassignment (the home is NFS-mounted and follows
the user; the VM does not). Nothing is written to machine-local paths.

All locations honour the XDG environment variables and a single override,
``JIOPC_HIBERNATE_HOME``, which relocates the entire data tree. The override
is what makes the system testable off-target (and lets a demo run in a
sandbox without touching the real ~/.local/share).

    State   ~/.local/share/jiopc/hibernate/        ($XDG_DATA_HOME/jiopc/hibernate)
    Config  ~/.config/jiopc-hibernate/             ($XDG_CONFIG_HOME/jiopc-hibernate)
    Logs    ~/.local/share/jiopc/hibernate/logs/
"""

from __future__ import annotations

import os
from pathlib import Path

#: The canonical state filename. The restore service consumes this and then
#: renames it to LAST_STATE_NAME so it never re-triggers.
STATE_NAME = "session-state.json"
LAST_STATE_NAME = "session-state-last.json"
#: Restore-history files are named session-state-<epoch>.json (bonus goal).
HISTORY_GLOB = "session-state-*.json"


def _env_path(var: str) -> Path | None:
    value = os.environ.get(var)
    return Path(value).expanduser() if value else None


def home() -> Path:
    """Root of the hibernate data tree (state + logs).

    Resolution order:
      1. ``JIOPC_HIBERNATE_HOME`` (test / demo override)
      2. ``$XDG_DATA_HOME/jiopc/hibernate``
      3. ``~/.local/share/jiopc/hibernate``
    """
    override = _env_path("JIOPC_HIBERNATE_HOME")
    if override:
        return override
    data_home = _env_path("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    return data_home / "jiopc" / "hibernate"


def config_dir() -> Path:
    """Directory holding config.json and handlers.json (user overrides)."""
    override = _env_path("JIOPC_HIBERNATE_CONFIG")
    if override:
        return override
    config_home = _env_path("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return config_home / "jiopc-hibernate"


def state_file() -> Path:
    return home() / STATE_NAME


def last_state_file() -> Path:
    return home() / LAST_STATE_NAME


def log_dir() -> Path:
    return home() / "logs"


def log_file() -> Path:
    return log_dir() / "hibernate.log"


def ensure_dirs() -> None:
    """Create the data + log directories. Best-effort; never raises."""
    for path in (home(), log_dir()):
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
