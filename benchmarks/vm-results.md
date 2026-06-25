# Validated on a real Ubuntu 24.04 + LxQt VM

These are measured results from running `scripts/vm-verify.sh` on the actual
target stack (not the dev box). Reproduce with one command:
`bash scripts/vm-verify.sh`.

## Test environment

| Property | Value |
|---|---|
| Distro | Ubuntu 24.04.4 LTS |
| Desktop / session | **LXQt / X11** (the challenge target) |
| Kernel | 6.17.0-35-generic |
| CPU / RAM | **4 vCPU**, 7911 MB (matches the JioPC profile) |
| Architecture | **aarch64** (VirtualBox on Apple Silicon) |
| Python | 3.12.3 (system, stdlib only) |
| Tooling present | wmctrl, xdotool, xprintidle, notify-send, zenity, dpkg-deb |

> The VM is **arm64**, while the JioPC Gold Image is amd64. The system ran
> unmodified — concrete proof of the "stdlib-only, `Architecture: all`"
> portability claim. The save/restore logic is CPU- and arch-independent.

## Correctness

| Check | Result |
|---|---|
| Unit + integration suite (`pytest`) | **35 / 35 passed** |
| Offline self-test (real save→restore loop) | **PASS** (all 15 assertions) |
| Live enumeration (real `wmctrl` + `/proc`) | all GUI windows listed with their handler |
| Desktop-background window correctly excluded | ✅ `pcmanfm-desktop0` dropped, file windows kept |
| Per-terminal working directory captured | ✅ each qterminal saved with its own `cwd` |
| File-manager folder captured | ✅ `filemanager` handler, folder resolved from title |
| Display resolution recorded | ✅ `1280×720` |

Example of the **single-instance file-manager** correctness (the subtle case):
pcmanfm-qt serves the desktop and every file window from one PID with a shared
`--desktop` cmdline. The tool drops only the desktop-background window (by
title) and still captures the real file windows — verified live and pinned by
a regression test (`test_pcmanfm_desktop_ignored_but_file_window_kept`).

## Performance — save time (the budgeted path)

Real `wmctrl` + `/proc` capture, 5-window live session, 5 runs:

| Metric | Value | vs. 10 s budget |
|---|---:|---:|
| Save mean | **18.9 ms** | 0.2 % |
| Save p95 | **26.5 ms** | 0.3 % |
| Single 5-window save (observed) | 11 ms | 0.1 % |

The save completes **~370–530× inside** the 10 s budget on a 4-vCPU ARM VM —
it can never block session teardown. `budget_exceeded` was `false` throughout.

## Performance — harness (tool overhead, 10 app combinations × 20 runs)

Real saver/registry/restore code, stubbed OS seam (isolates the tool's own
cost from app start-up):

| Metric | Value |
|---|---:|
| Worst-case save mean (any combination) | **2.4 ms** |
| Typical save mean | 0.5–0.9 ms |
| Restore issue mean | 6–10 ms |
| Relaunch success rate | **100 %** |

## Packaging

| Check | Result |
|---|---|
| `.deb` builds with `dpkg-deb` on Ubuntu 24.04 (aarch64) | ✅ clean |
| Contents | package lib under `/opt`, 5 launchers in `/usr/bin`, 2 autostart entries, `/etc/jiopc-hibernate` config, docs in `/usr/share/doc` |
| `Architecture` | `all` (pure-Python, runs on amd64 and arm64 alike) |

## How to reproduce

```sh
git clone <repo> && cd jiopc-hibernate
sudo apt install -y wmctrl xdotool xprintidle libnotify-bin
# open a few apps (terminals, file manager, an editor), then:
bash scripts/vm-verify.sh        # writes vm-report.txt
```
