# Install Guide
Target: **Ubuntu 24.04 + LXQt + X11**. It saves open GUI apps into the user's
home and restores them on the next login, even on another VM.
## 1. Dependencies
```sh
sudo apt update
sudo apt install -y python3 wmctrl libnotify-bin xprintidle
sudo apt install -y xdotool zenity x11-utils   # optional
```
`wmctrl` captures X11 windows, `notify-send` shows prompts, and `xprintidle` supports inactivity saves.
## 2. Build And Install
```sh
packaging/build-deb.sh
if in case of permission denied: use "chmod +x packaging/build-deb.sh" and again try the above
sudo apt install ./packaging/dist/jiopc-hibernate_1.0.0_all.deb
```
On non-Debian systems, validate layout only with `packaging/build-deb.sh --stage`.
## 3. What Gets Installed
The package installs the CLI, guard, restore service, handler registry, XDG autostart files, and LXQt logout wrapper.
It diverts `/usr/bin/lxqt-leave` so `jiopc-hibernate-leave` runs first.
The wrapper saves before LXQt closes windows, then calls `/usr/bin/lxqt-leave.real` with the same arguments, so normal logout still works.
## 4. Verify Install
```sh
jiopc-hibernate status
ls /etc/xdg/autostart/jiopc-hibernate-*.desktop
dpkg-divert --list /usr/bin/lxqt-leave
ls -l /usr/bin/lxqt-leave /usr/bin/lxqt-leave.real
lxqt-leave
```
Expected: the normal LXQt leave dialog opens.
## 5. Test Manual Capture
Open terminal, file manager, and text editor, then run:
```sh
jiopc-hibernate enumerate
jiopc-hibernate save --trigger user_disconnect
python3 -m json.tool ~/.local/share/jiopc/hibernate/session-state.json
```
Expected: `window_count > 0` and `windows` lists the open apps.
## 6. Test Real Logout
Open the same apps, click the actual LXQt logout/disconnect button, log in again, then inspect:
```sh
python3 -m json.tool ~/.local/share/jiopc/hibernate/session-state.json
```
If restore already consumed it, inspect `session-state-last.json`. The newest
state should contain real windows, not `"windows": []`.
## 7. Important Paths
`~/.local/share/jiopc/hibernate/session-state.json` - restore target
`~/.local/share/jiopc/hibernate/session-state-last.json` - consumed state
`~/.local/share/jiopc/hibernate/logs/hibernate.log` - logs
`~/.config/jiopc-hibernate/config.json` - user config
`~/.config/jiopc-hibernate/handlers.json` - handler override
## 8. Uninstall And Troubleshoot
```sh
sudo apt remove jiopc-hibernate
rm -f ~/.local/share/jiopc/hibernate/session-state*.json   # optional cleanup
```
If no windows are captured, confirm `echo "$XDG_SESSION_TYPE"` is `x11` and
`wmctrl -lpGx` lists windows. If the restore prompt fails, run
`jiopc-hibernate restore` manually and check `notify-send`.
