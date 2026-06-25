# Benchmark methodology

Three numbers are reported, matching the deliverable: **save time**,
**restore time**, **relaunch success rate**. This document defines exactly how
each is measured so the figures in `results.md` are reproducible.

## Definitions

| Metric | Start marker | End marker |
|---|---|---|
| **Save time** | save invoked (trigger fires) | `session-state.json` durably on disk (after `os.replace`) |
| **Restore time** | restore service begins relaunch | spawn issued for the last app (process forked) |
| **Success rate** | — | `apps launched / apps captured`, per the restore report |

Restore time deliberately ends at *spawn issued*, not "app fully drawn":
once the process is forked the app's own start-up dominates and is outside
this tool's control. Chrome painting its tabs is Chrome's latency, not ours.

## Mode 1 — `--fake` (harness numbers, what CI runs)

```sh
python3 benchmarks/benchmark.py --fake --runs 20 --out results.md
```

Window enumeration and process spawn are stubbed, so the **real**
saver → registry → handler → state-write → restore code runs end-to-end with
zero X11 or app-launch cost mixed in. This isolates the tool's *own* overhead
across 10 app combinations (1–6 apps each). It is the cleanest measure of
"does the implementation itself stay far inside the budget", and it runs
identically on the dev box, CI, and the VM.

Interpretation: the tool's overhead is sub-millisecond per session; the 10 s
budget is essentially all headroom for the external commands below.

## Mode 2 — `--live` (on the Ubuntu 24.04 + LxQt VM)

```sh
# inside the VM, with a real session of apps open:
python3 benchmarks/benchmark.py --live --runs 5
```

Save is measured against the real `wmctrl`/`/proc` path. On the reference
4-vCPU / no-GPU VM the cost breaks down roughly as:

| Stage | Typical cost | Notes |
|---|---|---|
| `wmctrl -lpGx` enumeration | 15–60 ms | one process exec + X round-trips |
| per-window /proc reads | < 1 ms each | cheap symlink/byte reads |
| handler capture | < 1 ms each | string work |
| atomic JSON write | 1–5 ms | small file, single `os.replace` |
| Chrome clean-shutdown signal | < 1 ms | one `kill(2)` per Chrome PID |

A realistic 4–6 app session saves in well under **300 ms** — two orders of
magnitude inside the 10 s budget. The budget exists for pathological cases
(a hung X server, hundreds of windows); the deadline logic in `saver.py`
guarantees we stop and write partial state rather than overrun.

### Restore time on the VM

Restore time as defined (spawn issued) is dominated by the configured
`relaunch_stagger_ms` (default 400 ms × N apps) plus per-app geometry lookup.
With geometry off, a 5-app restore issues all spawns in ~1–2 s; the apps then
start in parallel. The stagger is a deliberate throttle for the 4-vCPU VM, not
overhead — set `relaunch_stagger_ms: 0` to measure raw issue time.

## Success-rate test set

The 10 combinations in `benchmark.py` (`COMBOS`) span the personas named in
the spec — student, trader, developer, writer — from a single Chrome up to a
6-app heavy session, including duplicate apps (two terminals, two documents)
to exercise the geometry "claimed window" matching. Success is reported per
combination and aggregated.

## Reproducing

```sh
# unit + integration correctness gate
.venv/bin/python -m pytest -q

# offline end-to-end proof (no X11)
python3 -m jiopc_hibernate selftest

# harness benchmark
python3 benchmarks/benchmark.py --fake --runs 20 --out results.md
```
