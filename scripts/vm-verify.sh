#!/usr/bin/env bash
# vm-verify.sh — one-shot verification on the Ubuntu 24.04 + LxQt VM.
#
# Runs the whole correctness + performance + packaging battery and writes a
# single report to vm-report.txt that you can paste back. Safe to re-run; it
# only writes under a temp data home and the repo's packaging/dist.
#
#   bash scripts/vm-verify.sh            # full run (build deb, live benchmark)
#   bash scripts/vm-verify.sh --no-deb   # skip the .deb build
#
# It does NOT require the .deb to be installed — it runs from the source tree.
set -uo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

REPORT="vm-report.txt"
NO_DEB=0; [[ "${1:-}" == "--no-deb" ]] && NO_DEB=1
exec > >(tee "$REPORT") 2>&1

section() { echo; echo "==================== $* ===================="; }

section "0. ENVIRONMENT"
uname -a
. /etc/os-release 2>/dev/null && echo "distro: $PRETTY_NAME"
echo "desktop: ${XDG_CURRENT_DESKTOP:-unknown}  session: ${XDG_SESSION_TYPE:-unknown}"
if [ "${XDG_SESSION_TYPE:-}" = "wayland" ]; then
    echo "!! WARNING: this is a WAYLAND session. wmctrl is an X11 tool and CANNOT"
    echo "!! enumerate Wayland windows, so live capture (steps 5/6/9) will find 0"
    echo "!! windows. The challenge target is LxQt on X11. Log out and pick an"
    echo "!! 'LXQt' (X11) session at the login screen, then re-run this script."
fi
python3 --version
echo "nproc: $(nproc)  mem: $(free -m 2>/dev/null | awk '/Mem:/{print $2"MB"}')"

section "1. TOOLING"
for t in wmctrl xdotool xprintidle xssstate notify-send zenity dpkg-deb; do
    if command -v "$t" >/dev/null 2>&1; then echo "  $t = yes ($(command -v $t))"; else echo "  $t = NO"; fi
done
echo "TIP: sudo apt install -y wmctrl xdotool xprintidle libnotify-bin   # for full functionality"

section "2. VENV + UNIT TESTS"
python3 -m venv .venv 2>/dev/null || true
.venv/bin/pip install -q -e ".[dev]" 2>&1 | tail -1
.venv/bin/python -m pytest -q

section "3. OFFLINE SELFTEST (real save->restore loop, mocked OS)"
PYTHONPATH=src .venv/bin/python -m jiopc_hibernate selftest

section "4. STATUS (tooling + config the tool sees)"
PYTHONPATH=src .venv/bin/python -m jiopc_hibernate status

section "5. LIVE ENUMERATION (what would be captured right now)"
echo "Open a few apps (chrome, qterminal, pcmanfm-qt, libreoffice) before this for a good demo."
PYTHONPATH=src .venv/bin/python -m jiopc_hibernate enumerate

section "6. LIVE SAVE (real wmctrl + /proc), then show the JSON"
export JIOPC_HIBERNATE_HOME="$(mktemp -d)/hib"
PYTHONPATH=src .venv/bin/python -m jiopc_hibernate save --trigger user_disconnect
echo "--- session-state.json ---"
python3 -m json.tool "$JIOPC_HIBERNATE_HOME/session-state.json" 2>/dev/null || echo "(no state written)"

section "7. LIVE RESTORE (will relaunch the saved apps; --yes skips the prompt)"
echo "Skipping auto-relaunch in the report run to avoid spawning windows."
echo "To see it for real, run:  PYTHONPATH=src .venv/bin/python -m jiopc_hibernate restore"
echo "(interactive: shows the [Restore]/[Dismiss] notification first)"

section "8. BENCHMARK — harness (tool overhead)"
.venv/bin/python benchmarks/benchmark.py --fake --runs 20

section "9. BENCHMARK — live (real wmctrl save timing on this VM)"
if command -v wmctrl >/dev/null 2>&1; then
    .venv/bin/python benchmarks/benchmark.py --live --runs 5
else
    echo "wmctrl missing — skipping live benchmark"
fi

section "10. .deb BUILD"
if [[ "$NO_DEB" -eq 1 ]]; then
    echo "skipped (--no-deb)"
elif command -v dpkg-deb >/dev/null 2>&1; then
    bash packaging/build-deb.sh 2>&1 | tail -40
    echo "--- lintian (if present) ---"
    command -v lintian >/dev/null 2>&1 && lintian packaging/dist/*.deb 2>&1 | head -20 || echo "(lintian not installed)"
else
    echo "dpkg-deb missing — run: bash packaging/build-deb.sh --stage"
fi

section "DONE"
echo "Report written to: $REPORT"
echo "Paste vm-report.txt back so the numbers can go into the submission report."
