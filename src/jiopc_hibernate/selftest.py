"""Offline end-to-end self-test — proves the save→restore loop with no X11.

Runs entirely in a temporary data home with fabricated windows, so it works
on the CI box and the macOS dev machine where there is no display, no wmctrl
and no /proc. It exercises the real saver, real registry, real state I/O and
real restore service — only the OS seam (window list + process spawn) is
faked. ``jiopc-hibernate selftest`` is the fastest way to confirm an install
is wired correctly.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from . import saver, restore, state as state_mod, system, windows as win_mod
from .config import Config
from .handlers import Registry
from .windows import Window


def _fake_windows(root: Path) -> list[Window]:
    """Fabricate a realistic 4-app session, with real files/dirs under *root*
    so the handlers that verify existence (document, file manager) exercise
    their real code paths rather than being short-circuited."""
    docs = root / "Documents"
    docs.mkdir(parents=True, exist_ok=True)
    report = docs / "report.odt"
    report.write_text("offline-selftest document")
    projects = root / "projects"
    projects.mkdir(parents=True, exist_ok=True)
    return [
        Window("0x01", 0, 1001, 100, 50, 1200, 800,
               "google-chrome.Google-chrome", "vm-a", "Inbox - Gmail",
               exe="/usr/bin/google-chrome",
               cmdline=["/usr/bin/google-chrome", "--profile-directory=Default"], cwd=None),
        Window("0x02", 0, 1002, 50, 100, 800, 500,
               "qterminal.qterminal", "vm-a", "user@vm-a: ~/projects",
               exe="/usr/bin/qterminal", cmdline=["/usr/bin/qterminal"], cwd=str(projects)),
        Window("0x03", 0, 1003, 200, 200, 900, 600,
               "pcmanfm-qt.pcmanfm-qt", "vm-a", "Documents",
               exe="/usr/bin/pcmanfm-qt", cmdline=["/usr/bin/pcmanfm-qt", str(docs)], cwd=str(docs)),
        Window("0x04", 0, 1004, 300, 80, 1000, 700,
               "libreoffice-writer.Soffice", "vm-a", "•report.odt - LibreOffice Writer",
               exe="/usr/bin/soffice", cmdline=["/usr/bin/soffice", str(report)], cwd=str(root)),
    ]


def run_selftest() -> bool:
    spawned: list[list[str]] = []
    fake: list[Window] = []

    # --- patch the OS seam -------------------------------------------------
    orig_enum = win_mod.enumerate_windows
    orig_display = win_mod.display_geometry
    orig_spawn = system.spawn
    orig_geo_ids = None

    win_mod.enumerate_windows = lambda timeout=3.0: list(fake)
    win_mod.display_geometry = lambda timeout=2.0: {"width": 1920, "height": 1080}
    system.spawn = lambda argv, cwd=None: (spawned.append(argv) or 4242)

    from . import geometry
    orig_geo_ids = geometry.current_window_ids
    geometry.current_window_ids = lambda: set()
    geometry.find_window = lambda wm_class, exclude, timeout=4.0: None  # skip placement offline

    try:
        with tempfile.TemporaryDirectory() as tmp:
            import os
            os.environ["JIOPC_HIBERNATE_HOME"] = tmp
            os.environ["JIOPC_HIBERNATE_CONFIG"] = str(Path(tmp) / "config")
            fake[:] = _fake_windows(Path(tmp) / "home")
            cfg = Config(relaunch_stagger_ms=0)
            registry = Registry.load()

            # 1) SAVE
            session = saver.save_session("manual", cfg=cfg, registry=registry)
            ok = _check("4 windows captured", len(session.windows) == 4)
            ok &= _check("state file written", state_mod.read_state() is not None)

            byh = {w.handler: w for w in session.windows}
            ok &= _check("chrome handler matched", "chrome" in byh)
            ok &= _check("terminal handler matched", "terminal" in byh)
            ok &= _check("filemanager handler matched", "filemanager" in byh)
            ok &= _check("document handler matched", "document" in byh)
            term_cwd = fake[1].cwd
            doc_path = fake[3].cmdline[1]
            ok &= _check("terminal cwd captured",
                         byh["terminal"].extra.get("cwd") == term_cwd)
            ok &= _check("document path captured",
                         doc_path in byh["document"].restore_args)
            ok &= _check("unsaved work flagged on document", byh["document"].unsaved is True)
            ok &= _check("save within budget", session.save_duration_ms <= cfg.save_time_budget_ms)

            # 2) RESTORE (auto-yes, fake spawn)
            spawned.clear()
            report = restore.run_restore(cfg=cfg, registry=registry, auto_yes=True)
            ok &= _check("restore relaunched 4 apps", report.launched == 4)
            chrome_cmd = next((c for c in spawned if "chrome" in c[0]), [])
            ok &= _check("chrome restored with --restore-last-session",
                         "--restore-last-session" in chrome_cmd)
            term_cmd = next((c for c in spawned if "qterminal" in c[0]), [])
            ok &= _check("terminal restored with workdir",
                         any(term_cwd in a for a in term_cmd))
            ok &= _check("state consumed (renamed)", state_mod.read_state() is None)

            # 3) STALE handling
            old = state_mod.SessionState(trigger="manual",
                                         saved_at=state_mod.utc_now_iso(0))  # epoch 1970
            state_mod.write_state(old)
            rep2 = restore.run_restore(cfg=cfg, registry=registry, auto_yes=True)
            ok &= _check("stale state discarded without restore", rep2.outcome == "stale")
            return bool(ok)
    finally:
        win_mod.enumerate_windows = orig_enum
        win_mod.display_geometry = orig_display
        system.spawn = orig_spawn
        if orig_geo_ids is not None:
            geometry.current_window_ids = orig_geo_ids


def _check(label: str, passed: bool) -> bool:
    print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
    return passed
