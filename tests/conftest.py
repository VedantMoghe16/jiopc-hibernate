"""Shared fixtures: an isolated data home, fake windows, a mocked OS seam.

Every test runs against a throwaway JIOPC_HIBERNATE_HOME so nothing touches a
real ~/.local/share, and the OS seam (window enumeration + process spawn) is
faked so the suite is fully hermetic — it passes on Linux, macOS and CI with
no X11, wmctrl or /proc.
"""

from __future__ import annotations

import pytest

from jiopc_hibernate.windows import Window


@pytest.fixture
def data_home(tmp_path, monkeypatch):
    home = tmp_path / "hibernate"
    cfg = tmp_path / "config"
    monkeypatch.setenv("JIOPC_HIBERNATE_HOME", str(home))
    monkeypatch.setenv("JIOPC_HIBERNATE_CONFIG", str(cfg))
    return home


@pytest.fixture
def make_docs(tmp_path):
    """Create real files/dirs so existence-checking handlers exercise real code."""
    docs = tmp_path / "Documents"
    docs.mkdir()
    report = docs / "report.odt"
    report.write_text("x")
    projects = tmp_path / "projects"
    projects.mkdir()
    return {"root": str(tmp_path), "docs": str(docs),
            "report": str(report), "projects": str(projects)}


@pytest.fixture
def fake_windows(make_docs):
    d = make_docs
    return [
        Window("0x01", 0, 1001, 100, 50, 1200, 800,
               "google-chrome.Google-chrome", "vm-a", "Inbox - Gmail",
               exe="/usr/bin/google-chrome",
               cmdline=["/usr/bin/google-chrome", "--profile-directory=Default"], cwd=None),
        Window("0x02", 0, 1002, 50, 100, 800, 500,
               "qterminal.qterminal", "vm-a", "user@vm-a: ~/projects",
               exe="/usr/bin/qterminal", cmdline=["/usr/bin/qterminal"], cwd=d["projects"]),
        Window("0x03", 0, 1003, 200, 200, 900, 600,
               "pcmanfm-qt.pcmanfm-qt", "vm-a", "Documents",
               exe="/usr/bin/pcmanfm-qt", cmdline=["/usr/bin/pcmanfm-qt", d["docs"]], cwd=d["docs"]),
        Window("0x04", 0, 1004, 300, 80, 1000, 700,
               "libreoffice-writer.Soffice", "vm-a", "•report.odt - LibreOffice Writer",
               exe="/usr/bin/soffice", cmdline=["/usr/bin/soffice", d["report"]], cwd=d["root"]),
    ]


@pytest.fixture
def patched_seam(monkeypatch, fake_windows):
    """Patch enumeration, display, spawn and geometry to a fake X11 box.

    Returns the list that captures every spawned argv during restore.
    """
    from jiopc_hibernate import windows as win_mod, system, geometry
    spawned: list[list[str]] = []
    monkeypatch.setattr(win_mod, "enumerate_windows", lambda timeout=3.0: list(fake_windows))
    monkeypatch.setattr(win_mod, "display_geometry", lambda timeout=2.0: {"width": 1920, "height": 1080})
    monkeypatch.setattr(system, "spawn", lambda argv, cwd=None: (spawned.append(argv) or 4242))
    monkeypatch.setattr(geometry, "current_window_ids", lambda: set())
    monkeypatch.setattr(geometry, "find_window", lambda wm_class, exclude, timeout=4.0: None)
    return spawned
