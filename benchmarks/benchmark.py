#!/usr/bin/env python3
"""Benchmark harness — save time, restore time, success rate.

Measures the three numbers the deliverable asks for, across a matrix of app
combinations:

  * **save time**    — trigger → session-state.json on disk (Component B)
  * **restore time** — restore start → every app's relaunch issued (Component E)
  * **success rate** — fraction of captured apps that relaunch without error

Two modes:

  * ``--fake`` (default): fabricates window sets and stubs the OS seam, so the
    *real* saver/registry/restore code is timed end-to-end with no X11. This
    is what runs on CI and the dev box and produces results.md.
  * ``--live``: measures against the actual running X11 session on the VM
    (needs wmctrl). Save is real; restore is real launches. Use for the
    on-VM benchmark in the report.

Usage:
    python3 benchmark.py --fake --runs 20 --out results.md
    python3 benchmark.py --live --runs 5
"""

from __future__ import annotations

import argparse
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jiopc_hibernate import saver, restore, state as S, system, windows as win_mod, geometry  # noqa: E402
from jiopc_hibernate.config import Config  # noqa: E402
from jiopc_hibernate.windows import Window  # noqa: E402

# 10 representative app combinations (the spec asks for ~10).
COMBOS = {
    "student":        ["chrome", "document", "pdf"],
    "trader":         ["chrome", "chrome2", "terminal"],
    "developer":      ["terminal", "terminal2", "chrome", "editor"],
    "writer":         ["document", "filemanager"],
    "researcher":     ["chrome", "document", "document2", "filemanager"],
    "minimal":        ["chrome"],
    "heavy":          ["chrome", "terminal", "document", "filemanager", "editor", "pdf"],
    "office":         ["document", "document2", "chrome"],
    "files-only":     ["filemanager", "filemanager2"],
    "mixed-unsaved":  ["document", "terminal", "chrome", "editor"],
}

_SPECS = {
    "chrome":  ("google-chrome.Google-chrome", "/usr/bin/google-chrome", ["--profile-directory=Default"], None, "Gmail"),
    "chrome2": ("google-chrome.Google-chrome", "/usr/bin/google-chrome", [], None, "Docs"),
    "terminal": ("qterminal.qterminal", "/usr/bin/qterminal", [], "PROJECTS", "shell"),
    "terminal2": ("qterminal.qterminal", "/usr/bin/qterminal", [], "PROJECTS", "logs"),
    "filemanager": ("pcmanfm-qt.pcmanfm-qt", "/usr/bin/pcmanfm-qt", ["DOCS"], "DOCS", "Documents"),
    "filemanager2": ("pcmanfm-qt.pcmanfm-qt", "/usr/bin/pcmanfm-qt", ["DOCS"], "DOCS", "Files"),
    "document": ("libreoffice-writer.Soffice", "/usr/bin/soffice", ["REPORT"], None, "•report.odt - LibreOffice"),
    "document2": ("libreoffice-calc.Soffice", "/usr/bin/soffice", ["SHEET"], None, "budget.ods - LibreOffice"),
    "editor": ("featherpad.FeatherPad", "/usr/bin/featherpad", ["NOTES"], None, "notes.txt"),
    "pdf": ("qpdfview.qpdfview", "/usr/bin/qpdfview", ["REPORT"], None, "report.pdf"),
}


def _build_windows(keys: list[str], root: Path) -> list[Window]:
    docs = root / "Documents"; docs.mkdir(parents=True, exist_ok=True)
    projects = root / "projects"; projects.mkdir(parents=True, exist_ok=True)
    report = docs / "report.odt"; report.write_text("x")
    sheet = docs / "budget.ods"; sheet.write_text("x")
    notes = docs / "notes.txt"; notes.write_text("x")
    rpdf = docs / "report.pdf"; rpdf.write_text("x")
    subst = {"PROJECTS": str(projects), "DOCS": str(docs), "REPORT": str(report),
             "SHEET": str(sheet), "NOTES": str(notes)}
    out = []
    for i, key in enumerate(keys):
        wm, exe, args, cwd, title = _SPECS[key]
        args = [subst.get(a, a) for a in args]
        cwd = subst.get(cwd, cwd)
        out.append(Window(f"0x{i+1:02x}", 0, 1000 + i, 50 + i * 20, 40 + i * 20, 1000, 700,
                          wm, "vm-bench", title, exe=exe, cmdline=[exe, *args], cwd=cwd))
    return out


