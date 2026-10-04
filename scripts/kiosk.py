#!/usr/bin/env python3
"""Small, per-user TouchKio deployment manager; Python standard library only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.request
from urllib.parse import urlparse

UNIT = 'lx-ha-kiosk.service'
ROOT = Path.home() / '.local/share/lx-ha-kiosk'
CFG = Path.home() / '.config/lx-ha-kiosk/device.json'
MANIFEST = ROOT / 'manifest.json'
BEGIN = '# BEGIN lx-ha-kiosk managed autostart\n'
END = '# END lx-ha-kiosk managed autostart\n'


def run(*args, check=True):
    return subprocess.run(args, check=check, text=True, capture_output=False)


def ctl(*args, check=True):
    return run('systemctl', '--user', *args, check=check)


def reset_failed():
    # systemd may unload an inactive unit with no recorded failure. Resetting
    # that unit is optional; the subsequent start/restart reports real errors.
    subprocess.run(['systemctl', '--user', 'reset-failed', UNIT],
                   text=True, capture_output=True, check=False)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic(path, data, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def config(path):
    c = json.loads(path.read_text())
    allowed = {'web_url', 'web_theme', 'web_zoom', 'web_widget', 'web_pager'}
    if not isinstance(c, dict) or set(c) - allowed:
        raise ValueError('Only documented web_* settings are accepted; see examples.')
    u = urlparse(c.get('web_url', ''))
    if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password:
        raise ValueError('web_url must be an HTTP(S) URL without credentials.')
    if c.get('web_theme', 'dark') not in ('dark', 'light'):
        raise ValueError('web_theme must be dark or light.')
    z = c.get('web_zoom', 1.0)
    if isinstance(z, bool) or not isinstance(z, (int, float)) or not 0.5 <= z <= 3:
        raise ValueError('web_zoom must be between 0.5 and 3.')
    for key in ('web_widget', 'web_pager'):
        if key in c and not isinstance(c[key], bool):
            raise ValueError(key + ' must be a JSON boolean.')
    return c


def load():
    return json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {'files': {}}


def verify(m):
    for name, expected in m['files'].items():
        p = Path(name)
        if p.is_symlink() or not p.exists() or digest(p.read_bytes()) != expected:
            raise ValueError('Managed file changed or missing; preserve/reconcile it first: ' + name)
    if 'labwc' in m:
        p = Path(m['labwc'])
        if p.is_symlink() or not p.exists() or p.read_bytes().count(m['block'].encode()) != 1:
            raise ValueError('Managed labwc block changed; reconcile it first.')


def session(mode):
    if mode != 'auto':
        return mode
    desktop = (os.environ.get('XDG_CURRENT_DESKTOP', '') + ' ' +
               os.environ.get('XDG_SESSION_DESKTOP', '')).lower()
    if 'labwc' in desktop:
        return 'labwc'
    if any(x in desktop for x in ('gnome', 'kde', 'xfce', 'lxde', 'lxqt', 'mate', 'cinnamon')):
        return 'xdg'
    raise ValueError('Unknown desktop. Run in a desktop terminal, or select --autostart labwc|xdg after checking session support.')


def platform_check():
    if platform.system() != 'Linux' or not Path('/etc/debian_version').exists():
        raise ValueError('Installation requires Debian Linux or Raspberry Pi OS.')
    arch = {'aarch64': 'arm64', 'x86_64': 'amd64'}.get(platform.machine())
    if not arch or sys.maxsize <= 2**32:
        raise ValueError('Use a 64-bit ARM64 or x86-64 OS; 32-bit Pi OS is unsupported.')
    native = subprocess.check_output(['dpkg', '--print-architecture'], text=True).strip()
    if native != arch:
        raise ValueError('Kernel and Debian userland architecture must match.')
    return arch


def user_manager_check():
    result = subprocess.run(['systemctl', '--user', 'show-environment'],
                            text=True, capture_output=True)
    if result.returncode:
        raise ValueError('User systemd manager is unavailable. Run as the kiosk user in its logged-in desktop; no packages or settings were changed.')


def home_check():
    if not re.fullmatch(r'[A-Za-z0-9_/.-]+', str(Path.home())):
        raise ValueError('This initial version requires a home path without spaces or special characters.')


def conflict_check():
    for state in ('is-active', 'is-enabled'):
        result = subprocess.run(['systemctl', '--user', '--quiet', state, 'touchkio.service'])
        if result.returncode == 0:
            raise ValueError('Existing touchkio.service conflicts. Stop/disable it explicitly before proceeding; its files are preserved.')


def doctor(args):
    """Read-only prerequisite checks; intentionally no sudo or network access."""
    arch = platform_check()
    home_check()
    for command in ('python3', 'systemctl', 'apt-get', 'dpkg-deb', 'sudo'):
        if not shutil.which(command):
            raise ValueError('Required command missing: ' + command)
    user_manager_check()
    conflict_check()
    verify(load())
    mode = session(args.autostart)
    if args.config:
        config(Path(args.config))
        print('Device configuration: valid')
    print('Architecture:', arch)
    print('Autostart:', mode)
    print('TouchKio:', 'installed' if shutil.which('touchkio') else 'will be installed')
    print('Display environment:', 'available' if os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY') else 'not available; start from the desktop later')
    print('Prerequisites passed. URL reachability, touchscreen behavior and HA login still need on-device verification.')


def package(deb, version):
    arch = platform_check()
    with tempfile.TemporaryDirectory(prefix='lx-ha-kiosk-') as tmp:
        if deb:
            target = Path(deb).resolve()
        else:
            suffix = 'latest' if version == 'latest' else 'tags/' + version
            if version != 'latest' and not re.fullmatch(r'v?\d+\.\d+\.\d+', version):
                raise ValueError('Version must be latest or a stable tag such as v1.4.2.')
            req = urllib.request.Request('https://api.github.com/repos/leukipp/touchkio/releases/' + suffix,
                                         headers={'User-Agent': 'lx-ha-kiosk'})
            with urllib.request.urlopen(req, timeout=30) as r:
                release = json.load(r)
            if release.get('prerelease') or release.get('draft'):
                raise ValueError('Only stable releases are supported.')
            upstream_arch = 'x64' if arch == 'amd64' else arch
            assets = [a for a in release['assets'] if a['name'].endswith('_' + upstream_arch + '.deb')]
            if len(assets) != 1:
                raise ValueError('Expected exactly one matching official .deb asset.')
            asset = assets[0]
            url = asset['browser_download_url']
            if not url.startswith('https://github.com/leukipp/touchkio/releases/download/'):
                raise ValueError('Unexpected release download URL.')
            target = Path(tmp) / asset['name']
            with urllib.request.urlopen(url, timeout=120) as r, target.open('wb') as f:
                shutil.copyfileobj(r, f)
            expected = asset.get('digest')
            if expected and expected.startswith('sha256:'):
                if digest(target.read_bytes()) != expected.split(':', 1)[1]:
                    raise ValueError('Release checksum mismatch.')
            else:
                print('Upstream supplied no SHA256 digest; relying on HTTPS. Use --deb for an independently verified package.')
        fields = subprocess.check_output(['dpkg-deb', '-f', str(target), 'Package', 'Architecture'], text=True)
        values = dict(line.split(': ', 1) for line in fields.strip().splitlines())
        if values.get('Package') != 'touchkio' or values.get('Architecture') != arch:
            raise ValueError('Package name or Debian architecture mismatch.')
        # apt's sandbox user must be able to read the temporary download.
        os.chmod(tmp, 0o755)
        if not deb:
            os.chmod(target, 0o644)
        run('sudo', 'apt-get', 'install', '-y', str(target))


def install(args):
    c = config(Path(args.config))
    platform_check()
    mode = session(args.autostart)
    home_check()
    user_manager_check()
    m = load()
    verify(m)
    if m.get('mode', mode) != mode:
        raise ValueError('Uninstall before changing autostart method.')
    conflict_check()
    starter = f'/usr/bin/python3 {ROOT}/manager.py session-start'
    service = ('[Unit]\nDescription=Home Assistant TouchKio kiosk\n'
               'PartOf=graphical-session.target\nStartLimitIntervalSec=120\nStartLimitBurst=5\n'
               f'[Service]\nExecStart=/usr/bin/python3 {ROOT}/manager.py launch\n'
               'Restart=always\nRestartSec=10\nTimeoutStopSec=15\nKillMode=control-group\n')
    files = {ROOT / 'manager.py': Path(__file__).read_bytes(),
             CFG: (json.dumps(c, indent=2) + '\n').encode(),
             Path.home() / '.config/systemd/user' / UNIT: service.encode()}
    if mode == 'xdg':
        files[Path.home() / '.config/autostart/lx-ha-kiosk.desktop'] = (
            '[Desktop Entry]\nType=Application\nName=Home Assistant Kiosk\n'
            f'Exec={starter}\nTerminal=false\n').encode()
    for p in files:
        if p.is_symlink() or (p.exists() and str(p) not in m['files']):
            raise ValueError('Refusing to overwrite existing file: ' + str(p))
    labwc = Path.home() / '.config/labwc/autostart'
    block = '\n' + BEGIN + starter + ' &\n' + END
    if mode == 'labwc' and 'labwc' not in m:
        if labwc.is_symlink() or (labwc.exists() and BEGIN in labwc.read_text()):
            raise ValueError('Unexpected existing labwc block or symlink.')
    if not args.skip_package:
        package(args.deb, args.version)
    elif not shutil.which('touchkio'):
        raise ValueError('--skip-package requires TouchKio already installed.')
    # Persist ownership after each write, so interrupted installs can be retried.
    for p, data in files.items():
        atomic(p, data)
        m['files'][str(p)] = digest(data)
        m['mode'] = mode
        atomic(MANIFEST, json.dumps(m, indent=2).encode())
    if mode == 'labwc' and 'labwc' not in m:
        old = labwc.read_bytes() if labwc.exists() else b''
        atomic(ROOT / 'labwc-autostart.before', old)
        m.update(labwc=str(labwc), block=block, labwc_existed=labwc.exists())
        atomic(MANIFEST, json.dumps(m, indent=2).encode())
        mode_bits = stat.S_IMODE(labwc.stat().st_mode) if labwc.exists() else 0o644
        atomic(labwc, old + block.encode(), mode_bits)
    ctl('daemon-reload')
    print('Installed. Log in to the desktop or run session-start there. Existing TouchKio profile is preserved.')


def session_start():
    if not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY'):
        raise ValueError('No desktop display environment; run from the logged-in desktop.')
    # Clear stale variables from a previous session, then import only actual values.
    names = ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'XDG_CURRENT_DESKTOP', 'XDG_SESSION_TYPE')
    ctl('unset-environment', *names)
    present = [n for n in names if os.environ.get(n)]
    ctl('import-environment', *present)
    reset_failed()
    ctl('start', UNIT)


def launch():
    c = config(CFG)
    executable = shutil.which('touchkio')
    if not executable:
        raise ValueError('TouchKio is missing.')
    argv = [executable] + ['--' + k.replace('_', '-') + '=' +
                          (str(v).lower() if isinstance(v, bool) else str(v)) for k, v in c.items()]
    os.execv(executable, argv)


def uninstall():
    if not MANIFEST.exists():
        print('No managed installation exists.')
        return
    m = load()
    verify(m)
    ctl('stop', UNIT)
    if 'labwc' in m:
        p = Path(m['labwc'])
        remaining = p.read_bytes().replace(m['block'].encode(), b'', 1)
        if not remaining and not m['labwc_existed']:
            p.unlink()
        else:
            atomic(p, remaining, stat.S_IMODE(p.stat().st_mode))
    for name in m['files']:
        Path(name).unlink()
    MANIFEST.unlink()
    ctl('daemon-reload')
    ctl('reset-failed', UNIT, check=False)
    print('Managed files removed; TouchKio package, browser profile, backup and dependencies retained.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    i = sub.add_parser('install')
    i.add_argument('--config', required=True)
    i.add_argument('--autostart', choices=['auto', 'labwc', 'xdg'], default='auto')
    i.add_argument('--version', default='latest')
    i.add_argument('--deb')
    i.add_argument('--skip-package', action='store_true')
    u = sub.add_parser('update')
    u.add_argument('--version', default='latest')
    u.add_argument('--deb')
    d = sub.add_parser('doctor', help='Read-only prerequisite and configuration checks')
    d.add_argument('--config')
    d.add_argument('--autostart', choices=['auto', 'labwc', 'xdg'], default='auto')
    for name in ('status', 'start', 'stop', 'restart', 'uninstall', 'session-start', 'launch'):
        sub.add_parser(name)
    args = p.parse_args()
    if hasattr(os, 'geteuid') and os.geteuid() == 0:
        p.error('Run as the kiosk desktop user, not root. Package installation alone uses sudo.')
    try:
        if args.command == 'install':
            install(args)
        elif args.command == 'doctor':
            doctor(args)
        elif args.command == 'update':
            if not MANIFEST.exists():
                raise ValueError('Install first.')
            verify(load())
            user_manager_check()
            package(args.deb, args.version)
            if subprocess.run(['systemctl', '--user', '--quiet', 'is-active', UNIT]).returncode == 0:
                ctl('restart', UNIT)
        elif args.command == 'session-start':
            session_start()
        elif args.command == 'launch':
            launch()
        elif args.command == 'uninstall':
            uninstall()
        else:
            if args.command == 'status':
                print('Managed installation:', MANIFEST.exists())
                print('Desktop:', os.environ.get('XDG_CURRENT_DESKTOP', 'unknown'))
                run('dpkg-query', '-W', 'touchkio', check=False)
            if args.command in ('start', 'restart'):
                reset_failed()
            result = ctl(args.command, UNIT, check=False)
            return result.returncode
    except (ValueError, OSError, subprocess.CalledProcessError) as e:
        print('Error:', e, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
