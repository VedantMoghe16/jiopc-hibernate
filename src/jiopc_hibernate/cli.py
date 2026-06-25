"""Command-line surface for JioPC Session Hibernate.

One dispatcher binary, ``jiopc-hibernate <command>``, plus thin aliases wired
as console scripts for the integration glue:

    jiopc-hibernate save [--trigger ...]   capture now (Component A/B)
    jiopc-hibernate restore [--yes]        run the restore flow (Component E)
    jiopc-hibernate guard                  the idle/signal daemon (Component A)
    jiopc-hibernate status                 show saved state + config + tooling
    jiopc-hibernate enumerate              list capturable windows (debug)
    jiopc-hibernate selftest               offline end-to-end check (no X11)

Exit codes are intentionally forgiving: the restore/save commands return 0
even on partial failure, because they are wired into the session lifecycle
and a non-zero exit must never look like a session error.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__, paths, system
from .config import Config
from .log import get_logger

_log = get_logger()


def _cmd_save(args) -> int:
    from . import saver
    cfg = Config.load()
    session = saver.save_session(args.trigger, cfg=cfg)
    print(f"saved {len(session.windows)} window(s) in {session.save_duration_ms}ms "
          f"(budget {cfg.save_time_budget_ms}ms, exceeded={session.budget_exceeded}) "
          f"-> {paths.state_file()}")
    return 0


def _cmd_restore(args) -> int:
    from . import restore
    report = restore.run_restore(auto_yes=args.yes)
    print(report.summary_line())
    for r in report.results:
        flag = "ok " if r.launched else "FAIL"
        print(f"  [{flag}] {r.app_name} (handler={r.handler}, in-app={r.in_app_restore}, "
              f"geometry={r.geometry_applied}) {r.detail}")
    return 0


def _cmd_guard(_args) -> int:
    from .guard import SessionGuard
    SessionGuard().run()
    return 0


def _cmd_status(_args) -> int:
    from . import state as state_mod
    cfg = Config.load()
    print(f"jiopc-hibernate {__version__}")
    print(f"platform        : {'linux' if system.is_linux() else sys.platform}")
    print(f"state dir       : {paths.home()}")
    print(f"config dir      : {paths.config_dir()}")
    print("tooling         : " + ", ".join(
        f"{t}={'yes' if system.have(t) else 'no'}"
        for t in ("wmctrl", "xdotool", "xprintidle", "notify-send", "zenity")))
    print("config          :")
    for k, v in cfg.to_dict().items():
        print(f"    {k} = {v}")
    session = state_mod.read_state()
    if session is None:
        print("saved session   : none")
    else:
        age = session.age_seconds()
        print(f"saved session   : {len(session.windows)} window(s), trigger={session.trigger}, "
              f"saved_at={session.saved_at}"
              + (f", age={age:.0f}s" if age is not None else ""))
    hist = state_mod.list_history()
    if hist:
        print(f"history         : {len(hist)} snapshot(s)")
    return 0


def _cmd_enumerate(_args) -> int:
    from . import windows as win_mod
    from .handlers import Registry
    registry = Registry.load()
    wins = win_mod.enumerate_windows()
    if not wins:
        print("no windows enumerated (need Linux + wmctrl + a running X11 session)")
        return 0
    for w in wins:
        h = registry.match(w)
        print(f"{w.wid} pid={w.pid:<7} handler={h.name:<11} {w.wm_class:<28} {w.title[:40]}")
    return 0


def _cmd_selftest(_args) -> int:
    from .selftest import run_selftest
    ok = run_selftest()
    print("SELFTEST: PASS" if ok else "SELFTEST: FAIL")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="jiopc-hibernate",
                                description="JioPC application-level session save & restore.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("save", help="capture the running session now")
    sp.add_argument("--trigger", default="manual",
                    choices=["manual", "inactivity_timeout", "user_disconnect", "session_end"])
    sp.set_defaults(func=_cmd_save)

    rp = sub.add_parser("restore", help="run the restore flow")
    rp.add_argument("--yes", action="store_true", help="skip the prompt (for the demo/tests)")
    rp.set_defaults(func=_cmd_restore)

    sub.add_parser("guard", help="run the idle/signal session-end daemon").set_defaults(func=_cmd_guard)
    sub.add_parser("status", help="show saved state, config and tooling").set_defaults(func=_cmd_status)
    sub.add_parser("enumerate", help="list capturable windows (debug)").set_defaults(func=_cmd_enumerate)
    sub.add_parser("selftest", help="offline end-to-end check (no X11 needed)").set_defaults(func=_cmd_selftest)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # last-ditch guard: never propagate a crash
        _log.error("unhandled error in '%s': %s", getattr(args, "command", "?"), exc)
        print(f"error: {exc}", file=sys.stderr)
        return 0  # still 0: we must not look like a session failure


# --- console-script aliases (see pyproject [project.scripts]) ---------------

def main_save() -> int:
    return main(["save", "--trigger", "user_disconnect"])


def main_restore() -> int:
    return main(["restore"])


def main_guard() -> int:
    return main(["guard"])


if __name__ == "__main__":
    raise SystemExit(main())
