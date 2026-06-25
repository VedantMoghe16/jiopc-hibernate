"""Registry matching and per-app capture/restore (Component C)."""

from __future__ import annotations

from jiopc_hibernate.handlers import Registry, MatchRule
from jiopc_hibernate.handlers.base import RestoreHandler
from jiopc_hibernate.handlers.chrome import ChromeHandler
from jiopc_hibernate.windows import Window


def _win(**kw):
    base = dict(wid="0x1", desktop=0, pid=10, x=0, y=0, width=100, height=100,
                wm_class="", host="h", title="", exe=None, cmdline=[], cwd=None)
    base.update(kw)
    return Window(**base)


def test_registry_matches_each_known_app(fake_windows):
    reg = Registry.load()
    names = [reg.match(w).name for w in fake_windows]
    assert names == ["chrome", "terminal", "filemanager", "document"]


def test_unmatched_window_falls_to_generic():
    reg = Registry.load()
    w = _win(wm_class="some-random-app.Foo", exe="/usr/bin/foo", cmdline=["/usr/bin/foo"])
    assert reg.match(w).name == "generic"


def test_chrome_restore_command_uses_restore_flag():
    reg = Registry.load()
    w = _win(wm_class="google-chrome.Google-chrome", exe="/usr/bin/google-chrome",
             cmdline=["/usr/bin/google-chrome"])
    h = reg.match(w)
    ws = h.capture(w)
    cmd = h.restore_command(ws)
    assert "--restore-last-session" in cmd


def test_chrome_preserves_profile():
    h = ChromeHandler(MatchRule(handler="chrome", wm_class_contains=["chrome"]))
    w = _win(wm_class="google-chrome.Google-chrome", exe="/usr/bin/google-chrome",
             cmdline=["/usr/bin/google-chrome", "--profile-directory=Profile 2"])
    cmd = h.restore_command(h.capture(w))
    assert "--profile-directory=Profile 2" in cmd


def test_terminal_captures_cwd(make_docs):
    reg = Registry.load()
    w = _win(wm_class="qterminal.qterminal", exe="/usr/bin/qterminal",
             cmdline=["/usr/bin/qterminal"], cwd=make_docs["projects"])
    h = reg.match(w)
    ws = h.capture(w)
    assert ws.extra["cwd"] == make_docs["projects"]
    assert any(make_docs["projects"] in a for a in ws.restore_args)
    assert ws.restore_supported is True


def test_document_captures_existing_file(make_docs):
    reg = Registry.load()
    w = _win(wm_class="libreoffice-writer.Soffice", exe="/usr/bin/soffice",
             cmdline=["/usr/bin/soffice", make_docs["report"]])
    ws = reg.match(w).capture(w)
    assert make_docs["report"] in ws.restore_args
    assert ws.restore_supported is True


def test_document_ignores_nonexistent_file():
    reg = Registry.load()
    w = _win(wm_class="libreoffice-writer.Soffice", exe="/usr/bin/soffice",
             cmdline=["/usr/bin/soffice", "/nope/missing.odt"])
    ws = reg.match(w).capture(w)
    assert ws.restore_args == []          # never restore a dead path
    assert ws.restore_supported is False


def test_filemanager_captures_folder(make_docs):
    reg = Registry.load()
    w = _win(wm_class="pcmanfm-qt.pcmanfm-qt", exe="/usr/bin/pcmanfm-qt",
             cmdline=["/usr/bin/pcmanfm-qt", make_docs["docs"]], cwd=make_docs["docs"])
    ws = reg.match(w).capture(w)
    assert ws.restore_args == [make_docs["docs"]]


def test_filemanager_single_instance_resolves_folder_from_title(tmp_path, monkeypatch):
    """LxQt single-instance pcmanfm-qt: shared --desktop cmdline and $HOME cwd,
    so the folder must be recovered from the window TITLE."""
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "Documents").mkdir()
    reg = Registry.load()
    w = _win(wm_class="pcmanfm-qt.pcmanfm-qt", exe="/usr/bin/pcmanfm-qt",
             cmdline=["/usr/bin/pcmanfm-qt", "--desktop", "--profile=lxqt"],
             cwd=str(tmp_path), title="Documents")
    ws = reg.match(w).capture(w)
    assert ws.restore_args == [str(tmp_path / "Documents")]
    assert ws.restore_supported is True


def test_declarative_handler_added_by_config_only(tmp_path):
    """A handler name with no Python class still works from JSON alone."""
    rules = tmp_path / "handlers.json"
    rules.write_text('{"handlers":[{"handler":"myeditor",'
                     '"wm_class_contains":["myeditor"],'
                     '"restore_args":["--reopen"],"restore_supported":true}]}')
    reg = Registry.load(rules_file=rules)
    w = _win(wm_class="myeditor.MyEditor", exe="/usr/bin/myeditor",
             cmdline=["/usr/bin/myeditor"])
    h = reg.match(w)
    assert h.name == "myeditor"
    assert isinstance(h, RestoreHandler)
    cmd = h.restore_command(h.capture(w))
    assert cmd == ["/usr/bin/myeditor", "--reopen"]


def test_generic_capture_records_geometry():
    reg = Registry.load()
    w = _win(wm_class="x.Y", exe="/usr/bin/x", cmdline=["/usr/bin/x"],
             x=5, y=6, width=7, height=8)
    ws = reg.match(w).capture(w)
    assert ws.geometry == {"x": 5, "y": 6, "width": 7, "height": 8}


def test_pre_save_hooks_only_chrome():
    reg = Registry.load()
    hooks = reg.pre_save_hooks()
    assert [h.name for h in hooks] == ["chrome"]
