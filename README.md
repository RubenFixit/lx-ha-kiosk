# lx-ha-kiosk

Per-device configuration and reversible management scripts for Home Assistant touchscreen kiosks. Uses [TouchKio](https://github.com/leukipp/touchkio); does not implement a browser or an HA permission system. Official [installation/configuration](https://github.com/leukipp/touchkio/blob/main/README.md), [installer](https://github.com/leukipp/touchkio/blob/main/install.sh), and [hardware notes](https://github.com/leukipp/touchkio/blob/main/HARDWARE.md) were reviewed on 2026-10-03.

## Requirements

- Raspberry Pi 4 with **64-bit Raspberry Pi OS Desktop**, or Debian ARM64/x86-64 with a working desktop, systemd user manager, Python 3.9+, apt, sudo, and network access.
- A working touchscreen configured through the OS before installation. Pi example targets the **original official 7-inch 800×480 DSI display**, not Touch Display 2. Use landscape orientation and start with zoom 1.0; design a compact HA dashboard with large touch targets. Verify touch alignment and all four screen corners before installing.
- Run as the account that will log into the kiosk desktop. Do not run the script with sudo. Only package installation requests sudo.
- A logged-in desktop is required. Desktop autologin is an optional, separate OS decision; this repository never enables it, changes screen locking, rewrites boot configuration, or disables blanking.

The original panel's DSI connector, power wiring, orientation, and touch mapping must already work. Connect hardware with power off and follow the manufacturer's guide. No overlays or backlight privileges are installed. Other Debian touchscreen computers use the second example; native ARM64 and amd64 userland must match their kernel architecture. 32-bit Pi OS is rejected.

## First installation

Copy this repository to the device. In a terminal **inside its desktop session**:

```sh
cp examples/pi4-original-7inch.json device.json
# Edit web_url to your actual HA dashboard URL; choose theme and zoom.
sh scripts/lx-ha-kiosk install --config device.json
sh scripts/lx-ha-kiosk session-start
```

For other computers, start with `examples/debian-touchscreen.json`. The URL in each example is a placeholder; no HA credentials are embedded. Log in to HA interactively using an appropriately limited, dedicated non-administrator account. Keep a keyboard or remote desktop available for the initial login. Browser authentication remains in TouchKio's own profile.

Automatic desktop detection selects a managed block in `~/.config/labwc/autostart` for labwc, or an XDG desktop autostart entry for GNOME, KDE, XFCE, LXDE, LXQt, MATE and Cinnamon. Unknown sessions fail with instructions instead of guessing. If detection is unavailable over SSH, explicitly select `--autostart labwc` or `--autostart xdg` only after verifying the actual desktop's support. Bare Wayland compositors are not assumed to support XDG autostart. Session startup imports actual display variables into the user service; it never assumes `:0` or `wayland-0`. SSH installation alone does not start the GUI; log in locally afterwards.

The manager downloads a stable official GitHub release, checks the release SHA256 digest when one is supplied, validates the Debian package name/architecture, and installs through apt. A missing upstream digest is reported. For reviewed/offline packages use:

```sh
sh scripts/lx-ha-kiosk install --config device.json --deb /absolute/path/touchkio_VERSION_arm64.deb
# Or retain an already-installed TouchKio package:
sh scripts/lx-ha-kiosk install --config device.json --skip-package
```

An active or enabled upstream `touchkio.service` blocks installation to avoid two kiosk instances. If replacing that startup is intentional, first record its current state, then explicitly stop and disable it with `systemctl --user disable --now touchkio.service`. Its service file and settings remain intact. Check for other manually launched TouchKio processes or existing desktop startup entries yourself.

## Management

```sh
sh scripts/lx-ha-kiosk status
sh scripts/lx-ha-kiosk stop
sh scripts/lx-ha-kiosk start
sh scripts/lx-ha-kiosk restart
sh scripts/lx-ha-kiosk update
sh scripts/lx-ha-kiosk update --version v1.4.2   # example tag, choose a reviewed release
sh scripts/lx-ha-kiosk update --deb /absolute/path/reviewed-package.deb
sh scripts/lx-ha-kiosk uninstall
```

Update installs over the existing package and restarts only if the managed kiosk is running. It preserves device settings and browser login. Running install again with the same input is idempotent. To change settings, edit your **source** `device.json`, rerun install with `--skip-package` and the same autostart method, then restart. Avoid concurrent management commands.

The stable installed manager lives in `~/.local/share/lx-ha-kiosk/manager.py`, so moving the checkout does not break startup. It can be invoked directly with `python3` and these same subcommands. The unit is `lx-ha-kiosk.service`; it is started by desktop autostart rather than enabled at boot. Stop is temporary until the next desktop login. Uninstall removes managed autostart and unit files to disable future startup.

## Preservation and rollback

Managed device configuration is separate from `~/.config/touchkio/Arguments.json`; documented web options are passed on launch. Existing TouchKio settings and browser profile are never overwritten or deleted. This version accepts only web settings, not MQTT credentials. Any existing MQTT settings in the TouchKio profile remain upstream behavior: review that profile before deployment.

The ownership manifest records each managed file's hash. A collision is refused. Edited/missing managed files block reinstall/update/uninstall, preserving your work. Reconcile them against the recorded installation first: save your edits, restore the original managed content, then rerun the operation. The labwc block is removed independently, so unrelated changes made after installation survive. Its initial content is also retained as `~/.local/share/lx-ha-kiosk/labwc-autostart.before`. If interrupted between manifest and block creation, preserve the current file and reconcile the missing block before retrying; installation is not a transaction across apt and desktop files.

Uninstall retains the TouchKio package, apt dependencies, browser profile and labwc backup. Package removal is an explicit optional OS action: `sudo apt-get remove touchkio`. Do not purge or autoremove packages without reviewing what your machine uses. If you disabled an earlier upstream startup, restore its recorded enable/running state yourself after uninstall.

For package rollback, retain a reviewed earlier `.deb`, stop the kiosk and install it with apt's explicit downgrade option after reviewing the package version. A downgrade may not reverse browser profile migrations; back up the TouchKio profile **while stopped** before upgrades. This repository does not claim to undo third-party apt maintainer scripts.

## Recovery and verification on the device

The service retries exits after ten seconds, limited to five starts per two minutes to avoid a crash loop. `restart` resets the failure limit. It does not detect a frozen renderer or a stale dashboard; use restart after inspecting the logs. HA/network outages are left to TouchKio and the dashboard; no destructive profile reset is performed.

```sh
journalctl --user -u lx-ha-kiosk.service -b --no-pager
systemctl --user status lx-ha-kiosk.service
# Additional application log: ~/.config/touchkio/logs/main.log
```

If startup fails, confirm desktop session and display environment, package architecture, user systemd availability, URL reachability, and absence of duplicate kiosk processes. For direct debugging, stop the service and launch `touchkio` in a desktop terminal with your web URL. Review OS screen blanking settings separately. The unit follows `graphical-session.target` when the desktop manages that target; on desktops that do not, explicitly stop the kiosk before logging out or switching users. Multi-seat/user switching is not supported by this initial version.

Device acceptance checklist: log out/in and reboot; confirm exactly one kiosk starts; test touch at 800×480 on the original Pi panel; authenticate to HA; disconnect/reconnect network; terminate TouchKio and verify bounded restart; test stop/restart/uninstall; verify prior desktop commands and profile remain. These require real hardware and have **not** been run locally.

## Home Assistant cards and OS locking

Install [Restriction Card](https://github.com/iantrich/restriction-card) in HA separately, then use `examples/ha-restriction-card.yaml` as a card-level PIN prompt. Replace its demonstration PIN and entity. This is an interaction guard against accidental use; the PIN is visible in frontend configuration and can be bypassed. It is not authorization, a secure device lock, or a replacement for HA user permissions.

Optional [Lovelace WallPanel](https://github.com/j-a-n/lovelace-wallpanel) can show informational screensaver cards; follow its [info-box documentation](https://j-a-n.github.io/lovelace-wallpanel/info-box/) after installing it as an HA frontend resource. Configure weather, clock or calendar information in HA. This is separate from TouchKio startup and OS display power/blanking. A screensaver is not authentication. This repository does not promise a live browser dashboard on a secure OS lock screen; choose OS locking or an unlocked visible kiosk according to your needs.

Future voice work should use [OHF Linux Voice Assistant](https://github.com/OHF-Voice/linux-voice-assistant) through the ESPHome protocol. Begin with a deliberate button activation and microphone/speaker testing; consider wake words later. No microphone services or voice dependencies are installed here.

## Local checks and scope

```sh
python3 -m unittest discover -s tests -v
sh -n scripts/lx-ha-kiosk
python3 scripts/kiosk.py --help
```

Tests simulate per-user deployment and service commands, including repeated installs, edited-file refusal, profile preservation, labwc edits and display environment handling. They do not install Debian packages, start Electron, or prove hardware compatibility. This initial implementation was checked on a Windows development host. Deployment needs the target OS/session, actual HA URL, kiosk account and a reviewed release.

## Management direction

The inventory and device-variable structure in [rpi-ha-kiosk](https://github.com/kr1schan/rpi-ha-kiosk) is a useful model for a future optional Ansible deployment layer. Keep that layer separate from the local install/update/status/restart/uninstall interface. Its Firefox-specific workarounds and Touch Display 2 defaults should not be applied to TouchKio or the original 800×480 panel without testing. Display, GPIO, autologin and permission changes should remain explicit device choices with rollback support. No code from that project is included here.
