"""Restore flow: confirm/dismiss, stale, partial failure, consume (Comp. E)."""

from __future__ import annotations

from jiopc_hibernate import restore, saver, state as S
from jiopc_hibernate.config import Config
from jiopc_hibernate.notify import Choice


def _save(cfg):
    return saver.save_session("user_disconnect", cfg=cfg)


def test_restore_relaunches_all_on_yes(data_home, patched_seam):
    cfg = Config(relaunch_stagger_ms=0)
    _save(cfg)
    report = restore.run_restore(cfg=cfg, auto_yes=True)
    assert report.outcome == "restored"
    assert report.launched == 4 and report.failed == 0
    # Chrome reopened via its own session restore
    assert any("--restore-last-session" in c for c in patched_seam)
    # state consumed so it won't re-trigger
    assert S.read_state() is None


def test_dismiss_relaunches_nothing(data_home, patched_seam, monkeypatch):
    cfg = Config(relaunch_stagger_ms=0)
    _save(cfg)
    monkeypatch.setattr(restore.notify, "ask_restore",
                        lambda *a, **k: Choice.DISMISS)
    report = restore.run_restore(cfg=cfg)
    assert report.outcome == "dismissed"
    assert patched_seam == []          # nothing spawned
    assert S.read_state() is None      # still consumed


def test_prompt_shown_before_relaunch(data_home, patched_seam, monkeypatch):
    cfg = Config(relaunch_stagger_ms=0)
    _save(cfg)
    calls = {"n": 0}

    def fake_ask(*a, **k):
        calls["n"] += 1
        return Choice.YES

    monkeypatch.setattr(restore.notify, "ask_restore", fake_ask)
    restore.run_restore(cfg=cfg)
    assert calls["n"] == 1             # exactly one prompt, before launching


def test_stale_state_discarded_silently(data_home, patched_seam, monkeypatch):
    cfg = Config(relaunch_stagger_ms=0)
    S.write_state(S.SessionState(trigger="manual", saved_at=S.utc_now_iso(0)))
    called = {"asked": False}
    monkeypatch.setattr(restore.notify, "ask_restore",
                        lambda *a, **k: called.__setitem__("asked", True) or Choice.YES)
    report = restore.run_restore(cfg=cfg)
    assert report.outcome == "stale"
    assert called["asked"] is False    # no prompt for stale state
    assert patched_seam == []


def test_absent_state_is_noop(data_home):
    report = restore.run_restore(cfg=Config())
    assert report.outcome == "absent"


def test_partial_failure_continues_and_reports(data_home, patched_seam, monkeypatch):
    """One app that won't launch must not stop the others; it's reported."""
    cfg = Config(relaunch_stagger_ms=0)
    _save(cfg)
    from jiopc_hibernate import system

    real_spawn = patched_seam

    def flaky_spawn(argv, cwd=None):
        if "qterminal" in argv[0]:
            return None                # simulate a failed relaunch
        real_spawn.append(argv)
        return 4242

    monkeypatch.setattr(system, "spawn", flaky_spawn)
    report = restore.run_restore(cfg=cfg, auto_yes=True)
    assert report.outcome == "restored"
    assert report.failed == 1
    assert report.launched == 3
    failed = [r for r in report.results if not r.launched]
    assert len(failed) == 1
    assert failed[0].handler == "terminal"
