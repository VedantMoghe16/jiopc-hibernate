"""Runtime configuration — every tunable the spec calls "configurable".

Defaults match the challenge spec exactly:
  * save time budget        10 seconds
  * staleness threshold     24 hours
  * restore history depth   3 sessions (bonus)

A user (or the Gold Image) may override any field by dropping a JSON file at
``$XDG_CONFIG_HOME/jiopc-hibernate/config.json``. Unknown keys are ignored;
malformed files fall back to defaults with a logged warning — configuration
must never be a reason a session fails to save.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

from . import paths

CONFIG_NAME = "config.json"


@dataclass
class Config:
    # --- Component A: the trigger -------------------------------------------
    #: Hard ceiling on the whole save. The hook abandons remaining work past
    #: this so it never blocks session teardown (spec: default 10 s).
    save_time_budget_ms: int = 10_000
    #: Per-window capture timeout, so one wedged /proc read can't eat the budget.
    per_window_timeout_ms: int = 1_500
    #: Idle seconds before the guard fires an inactivity_timeout save. The guard
    #: only *saves*; it never locks or logs the user out (that stays the DE's job).
    idle_timeout_s: int = 600
    #: How often the guard samples idle time.
    idle_poll_interval_s: int = 15

    # --- Component E: the restore flow --------------------------------------
    #: Older than this and the state is discarded silently — no prompt
    #: (spec: default 24 h).
    staleness_threshold_s: int = 24 * 3600
    #: Seconds to wait for the user to answer the restore prompt before
    #: treating it as a dismiss (so a headless/unattended login never hangs).
    restore_prompt_timeout_s: int = 60
    #: Stagger between app relaunches (gives Chrome/X time to settle, keeps the
    #: 4-vCPU VM from thrashing on a burst of process spawns).
    relaunch_stagger_ms: int = 400
    #: Keep the last N session-state files for "restore from an earlier
    #: session" (bonus). 1 disables history.
    history_depth: int = 3
    #: Apply saved window geometry on restore (best-effort, needs wmctrl).
    restore_geometry: bool = True

    # --- behaviour switches -------------------------------------------------
    #: Send Chrome a clean-shutdown signal on save so it flushes its session.
    chrome_clean_shutdown: bool = True
    #: WM_CLASS / executable substrings that are never captured (the shell
    #: itself, panels, the restore prompt — restoring them is meaningless).
    ignore_patterns: list[str] = field(
        default_factory=lambda: [
            "lxqt-panel", "pcmanfm-qt --desktop", "lxqt-runner", "xfdesktop",
            "plank", "conky", "jiopc-home", "jiopc-hibernate", "lxqt-notificationd",
        ]
    )

    @classmethod
    def load(cls, config_file: Path | None = None) -> "Config":
        """Load config, overlaying any on-disk JSON over the defaults."""
        cfg = cls()
        path = config_file or (paths.config_dir() / CONFIG_NAME)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cfg
        except (OSError, ValueError):
            # Malformed config is non-fatal: defaults keep the system working.
            return cfg
        known = {f for f in cfg.__dataclass_fields__}
        for key, value in raw.items():
            if key in known:
                setattr(cfg, key, value)
        return cfg

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def save_time_budget_s(self) -> float:
        return self.save_time_budget_ms / 1000.0

    @property
    def per_window_timeout_s(self) -> float:
        return self.per_window_timeout_ms / 1000.0
