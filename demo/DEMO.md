# Cross-VM session restore — demo runbook

A step-by-step script for the **recorded demo** deliverable: open apps on one
VM, disconnect, log in on a *different* VM with the same home mounted, and watch
the session come back. Record the whole thing inside the VM (e.g. with
`vokoscreenNG`, OBS, or `recordmydesktop`).

## 0. Prerequisites (once, on the Gold Image)

```sh
sudo apt install ./packaging/dist/jiopc-hibernate_1.0.0_all.deb
sudo apt install wmctrl libnotify-bin xprintidle    # recommended companions
```

Confirm wiring:

```sh
jiopc-hibernate status
# expect: tooling wmctrl=yes, notify-send=yes; state dir under ~/.local/share
ls /etc/xdg/autostart/jiopc-hibernate-*.desktop     # guard + restore present
```

## 1. The cross-VM setup

The whole trick is that `~/.local/share/jiopc/hibernate/` lives in the
**roaming home**. Pick whichever matches your environment:

- **Two real pool VMs (ideal).** VM-A and VM-B both mount the same NFS home.
  Save on VM-A, log in on VM-B. This is the true cross-VM demo.
- **One VM, simulated reassignment.** Log into VM-A, disconnect, then log back
  in. To *prove* it is VM-agnostic on a single box, change the hostname between
  sessions (`sudo hostnamectl set-hostname vm-b`) — the saved
  `"hostname": "vm-a"` in `session-state.json` vs. the new host visibly
  demonstrates the session moved machines.

> Talking point for the recording: open `session-state.json` and show
> `hostname` ≠ the current `hostname` — the file followed the *user*, not the
> machine.

## 2. Build a session on VM-A (the "before")

Open **3–4 apps, including Chrome**:

```sh
google-chrome --restore-last-session https://news.ycombinator.com &  # open a couple tabs
qterminal &        # then `cd ~/projects` inside it
pcmanfm-qt ~/Documents &
soffice ~/Documents/report.odt &   # edit it a little, leave it "•" unsaved
```

Show what will be captured:

```sh
jiopc-hibernate enumerate
# lists each window with the handler that will own it (chrome/terminal/...)
```

## 3. Trigger the disconnect

Pick the path you want to show (do both for a thorough recording):

- **User-initiated disconnect** — press the LxQt logout/disconnect button (or
  run the explicit wrapper `jiopc-hibernate-leave`). The guard's SIGTERM trap
  fires a `user_disconnect` save during teardown.
- **Inactivity timeout** — for a quick demo, drop `idle_timeout_s` to ~20 in
  `~/.config/jiopc-hibernate/config.json`, restart the guard, and simply stop
  touching the machine. The guard fires an `inactivity_timeout` save.
- **Manual (fastest for B-roll)** — `jiopc-hibernate save --trigger user_disconnect`.

Verify the capture (note the duration is far inside the 10 s budget):

```sh
jiopc-hibernate status
cat ~/.local/share/jiopc/hibernate/session-state.json | python3 -m json.tool
# show: trigger, save_duration_ms, the 4 windows, chrome handler with
# --restore-last-session, terminal with --workdir, the unsaved flag on report.odt
```

## 4. Log in on VM-B (the "after")

Log into the second VM (or relog after the hostname change). The restore
service runs automatically a few seconds into the session:

1. A desktop notification appears: **"Restore your previous session?
   [Restore] [Dismiss]"** — *this appears before anything relaunches.*
2. Click **Restore.**
3. The 4 apps relaunch: Chrome reopens its exact tabs (its own
   `--restore-last-session`), the terminal opens in `~/projects`, the file
   manager opens `~/Documents`, LibreOffice reopens `report.odt`. Windows are
   nudged toward their saved positions (best-effort).
4. A summary notification reports how many apps were restored.

To drive it deterministically on camera (no waiting for autostart):

```sh
jiopc-hibernate restore          # shows the prompt
# or, to skip the prompt for B-roll:
jiopc-hibernate restore --yes
```

Show that it won't re-trigger:

```sh
ls ~/.local/share/jiopc/hibernate/
# session-state.json is now session-state-last.json (consumed)
```

## 5. Reviewer acceptance checklist (map to what's on screen)

| Check | Show on camera |
|---|---|
| State saved on inactivity timeout | idle save → `trigger: inactivity_timeout` in JSON |
| State saved on user disconnect | logout → `trigger: user_disconnect` in JSON |
| All running GUI apps captured | `enumerate` vs. `windows[]` in JSON |
| Save within budget, no logout block | `save_duration_ms` ≪ 10000; logout proceeds normally |
| Restore prompt before any relaunch | the notification appears first |
| Dismiss relaunches nothing | run once, click Dismiss, no apps open |
| Apps relaunch on confirm | the 4 apps reappear |
| Chrome reopens its tabs | the exact tabs come back |
| In-app state where a handler exists | terminal lands in `~/projects` |
| Apps without a handler relaunch fresh | open e.g. a calculator; it reopens blank, no error |
| Geometry near saved positions | windows land roughly where they were |
| Works on a fresh VM (same NFS home) | VM-B (or changed hostname) restores VM-A's session |
| Failed relaunch doesn't crash desktop | rename a binary, restore, see it reported, desktop fine |
| Stale state discarded, no prompt | `touch -d '2 days ago'` the file, log in, no prompt |
| `.deb` installs cleanly | the `apt install` in step 0 |

## 6. Quick teardown / reset between takes

```sh
rm -f ~/.local/share/jiopc/hibernate/session-state*.json
```
