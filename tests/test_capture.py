"""Window parsing, unsaved detection, ignore filtering, save budget (Comp. B)."""

from __future__ import annotations

from jiopc_hibernate import saver, windows as win_mod
from jiopc_hibernate.config import Config
from jiopc_hibernate.unsaved import has_unsaved_marker
from jiopc_hibernate.windows import _parse_wmctrl


def test_parse_wmctrl_basic():
    line = "0x03a00007  0 1234   100 50   1200 800  google-chrome.Google-chrome  vm-a Inbox - Gmail"
    wins = _parse_wmctrl([line])
    assert len(wins) == 1
    w = wins[0]
    assert w.wid == "0x03a00007"
    assert w.pid == 1234
    assert (w.x, w.y, w.width, w.height) == (100, 50, 1200, 800)
    assert w.wm_class == "google-chrome.Google-chrome"
    assert w.title == "Inbox - Gmail"


def test_parse_wmctrl_title_with_many_spaces():
    line = "0x01 0 5 0 0 10 10 cls.Cls host A  B   C    D"
    w = _parse_wmctrl([line])[0]
    assert w.title == "A  B   C    D"


def test_parse_wmctrl_skips_malformed():
    assert _parse_wmctrl(["garbage", "0x01 0 notapid 0 0 1 1 c h t"]) == []


def test_unsaved_markers():
    assert has_unsaved_marker("•report.odt - LibreOffice")
    assert has_unsaved_marker("*Untitled - gedit")
    assert has_unsaved_marker("notes.txt - modified")
    assert not has_unsaved_marker("Inbox - Gmail")
    assert not has_unsaved_marker("")


def test_save_captures_and_writes(data_home, patched_seam):
    cfg = Config(relaunch_stagger_ms=0)
    sess = saver.save_session("manual", cfg=cfg)
    assert len(sess.windows) == 4
    assert sess.save_duration_ms <= cfg.save_time_budget_ms
    assert sess.budget_exceeded is False
    assert sess.hostname  # recorded


def test_ignore_patterns_skip_shell(data_home, monkeypatch):
    from jiopc_hibernate.windows import Window
    shell = Window("0x9", 0, 9, 0, 0, 10, 10, "jiopc-home.JioPC", "h", "Home",
                   exe="/usr/bin/jiopc-home", cmdline=["/usr/bin/jiopc-home"])
    monkeypatch.setattr(win_mod, "enumerate_windows", lambda timeout=3.0: [shell])
    monkeypatch.setattr(win_mod, "display_geometry", lambda timeout=2.0: None)
    sess = saver.save_session("manual", cfg=Config())
    assert sess.windows == []  # the shell itself is never captured


def test_pcmanfm_desktop_ignored_but_file_window_kept(data_home, monkeypatch):
    """Single-instance pcmanfm-qt: desktop bg and a file window share one PID
    (and a `--desktop` cmdline). The desktop must be dropped by title; the
    real file window must still be captured."""
    from jiopc_hibernate.windows import Window
    shared_cmd = ["pcmanfm-qt", "--desktop", "--profile", "lxqt"]
    desktop = Window("0x01", -1, 176371, 0, 0, 1280, 720, "pcmanfm-qt.pcmanfm-qt",
                     "h", "pcmanfm-desktop0", exe="/usr/bin/pcmanfm-qt",
                     cmdline=shared_cmd, cwd="/home/u")
    filewin = Window("0x02", 0, 176371, 50, 50, 900, 600, "pcmanfm-qt.pcmanfm-qt",
                     "h", "Documents", exe="/usr/bin/pcmanfm-qt",
                     cmdline=shared_cmd, cwd="/home/u")
    monkeypatch.setattr(win_mod, "enumerate_windows", lambda timeout=3.0: [desktop, filewin])
    monkeypatch.setattr(win_mod, "display_geometry", lambda timeout=2.0: None)
    sess = saver.save_session("manual", cfg=Config())
    titles = [w.title for w in sess.windows]
    assert titles == ["Documents"]            # desktop dropped, file window kept
    assert sess.windows[0].handler == "filemanager"


def test_save_never_raises_on_empty(data_home, monkeypatch):
    monkeypatch.setattr(win_mod, "enumerate_windows", lambda timeout=3.0: [])
    monkeypatch.setattr(win_mod, "display_geometry", lambda timeout=2.0: None)
    sess = saver.save_session("inactivity_timeout", cfg=Config())
    assert sess.windows == []
    assert sess.trigger == "inactivity_timeout"
