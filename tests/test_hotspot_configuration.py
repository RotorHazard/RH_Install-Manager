"""Hotspot configuration with all privileged operations redirected to temp fixtures."""
import ast
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from test_version_selection import ROOT, load_function


VALUES = [('Timer with spaces', 'pass with spaces'),
          ('quotes\'"$;`touch injected`', '$(touch injected);"\'password'),
          ('line one\nline two', 'password\n$(touch injected)')]


write_json = load_function('modules.py', 'write_json', os=os, tempfile=tempfile,
                           json=json, SimpleNamespace=SimpleNamespace)


class HotspotPythonTests(unittest.TestCase):
    def test_credentials_are_exact_arguments_without_shell_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'scripts').mkdir()
            script = root / 'scripts/net_hotspot_auto_12.sh'
            script.write_text('#!' + sys.executable + '\nimport json, sys\n'
                              'open("arguments", "w").write(json.dumps(sys.argv[1:]))\n')
            script.chmod(0o700)
            save = load_function('net_hotspot_auto_12.py', 'save_config_os', subprocess=subprocess)
            # Only this harmless argument recorder is run from the temporary checkout.
            previous = os.getcwd()
            try:
                os.chdir(directory)
                for ssid, password in VALUES:
                    self.assertTrue(save(ssid, password))
                    self.assertEqual(json.loads((root / 'arguments').read_text()), [ssid, password])
                    self.assertFalse((root / 'injected').exists())
            finally:
                os.chdir(previous)

    def test_setup_failures_keep_ap_config_and_do_not_report_success(self):
        for failure in (SimpleNamespace(returncode=7), OSError('not executable'),
                        ValueError('embedded null byte')):
            with self.subTest(failure=type(failure).__name__), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / 'RH_Install-Manager').mkdir()
                config = root / 'RH_Install-Manager/ap-config.json'
                config.write_text('{"previous": true}\n')
                run = Mock(**({'side_effect': failure} if isinstance(failure, Exception)
                              else {'return_value': failure}))
                save = load_function('net_hotspot_auto_12.py', 'save_config_os',
                                     subprocess=SimpleNamespace(run=run))
                configure = load_function(
                    'net_hotspot_auto_12.py', 'do_config', Path=SimpleNamespace(home=lambda: root),
                    conf_check=lambda: True, clear_the_screen=Mock(), logo_top=Mock(),
                    input=Mock(side_effect=['test ssid', 'test password', 'yes', '']),
                    save_config_os=save, write_json=write_json, sleep=Mock(), show_ip=Mock())
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(configure(), 0)
                self.assertEqual(config.read_text(), '{"previous": true}\n')
                self.assertNotIn('has been saved', output.getvalue())
                self.assertNotIn('Current configuration:', output.getvalue())
                self.assertIn('Hotspot configuration failed' if run.return_value is failure
                              else 'Could not run hotspot configuration', output.getvalue())

    def test_config_is_written_only_after_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'RH_Install-Manager').mkdir()
            config = root / 'RH_Install-Manager/ap-config.json'
            config.write_text('{"previous": true}')

            def apply(ssid, password):
                self.assertEqual(config.read_text(), '{"previous": true}')
                return True

            configure = load_function(
                'net_hotspot_auto_12.py', 'do_config', Path=SimpleNamespace(home=lambda: root),
                conf_check=lambda: True, clear_the_screen=Mock(), logo_top=Mock(),
                input=Mock(side_effect=['test ssid', 'test password', 'yes', '']),
                save_config_os=apply, write_json=write_json, sleep=Mock(), show_ip=lambda: ('eth', 'wifi'))
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(configure(), 0)
            self.assertEqual(json.loads(config.read_text()),
                             {'WIFI': {'SSID': 'test ssid', 'PASSWORD': 'test password'}})
            self.assertIn('has been saved', output.getvalue())

    def test_runtime_python36_syntax(self):
        ast.parse((ROOT / 'net_hotspot_auto_12.py').read_text(), feature_version=(3, 6))

    def test_config_save_error_is_reported_without_success(self):
        configure = load_function(
            'net_hotspot_auto_12.py', 'do_config', Path=SimpleNamespace(home=lambda: '/unused'),
            conf_check=lambda: True, clear_the_screen=Mock(), logo_top=Mock(),
            input=Mock(side_effect=['test ssid', 'test password', 'yes', '']),
            save_config_os=Mock(return_value=True), sleep=Mock(),
            write_json=Mock(side_effect=PermissionError('read-only config')))
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(configure(), 0)
        self.assertIn('could not be saved', output.getvalue())
        self.assertNotIn('has been saved', output.getvalue())


