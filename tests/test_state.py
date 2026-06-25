"""session-state.json schema, recency, history and lifecycle (Component D)."""

from __future__ import annotations

import json

from jiopc_hibernate import paths, state as S


def test_roundtrip_preserves_fields(data_home):
    ws = S.WindowState(app_name="Chrome", exec="/usr/bin/google-chrome",
                       handler="chrome", restore_args=["--restore-last-session"],
                       geometry={"x": 1, "y": 2, "width": 3, "height": 4},
                       restore_supported=True, extra={"k": "v"})
    sess = S.SessionState(trigger=S.TRIGGER_USER_DISCONNECT,
                          saved_at=S.utc_now_iso(1_700_000_000), windows=[ws])
    S.write_state(sess)
    back = S.read_state()
    assert back is not None
    assert back.trigger == S.TRIGGER_USER_DISCONNECT
    assert len(back.windows) == 1
    w = back.windows[0]
    assert w.handler == "chrome"
    assert w.restore_args == ["--restore-last-session"]
    assert w.geometry == {"x": 1, "y": 2, "width": 3, "height": 4}
    assert w.extra == {"k": "v"}


def test_window_count_serialized(data_home):
    sess = S.SessionState(trigger="manual", saved_at=S.utc_now_iso(),
                          windows=[S.WindowState(app_name="A", exec="/a")])
    S.write_state(sess)
    raw = json.loads(paths.state_file().read_text())
    assert raw["window_count"] == 1
    assert raw["schema_version"] == S.SCHEMA_VERSION


def test_atomic_write_leaves_no_tmp(data_home):
    S.write_state(S.SessionState(trigger="manual", saved_at=S.utc_now_iso()))
    leftovers = list(paths.home().glob("*.tmp"))
    assert leftovers == []


def test_staleness_threshold():
    fresh = S.SessionState(trigger="manual", saved_at=S.utc_now_iso(1000))
    assert fresh.is_stale(3600, now=1000 + 1800) is False
    assert fresh.is_stale(3600, now=1000 + 7200) is True


def test_unparseable_timestamp_is_stale():
    bad = S.SessionState(trigger="manual", saved_at="not-a-date")
    assert bad.is_stale(86400, now=0) is True


def test_iso_roundtrip():
    iso = S.utc_now_iso(1_700_000_000)
    assert iso.endswith("Z")
    assert abs(S.parse_iso(iso) - 1_700_000_000) < 1


def test_mark_consumed_renames(data_home):
    S.write_state(S.SessionState(trigger="manual", saved_at=S.utc_now_iso()))
    assert paths.state_file().exists()
    S.mark_consumed()
    assert not paths.state_file().exists()
    assert paths.last_state_file().exists()


def test_history_rotation_keeps_depth(data_home):
    # Write + rotate several times; history should never exceed depth-1 snapshots.
    for i in range(6):
        S.write_state(S.SessionState(trigger="manual", saved_at=S.utc_now_iso(1000 + i)))
        S.rotate_history(history_depth=3, epoch=2000 + i)
    snaps = S.list_history()
    assert len(snaps) <= 2  # depth 3 = current file + 2 snapshots


def test_history_disabled_when_depth_one(data_home):
    S.write_state(S.SessionState(trigger="manual", saved_at=S.utc_now_iso()))
    S.rotate_history(history_depth=1, epoch=5000)
    assert S.list_history() == []
