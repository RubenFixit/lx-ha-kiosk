# Set up the first two kiosks

Install the OS normally and verify touch input first. Run the following commands locally in the logged-in desktop, as the account that will run the kiosk. No Ansible controller or SSH configuration is required.

## Raspberry Pi 4 and original official 7-inch touchscreen

Use 64-bit Raspberry Pi OS **Desktop**. The original panel is 800×480. Check the OS display settings for landscape orientation and test touch at every corner. This project does not force a display mode or touch calibration.

```sh
git clone https://github.com/RubenFixit/lx-ha-kiosk.git
cd lx-ha-kiosk
cp examples/pi4-original-7inch.json device.json
```

Edit `device.json` with a text editor. Set `web_url` to your Home Assistant kiosk dashboard; keep zoom 1.0 initially. The example URL is a placeholder, not a dashboard this project creates.

```sh
sh scripts/lx-ha-kiosk doctor --config device.json
sh scripts/lx-ha-kiosk install --config device.json
sh scripts/lx-ha-kiosk session-start
```

On a labwc desktop the manager selects a labwc autostart block. If detection fails, confirm the actual desktop before passing `--autostart labwc` to both doctor and install. Older X11 desktops may use XDG autostart instead; do not select labwc merely because this is a Pi.

## HP Pavilion x360 convertible with Ubuntu

Use a 64-bit Ubuntu desktop installation. Confirm the built-in screen is set to 1366×768, touchscreen taps align, and the desktop works in the intended laptop/tablet position. Model-specific touch, hinge, rotation and suspend behavior remain OS responsibilities.

```sh
git clone https://github.com/RubenFixit/lx-ha-kiosk.git
cd lx-ha-kiosk
cp examples/ubuntu-hp-x360.json device.json
```

Edit the URL and begin with zoom 1.0. Increase toward 1.25 if you prefer larger controls. OS display scaling and TouchKio zoom both affect available dashboard space; inspect the result before changing both.

```sh
sh scripts/lx-ha-kiosk doctor --config device.json
sh scripts/lx-ha-kiosk install --config device.json
sh scripts/lx-ha-kiosk session-start
```

Ubuntu GNOME normally selects XDG autostart. Basic dashboard use is the initial goal. TouchKio's [hardware notes](https://github.com/leukipp/touchkio/blob/main/HARDWARE.md) document limited extended display/keyboard control on GNOME, especially Wayland. Do not assume its sidebar keyboard, remote display power or brightness controls work on this laptop. Use the physical keyboard for initial login and test Ubuntu's own on-screen keyboard separately. No desktop replacement or blanket sandbox disabling is part of this setup.

Choose lid, suspend, screen blanking and lock behavior in Ubuntu settings. A suspended laptop cannot keep displaying the dashboard; a secure lock screen does not expose the running browser. No settings are changed automatically.

## What doctor checks

The read-only command checks supported kernel/userland architecture, required commands, access to the user service manager, known desktop/autostart selection, upstream service conflicts, managed file integrity, and the supplied device JSON. It prints no user service environment values, performs no URL request, and uses no sudo. A failure must be corrected before installing. A successful check does not prove that the hardware, website, or OS on-screen keyboard works.

If a required tool such as git or Python is missing, install it through your OS package manager first. Run doctor from the desktop rather than a root shell. Keep normal authentication and package trust settings intact.

## First-use acceptance

1. Log into HA interactively. Confirm the intended dashboard and touch targets fit the screen.
2. Stop and restart with `sh scripts/lx-ha-kiosk stop` and `sh scripts/lx-ha-kiosk restart`.
3. Log out/in and then reboot; verify a single kiosk starts after desktop login.
4. Disconnect/reconnect the network and check dashboard recovery. Restart if needed.
5. Test touch, scrolling and text entry. On the laptop also test tablet position, lid and suspend/resume with your chosen OS settings.
6. Configure Restriction Card and optional WallPanel inside HA separately using the main README.

For subsequent repository changes, run `git pull --ff-only`, then rerun install with `--config device.json --skip-package` to refresh the installed manager/configuration. Restart afterwards. The `update` subcommand updates the **TouchKio package**, not this Git checkout or its installed manager.

The repository needs no HA password or token. Keep device configuration local. If either device fails, collect the doctor output and `journalctl --user -u lx-ha-kiosk.service -b` output, reviewing logs for private URLs/data before sharing. This project has not been deployed to either device yet.