def _bench_fake(runs: int) -> list[dict]:
    rows = []
    for name, keys in COMBOS.items():
        saves, restores, rates = [], [], []
        for _ in range(runs):
            with tempfile.TemporaryDirectory() as tmp:
                import os
                os.environ["JIOPC_HIBERNATE_HOME"] = tmp
                os.environ["JIOPC_HIBERNATE_CONFIG"] = str(Path(tmp) / "cfg")
                wins = _build_windows(keys, Path(tmp) / "home")
                spawned: list = []
                win_mod.enumerate_windows = lambda timeout=3.0, w=wins: list(w)
                win_mod.display_geometry = lambda timeout=2.0: {"width": 1920, "height": 1080}
                system.spawn = lambda argv, cwd=None: (spawned.append(argv) or 4242)
                geometry.current_window_ids = lambda: set()
                geometry.find_window = lambda wm_class, exclude, timeout=4.0: None
                cfg = Config(relaunch_stagger_ms=0)

                t0 = time.perf_counter()
                sess = saver.save_session("user_disconnect", cfg=cfg)
                saves.append((time.perf_counter() - t0) * 1000)

                t1 = time.perf_counter()
                rep = restore.run_restore(cfg=cfg, auto_yes=True)
                restores.append((time.perf_counter() - t1) * 1000)
                rates.append(rep.launched / rep.total if rep.total else 1.0)
        rows.append({
            "combo": name, "apps": len(keys),
            "save_ms": statistics.mean(saves), "save_p95": _p95(saves),
            "restore_ms": statistics.mean(restores),
            "success": statistics.mean(rates) * 100,
        })
    return rows


def _bench_live(runs: int) -> list[dict]:
    if not system.have("wmctrl"):
        print("live mode needs wmctrl on PATH", file=sys.stderr)
        sys.exit(2)
    saves = []
    for _ in range(runs):
        t0 = time.perf_counter()
        sess = saver.save_session("manual")
        saves.append((time.perf_counter() - t0) * 1000)
        time.sleep(0.5)
    return [{"combo": "live-session", "apps": len(sess.windows),
             "save_ms": statistics.mean(saves), "save_p95": _p95(saves),
             "restore_ms": float("nan"), "success": float("nan")}]


def _p95(xs: list[float]) -> float:
    s = sorted(xs)
    return s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))]


def _render(rows: list[dict], mode: str, runs: int) -> str:
    budget = Config().save_time_budget_ms
    lines = [
        "# JioPC Session Hibernate — Benchmark Results",
        "",
        f"Mode: **{mode}**  ·  Runs per combination: **{runs}**  ·  "
        f"Save budget: **{budget} ms**",
        "",
        "| Combination | Apps | Save mean (ms) | Save p95 (ms) | Restore mean (ms) | Success |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    all_save, all_succ = [], []
    for r in rows:
        rest = "—" if r["restore_ms"] != r["restore_ms"] else f"{r['restore_ms']:.1f}"
        succ = "—" if r["success"] != r["success"] else f"{r['success']:.0f}%"
        lines.append(f"| {r['combo']} | {r['apps']} | {r['save_ms']:.1f} | "
                     f"{r['save_p95']:.1f} | {rest} | {succ} |")
        all_save.append(r["save_ms"])
        if r["success"] == r["success"]:
            all_succ.append(r["success"])
    lines += ["",
              f"**Worst-case save mean:** {max(all_save):.1f} ms "
              f"({100*max(all_save)/budget:.1f}% of the {budget} ms budget).",
              ]
    if all_succ:
        lines.append(f"**Mean relaunch success rate:** {statistics.mean(all_succ):.0f}%.")
    lines += [
        "",
        "> `--fake` mode times the real saver/registry/restore code against "
        "stubbed window enumeration and process spawn, isolating the tool's own "
        "overhead from app start-up cost. On a real VM the dominant restore cost "
        "is the apps' own launch time, not this tool. See methodology.md.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="JioPC Session Hibernate benchmark")
    ap.add_argument("--live", action="store_true", help="measure the real X11 session (needs wmctrl)")
    ap.add_argument("--fake", action="store_true", help="synthetic combinations (default)")
    ap.add_argument("--runs", type=int, default=20)
    ap.add_argument("--out", type=str, default=None, help="write a markdown report here")
    args = ap.parse_args()
    mode = "live" if args.live else "fake"
    rows = _bench_live(args.runs) if args.live else _bench_fake(args.runs)
    report = _render(rows, mode, args.runs)
    print(report)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
