"""Run real Python -> Bash self-update with bounded filesystem command stubs."""
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
import zipfile

from test_version_selection import ROOT, load_function


# PATH contains only these stubs and interpreters; no host download/service command can run.
COMMAND_STUB = r'''
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

command = Path(sys.argv[0]).name
args = sys.argv[1:]
root = Path(os.environ['RHIM_TEST_ROOT']).resolve()
with (root / 'commands.jsonl').open('a') as stream:
    stream.write(json.dumps([command] + args) + '\n')
if command in ('sudo', 'systemctl', 'apt', 'apt-get', 'kill', 'pkill'):
    sys.exit('Forbidden host command: ' + command)
if command in ('sleep', 'pgrep'):
    sys.exit(1 if command == 'pgrep' else 0)
if command == 'wget':
    assert len(args) == 3 and args[1] == '-O'
    paths = [args[2]]
else:
    paths = [arg for arg in args if not arg.startswith('-')]
for value in paths:
    path = Path(value).resolve()
    assert root in path.parents, 'Unbounded command path: ' + value
failure = os.environ.get('RHIM_TEST_FAIL', '')
if (failure == command
        or failure == 'cp-ap' and command == 'cp' and args[-2].endswith('/ap-config.json')
        or failure in ('activate', 'activate-restore') and command == 'mv' and '/source/' in args[0]
        or failure == 'activate-restore' and command == 'mv' and '/RH_Install-Manager-backup.' in args[0]):
    sys.exit('Injected ' + failure + ' failure')
if command == 'wget':
    shutil.copyfile(str(root / 'replacement.zip'), args[2])
    sys.exit(0)
commands = json.loads(os.environ['RHIM_TEST_COMMANDS'])
sys.exit(subprocess.call([commands[command]] + args))
'''


class SelfUpdateIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='rhim-self-update-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / 'home with spaces'
        self.install = self.home / 'RH_Install-Manager'
        self.scripts = self.install / 'scripts'
        self.scripts.mkdir(parents=True)
        self.markers = self.home / '.rhim_markers'
        self.markers.mkdir()
        self.previous = self.markers / 'old_RH_Install-Manager'
        self.previous.mkdir()
        (self.previous / 'keep').write_text('earlier backup')
        self.unrelated = self.home / 'RH_Install-Manager-user-backup'
        self.unrelated.mkdir()
        (self.unrelated / 'keep').write_text('unrelated')
        (self.install / 'version.txt').write_text('old-version\n')
        (self.install / 'local-file').write_text('old installation')
        (self.install / 'updater-config.json').write_text('{"beta_tester": false, "local": "keep"}\n')
        (self.install / 'ap-config.json').write_text('{"hotspot": "keep"}\n')
        for name in ('self_updater.sh', 'updater_from_rhim.sh'):
            shutil.copy2(str(ROOT / 'scripts' / name), str(self.scripts / name))
        (self.scripts / 'net_fixer.sh').write_text('#!/bin/bash\nexit 97\n')
        (self.scripts / 'net_fixer.sh').chmod(0o700)
        # Only existing coordinator functions run. No application imports or network checks.
        harness = '''import os, subprocess, sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, {tests!r})
from test_version_selection import load_function
config = SimpleNamespace(beta_tester={branch!r})
operation = load_function('self_update.py', 'self_update', os=os, subprocess=subprocess,
    sleep=lambda seconds: None, internet_check=lambda: True, dots_show=lambda seconds: None,
    Bcolors=SimpleNamespace(RED='', GREEN='', ENDC=''),
    get_rhim_version=lambda mode: (Path(os.environ['HOME']) / 'RH_Install-Manager/version.txt').read_text().strip())
main = load_function('self_update.py', 'main', rhim_load_config=lambda: config, self_update=operation)
sys.exit(main())
'''
        self.harness = harness
        self.write_harness(False)
        self.original = self.manifest(self.install)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        commands = {}
        for command in ('mkdir', 'rmdir', 'mktemp', 'rm', 'unzip', 'chmod', 'cp', 'cmp', 'mv'):
            executable = shutil.which(command, path=os.defpath)
            self.assertIsNotNone(executable, command + ' is required')
            commands[command] = executable
        for command in tuple(commands) + ('wget', 'sleep', 'pgrep', 'sudo', 'systemctl',
                                          'apt', 'apt-get', 'kill', 'pkill'):
            path = self.bin / command
            path.write_text('#!' + sys.executable + '\n' + COMMAND_STUB)
            path.chmod(0o700)
        for command, executable in (('python3', sys.executable), ('bash', '/bin/bash'),
                                     ('grep', shutil.which('grep', path=os.defpath)),
                                     ('awk', shutil.which('awk', path=os.defpath))):
            (self.bin / command).symlink_to(executable)
        self.env = {'HOME': str(self.home), 'PATH': str(self.bin), 'LC_ALL': 'C',
                    'RHIM_TEST_ROOT': str(self.root), 'RHIM_TEST_COMMANDS': json.dumps(commands)}
        self.members = {name: "raise RuntimeError('Downloaded code must not run')\n"
                        for name in ('start_rhim.py', 'self_update.py', 'update.py', 'modules.py')}
        self.members.update({'rhim.sh': '#!/bin/bash\nexit 97\n',
                             'scripts/self_updater.sh': '#!/bin/bash\nexit 97\n',
                             'scripts/updater_from_rhim.sh': '#!/bin/bash\nexit 97\n',
                             'version.txt': 'new-version\n', 'distr-updater-config.json': '{}\n'})
        self.archive()

    def write_harness(self, branch):
        (self.install / 'self_update.py').write_text(self.harness.format(tests=str(ROOT / 'tests'), branch=branch))

    def archive(self, extra=None):
        with zipfile.ZipFile(str(self.root / 'replacement.zip'), 'w') as archive:
            for name, value in self.members.items():
                archive.writestr('Install-Manager-fixture/' + name, value)
            for name, value in (extra or {}).items():
                archive.writestr(name, value)

    def manifest(self, directory):
        return {str(path.relative_to(directory)): (path.read_bytes(), path.stat().st_mode & 0o777)
                for path in directory.rglob('*') if path.is_file()}

    def run_update(self, failure='', direct=False):
        env = dict(self.env, RHIM_TEST_FAIL=failure)
        command = ['bash', '--noprofile', '--norc',
                   str(self.scripts / ('self_updater.sh' if direct else 'updater_from_rhim.sh'))]
        if direct:
            command.append('stable')
        result = subprocess.run(command, env=env, cwd=str(self.install),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                universal_newlines=True, timeout=30)
        self.assertEqual((self.previous / 'keep').read_text(), 'earlier backup')
        self.assertEqual((self.unrelated / 'keep').read_text(), 'unrelated')
        self.assertFalse((self.markers / '.self-update-lock').exists())
        self.assertEqual(list(self.markers.glob('.self-update.*')), [])
        commands = [json.loads(line) for line in (self.root / 'commands.jsonl').read_text().splitlines()]
        self.assertFalse(any(command[0] in ('sudo', 'systemctl', 'apt', 'apt-get', 'kill', 'pkill')
                             for command in commands), result.stdout)
        return result, commands

    def assert_failed_intact(self, failure=''):
        result, commands = self.run_update(failure)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertNotIn('RotorHazard Manager updated to version', result.stdout)
        self.assertNotIn('Update process done', result.stdout)
        self.assertEqual(self.manifest(self.install), self.original, result.stdout)
        self.assertEqual(list(self.markers.glob('.was_updated*')), [])
        return result, commands

    def test_failed_download_preserves_installation_configuration_and_previous_backup(self):
        result, _ = self.assert_failed_intact('wget')
        self.assertIn('Download failed', result.stdout)

    def test_corrupt_archive_is_rejected(self):
        (self.root / 'replacement.zip').write_bytes(b'not a zip file')
        self.assert_failed_intact()

    def test_incomplete_archive_is_rejected(self):
        del self.members['modules.py']
        self.archive()
        self.assert_failed_intact()

    def test_path_traversal_is_rejected_before_extraction(self):
        self.archive({'Install-Manager-fixture/../../escaped': 'unsafe'})
        _, commands = self.assert_failed_intact()
        self.assertFalse(any(command[0] == 'unzip' for command in commands))
        self.assertFalse((self.root / 'escaped').exists())

    def test_invalid_python_is_rejected_without_running_it(self):
        self.members['update.py'] = 'def broken(\n'
        self.archive()
        self.assert_failed_intact()

    def test_archive_symlink_is_rejected_before_extraction(self):
        with zipfile.ZipFile(str(self.root / 'replacement.zip'), 'a') as archive:
            member = zipfile.ZipInfo('Install-Manager-fixture/link')
            member.create_system = 3
            member.external_attr = 0o120777 << 16
            archive.writestr(member, str(self.previous))
        _, commands = self.assert_failed_intact()
        self.assertFalse(any(command[0] == 'unzip' for command in commands))

    def test_invalid_shell_is_rejected_before_switch(self):
        self.members['rhim.sh'] = '#!/bin/bash\nif\n'
        self.archive()
        self.assert_failed_intact()

    def test_preparation_failures_preserve_installation(self):
        for command in ('unzip', 'chmod'):
            with self.subTest(command=command):
                self.assert_failed_intact(command)

    def test_required_config_copy_failure_aborts_before_switch(self):
        for failure in ('cp', 'cp-ap', 'cmp'):
            with self.subTest(failure=failure):
                self.assert_failed_intact(failure)

    def test_failed_activation_restores_old_installation(self):
        result, _ = self.assert_failed_intact('activate')
        self.assertIn('Cannot activate', result.stdout)

    def test_failed_restore_retains_recoverable_backup_and_reports_its_path(self):
        result, _ = self.run_update('activate-restore')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('Update process done', result.stdout)
        self.assertFalse(self.install.exists())
        backups = list(self.markers.glob('RH_Install-Manager-backup.*/RH_Install-Manager'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.manifest(backups[0]), self.original)
        self.assertIn('Restore the previous installation from ' + str(backups[0].parent), result.stdout)

    def test_success_retains_configs_and_scripts_are_executable(self):
        result, _ = self.run_update()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('RotorHazard Manager updated to version new-version', result.stdout)
        self.assertIn('Update process done', result.stdout)
        for name in ('updater-config.json', 'ap-config.json'):
            self.assertEqual((self.install / name).read_bytes(), self.original[name][0])
            self.assertEqual((self.install / name).stat().st_mode & 0o777, self.original[name][1])
        for name in ('rhim.sh', 'scripts/self_updater.sh', 'scripts/updater_from_rhim.sh'):
            self.assertTrue(os.access(str(self.install / name), os.X_OK))
            self.assertEqual((self.install / name).stat().st_mode & 0o022, 0)
        backups = list(self.markers.glob('RH_Install-Manager-backup.*/RH_Install-Manager'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.manifest(backups[0]), self.original)
        self.assertTrue((self.markers / '.was_updated_new').is_file())

    def test_relative_config_symlink_uses_activated_directory_for_version_read(self):
        config = self.install / 'updater-config.json'
        config.unlink()
        (self.home / 'local-config.json').write_text(json.dumps(
            dict(user='fixture-user', debug_mode=False, beta_tester=False)))
        config.symlink_to('../local-config.json')
        (self.install / 'distr-updater-config.json').write_text(json.dumps(
            dict(user='pi', debug_mode=False, beta_tester=False)))
        harness = '''import builtins, json, os, subprocess, sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, {tests!r})
from test_version_selection import load_function
load_json = load_function('modules.py', 'load_json', os=os, json=json, Namespace=SimpleNamespace)
load_config = load_function('modules.py', 'rhim_load_config', os=os, load_json=load_json)
def version_open(path, *args):
    assert Path(path) == Path('/home/fixture-user/RH_Install-Manager/version.txt'), path
    return builtins.open(str(Path(os.environ['HOME']) / 'RH_Install-Manager/version.txt'), *args)
get_version = load_function('modules.py', 'get_rhim_version', os=os,
    rhim_load_config=load_config, open=version_open)
operation = load_function('self_update.py', 'self_update', os=os, subprocess=subprocess,
    sleep=lambda seconds: None, internet_check=lambda: True, dots_show=lambda seconds: None,
    Bcolors=SimpleNamespace(RED='', GREEN='', ENDC=''), get_rhim_version=get_version)
sys.exit(0 if operation(load_config()) else 1)
'''
        (self.install / 'self_update.py').write_text(harness.format(tests=str(ROOT / 'tests')))
        self.original = self.manifest(self.install)
        result, _ = self.run_update()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('updated to version new-version', result.stdout)
        self.assertNotIn("can't read Install-Manager version", result.stdout)
        self.assertEqual(json.loads(config.read_text())['user'], 'fixture-user')
        self.assertTrue((self.markers / '.was_updated_new').is_file())
        self.assertFalse((self.markers / '.was_updated_old').exists())

    def test_branch_selection_is_passed_as_one_literal_argument(self):
        for branch, expected in ((True, 'dev'), ('feature/custom; echo unwanted', 'feature/custom; echo unwanted')):
            with self.subTest(branch=branch):
                self.write_harness(branch)
                self.original = self.manifest(self.install)
                _, commands = self.assert_failed_intact('wget')
                urls = [command[1] for command in commands if command[0] == 'wget']
                self.assertEqual(urls[-1], 'https://codeload.github.com/RotorHazard/Install-Manager/zip/' + expected)

    def test_missing_optional_configs_and_unchanged_version_can_succeed(self):
        for name in ('updater-config.json', 'ap-config.json'):
            (self.install / name).unlink()
        self.members['version.txt'] = 'old-version\n'
        self.archive()
        result, _ = self.run_update()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue((self.markers / '.was_updated_old').is_file())
        self.assertFalse((self.install / 'updater-config.json').exists())

    def test_existing_lock_is_preserved_and_refuses_direct_update(self):
        lock = self.markers / '.self-update-lock'
        lock.mkdir()
        result = subprocess.run(['bash', str(self.scripts / 'self_updater.sh'), 'stable'],
                                env=self.env, cwd=str(self.install), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, universal_newlines=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Another self-update may be running', result.stdout)
        self.assertEqual(self.manifest(self.install), self.original)
        self.assertTrue(lock.is_dir())

    def test_marker_write_failure_is_not_reported_as_success(self):
        (self.markers / '.was_updated_new').mkdir()
        result, _ = self.run_update()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('files were replaced', result.stdout)
        self.assertNotIn('RotorHazard Manager updated to version', result.stdout)
        self.assertNotIn('Update process done', result.stdout)

    def test_direct_shell_entry_propagates_failure(self):
        result, _ = self.run_update('wget', direct=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.manifest(self.install), self.original)


class SelfUpdateStatusTests(unittest.TestCase):
    def test_failed_entry_into_active_directory_does_not_report_success(self):
        version = Mock(return_value='old-version')
        marker = Mock()
        operation = load_function(
            'self_update.py', 'self_update', internet_check=lambda: True,
            sleep=Mock(), dots_show=Mock(), get_rhim_version=version,
            subprocess=SimpleNamespace(call=Mock(return_value=0)), open=marker,
            os=SimpleNamespace(chdir=Mock(side_effect=OSError('directory unavailable')),
                               path=SimpleNamespace(expanduser=lambda path: '/unused')),
            Bcolors=SimpleNamespace(RED='', GREEN='', ENDC=''))
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertFalse(operation(SimpleNamespace(beta_tester=False)))
        self.assertIn('directory could not be entered', output.getvalue())
        self.assertNotIn('updated to version', output.getvalue())
        version.assert_called_once_with(True)
        marker.assert_not_called()

    def test_network_repair_failure_is_returned(self):
        operation = load_function('self_update.py', 'self_update',
                                  internet_check=Mock(return_value=False), sleep=Mock(),
                                  subprocess=SimpleNamespace(call=Mock(return_value=1)),
                                  Bcolors=SimpleNamespace(RED='', ENDC=''))
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertFalse(operation(SimpleNamespace()))
        self.assertIn('Network repair failed', output.getvalue())

    def test_main_returns_process_failure_and_success(self):
        for success, status in ((False, 1), (True, 0)):
            main = load_function('self_update.py', 'main', rhim_load_config=Mock(),
                                 self_update=Mock(return_value=success))
            self.assertEqual(main(), status)

    def test_python36_syntax(self):
        ast.parse((ROOT / 'self_update.py').read_text(), feature_version=(3, 6))
