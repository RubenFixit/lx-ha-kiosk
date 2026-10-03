import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('kiosk', Path(__file__).parents[1] / 'scripts/kiosk.py')
k = importlib.util.module_from_spec(spec)
spec.loader.exec_module(k)


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.root = self.home / '.local/share/lx-ha-kiosk'
        self.cfg = self.home / '.config/lx-ha-kiosk/device.json'
        self.source = self.home / 'device.json'
        self.source.write_text(json.dumps({'web_url': 'https://ha.example/dashboard', 'web_zoom': 1.0}))
        self.patches = [patch.object(Path, 'home', return_value=self.home),
                        patch.object(k, 'ROOT', self.root), patch.object(k, 'CFG', self.cfg),
                        patch.object(k, 'MANIFEST', self.root / 'manifest.json'),
                        patch.object(k, 'platform_check', return_value='amd64'),
                        patch.object(k, 'user_manager_check'),
                        patch.object(k, 'home_check'),
                        patch.object(k, 'ctl'), patch.object(k.shutil, 'which', return_value='/usr/bin/touchkio'),
                        patch.object(k.subprocess, 'run', return_value=SimpleNamespace(returncode=1))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def args(self, mode='xdg'):
        return SimpleNamespace(config=str(self.source), autostart=mode,
                               skip_package=True, deb=None, version='latest')

    def test_repeat_install_and_uninstall_preserve_profile(self):
        profile = self.home / '.config/touchkio/Arguments.json'
        profile.parent.mkdir(parents=True)
        profile.write_text('existing settings')
        k.install(self.args())
        first = k.MANIFEST.read_bytes()
        k.install(self.args())
        self.assertEqual(first, k.MANIFEST.read_bytes())
        k.uninstall()
        k.uninstall()
        self.assertEqual(profile.read_text(), 'existing settings')
        self.assertFalse(self.cfg.exists())

    def test_labwc_retains_unrelated_edits(self):
        autostart = self.home / '.config/labwc/autostart'
        autostart.parent.mkdir(parents=True)
        autostart.write_text('existing-command &\n')
        k.install(self.args('labwc'))
        k.install(self.args('labwc'))
        autostart.write_bytes(autostart.read_bytes() + b'later-command &\n')
        k.uninstall()
        self.assertEqual(autostart.read_text(), 'existing-command &\nlater-command &\n')

    def test_collision_is_not_overwritten(self):
        self.cfg.parent.mkdir(parents=True)
        self.cfg.write_text('do not replace')
        with self.assertRaises(ValueError):
            k.install(self.args())
        self.assertEqual(self.cfg.read_text(), 'do not replace')

    def test_modified_managed_file_blocks_uninstall(self):
        k.install(self.args())
        self.cfg.write_text('user edits')
        with self.assertRaises(ValueError):
            k.uninstall()
        self.assertEqual(self.cfg.read_text(), 'user edits')

    def test_invalid_config(self):
        for c in ({'web_url': 'file:///etc/passwd'}, {'web_url': 'https://user:pass@ha/'},
                  {'web_url': 'https://ha/', 'web_widget': 'false'},
                  {'web_url': 'https://ha/', 'web_zoom': True},
                  {'web_url': 'https://ha/', 'mqtt_password': 'secret'}):
            self.source.write_text(json.dumps(c))
            with self.assertRaises(ValueError):
                k.config(self.source)

    def test_session_requires_display_and_imports_actual_environment(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                k.session_start()
        with patch.dict(os.environ, {'WAYLAND_DISPLAY': 'wayland-1'}, clear=True):
            k.session_start()
            k.ctl.assert_any_call('import-environment', 'WAYLAND_DISPLAY')

    def test_conflicting_upstream_service(self):
        k.subprocess.run.return_value.returncode = 0
        with self.assertRaises(ValueError):
            k.install(self.args())
        self.assertFalse(k.MANIFEST.exists())

    def test_missing_user_manager_blocks_package_install(self):
        k.user_manager_check.side_effect = ValueError('No user manager')
        with patch.object(k, 'package') as package:
            args = self.args()
            args.skip_package = False
            with self.assertRaises(ValueError):
                k.install(args)
            package.assert_not_called()
        self.assertFalse(k.MANIFEST.exists())

    def test_doctor_is_read_only(self):
        with patch.object(k, 'atomic') as atomic, patch.object(k, 'package') as package:
            k.doctor(SimpleNamespace(config=str(self.source), autostart='xdg'))
            atomic.assert_not_called()
            package.assert_not_called()
        self.assertFalse(self.root.exists())

    def test_supported_desktop_detection(self):
        for desktop, mode in [('LXDE-pi:labwc', 'labwc'), ('ubuntu:GNOME', 'xdg'), ('XFCE', 'xdg')]:
            with patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': desktop}, clear=True):
                self.assertEqual(k.session('auto'), mode)
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                k.session('auto')

    def test_all_device_examples_validate(self):
        for example in (Path(__file__).parents[1] / 'examples').glob('*.json'):
            with self.subTest(example=example.name):
                k.config(example)


if __name__ == '__main__':
    unittest.main()