class HotspotShellTests(unittest.TestCase):
    # Never delegate sudo to the host. Accept only the exact expected operations,
    # and map both absolute output paths into WORK before executing safe file tools.
    HARNESS = r'''
sudo() {
    case "$*" in
        'install -m 700 /dev/null /home/fixture/hotspot.sh')
            [ "$FAIL" != install ] || return 7
            command install -m 700 /dev/null "$WORK/hotspot.sh" ;;
        'tee /home/fixture/hotspot.sh')
            [ "$FAIL" != script ] || return 7
            command tee "$WORK/hotspot.sh" ;;
        'tee /etc/systemd/system/hotspot.service')
            [ "$FAIL" != service ] || return 7
            command tee "$WORK/hotspot.service" ;;
        'systemctl daemon-reload'|'systemctl enable hotspot.service')
            printf '%s\n' "$*" >> "$WORK/calls"
            [ "$FAIL" != "$2" ] ;;
        *) echo "Unexpected privileged operation" >&2; return 99 ;;
    esac
}
'''

    def run_setup(self, root, ssid, password, fail=''):
        script = (ROOT / 'scripts/net_hotspot_auto_12.sh').read_text()
        self.assertNotIn('sudo rm', script)
        return subprocess.run(
            [self.bash, '--noprofile', '--norc', '-c', self.HARNESS + script,
             'hotspot-setup', ssid, password], cwd=str(root),
            env={'PATH': os.defpath, 'LC_ALL': 'C', 'USER': 'fixture',
                 'WORK': str(root), 'FAIL': fail},
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)

    def setUp(self):
        self.bash = shutil.which('bash', path=os.defpath)
        self.assertIsNotNone(self.bash)

    def test_generated_script_preserves_arguments_and_service_behavior(self):
        for ssid, password in VALUES:
            with self.subTest(ssid=ssid), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                result = self.run_setup(root, ssid, password)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn(password, result.stdout)
                script = root / 'hotspot.sh'
                self.assertEqual(script.stat().st_mode & 0o777, 0o700)
                self.assertIn('ExecStart=sudo /home/fixture/hotspot.sh',
                              (root / 'hotspot.service').read_text())
                self.assertEqual((root / 'calls').read_text().splitlines(),
                                 ['systemctl daemon-reload', 'systemctl enable hotspot.service'])
                runtime = r'''
iwgetid() { if [ "$CONNECTED" = yes ]; then echo known-network; fi; }
nmcli() { printf '%s\0' "$@" > "$WORK/arguments"; return "$NMCLI_STATUS"; }
source "$WORK/hotspot.sh"
'''
                for connected, status in (('no', '0'), ('no', '7'), ('yes', '0')):
                    arguments = root / 'arguments'
                    if arguments.exists():
                        arguments.unlink()
                    run = subprocess.run(
                        [self.bash, '--noprofile', '--norc', '-c', runtime], cwd=directory,
                        env={'PATH': os.defpath, 'WORK': directory, 'CONNECTED': connected,
                             'NMCLI_STATUS': status}, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        timeout=10)
                    self.assertEqual(run.returncode, int(status), run.stderr)
                    if connected == 'no':
                        self.assertEqual(arguments.read_bytes().split(b'\0')[:-1],
                                         [value.encode() for value in
                                          ['dev', 'wifi', 'hotspot', 'ifname', 'wlan0',
                                           'ssid', ssid, 'password', password]])
                    else:
                        self.assertFalse(arguments.exists())
                    self.assertFalse((root / 'injected').exists())

    def test_each_required_operation_failure_stops_without_success(self):
        for failure in ('install', 'script', 'service', 'daemon-reload', 'enable'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                result = self.run_setup(root, 'test ssid', 'test password', fail=failure)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Hotspot configuration failed:', result.stderr)
                self.assertNotIn('AccessPoint enabled', result.stdout)
                if failure != 'enable':
                    self.assertNotIn('systemctl enable', (root / 'calls').read_text()
                                     if (root / 'calls').exists() else '')


if __name__ == '__main__':
    unittest.main()
