import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
# Literal, unmodified pi-gen fixtures, downloaded from these pinned upstream files:
# rc_local_bullseye: https://raw.githubusercontent.com/RPi-Distro/pi-gen/6ab22f38a23b3e48586fbf8fc79138bf1ccfb0ab/stage2/01-sys-tweaks/files/rc.local
# rc_local_buster: https://raw.githubusercontent.com/RPi-Distro/pi-gen/638c7521ee0c431fafca1e2bd4fd25705b37ea5b/stage2/01-sys-tweaks/files/rc.local
STOCK_FIXTURES = tuple(ROOT / 'tests/fixtures' / name
                       for name in ('rc_local_bullseye', 'rc_local_buster'))
SPEC = importlib.util.spec_from_file_location('rc_local', str(ROOT / 'rc_local.py'))
rc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rc)


class RcLocalTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root / 'rc.local'

    def put(self, text, mode=0o640):
        self.path.write_text(text)
        self.path.chmod(mode)

    def configure(self):
        return rc.configure(str(self.path))

    def backups(self):
        return list(self.root.glob('rc.local.rhim-backup-*'))

    def test_precheck_is_readonly_for_missing_supported_and_manual_layouts(self):
        missing = self.root / 'absent-directory/rc.local'
        rc.validate(str(missing))
        self.assertFalse(missing.parent.exists())
        for content in tuple(path.read_text() for path in STOCK_FIXTURES) + (
                        '#!/bin/sh\nexit 0\n', '#!/bin/sh\necho custom\nexit 0\n',
                        '#!/bin/sh\n' + rc.HEADERS[0] + '\n' + '\n'.join(rc.RULES) + '\niptables-save\nexit 0\n',
                        '#!/bin/sh\npython3 /home/pi/oled.py &\n' + rc.BLOCK + 'exit 0\n'):
            with self.subTest(content=content):
                self.put(content)
                before = rc.identity(self.path.stat())
                rc.validate(str(self.path))
                self.assertEqual(rc.identity(self.path.stat()), before)
                self.assertEqual(self.path.read_text(), content)
                self.assertEqual(list(self.root.iterdir()), [self.path])

    def test_configurator_revalidates_content_after_precheck(self):
        self.put('#!/bin/sh\nexit 0\n')
        rc.validate(str(self.path))
        self.put('#!/bin/sh\npython3 /home/pi/oled.py &\nexit 0\n')
        with self.assertRaises(rc.ConfigError):
            self.configure()
        self.assertEqual(self.backups(), [])

    def test_absent_creates_executable_posix_script_without_backup(self):
        self.assertTrue(self.configure())
        self.assertTrue(self.path.read_text().startswith('#!/bin/sh\n'))
        self.assertTrue(self.path.read_text().endswith('exit 0\n'))
        info = self.path.stat()
        self.assertEqual(stat.S_IMODE(info.st_mode), 0o755)
        self.assertEqual((info.st_uid, info.st_gid), (os.geteuid(), os.getegid()))
        self.assertEqual(self.backups(), [])
        self.assertFalse(Path(str(self.path) + '.iptables1_saved').exists())

    def test_stock_preserves_metadata_current_backup_and_repeat_identity(self):
        original = '#!/bin/sh -e\n# stock rc.local\n\nexit 0\n'
        self.put(original)
        before = self.path.stat()
        self.assertTrue(self.configure())
        self.assertNotEqual(self.path.stat().st_ino, before.st_ino)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o751)
        self.assertEqual((self.path.stat().st_uid, self.path.stat().st_gid), (before.st_uid, before.st_gid))
        self.assertEqual(self.backups()[0].read_text(), original)
        self.assertEqual(stat.S_IMODE(self.backups()[0].stat().st_mode), 0o640)
        self.assertEqual((self.backups()[0].stat().st_uid, self.backups()[0].stat().st_gid),
                         (before.st_uid, before.st_gid))
        self.assertEqual(Path(str(self.path) + '.iptables1_saved').read_text(), original)
        desired = self.path.read_bytes()
        identity = rc.identity(self.path.stat())
        self.assertFalse(self.configure())
        self.assertEqual(rc.identity(self.path.stat()), identity)
        self.assertEqual(self.path.read_bytes(), desired)
        self.assertEqual(len(self.backups()), 1)

    def test_permissions_only_update_does_not_rewrite_or_backup(self):
        self.put(rc.render('#!/bin/sh\nexit 0\n'), 0o640)
        before = self.path.stat()
        self.assertFalse(self.configure())
        self.assertEqual(self.path.stat().st_ino, before.st_ino)
        self.assertEqual(self.path.stat().st_mtime_ns, before.st_mtime_ns)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o751)
        self.assertEqual(self.backups(), [])

    def test_pinned_pi_os_stock_files_preserved_and_idempotent(self):
        for fixture in STOCK_FIXTURES:
            with self.subTest(fixture=fixture.name):
                original = fixture.read_bytes()
                self.path.write_bytes(original)
                self.path.chmod(0o755)
                count = len(self.backups())
                self.assertTrue(self.configure())
                configured = self.path.read_bytes()
                self.assertEqual(configured.replace(rc.BLOCK.encode('utf-8'), b''), original)
                self.assertEqual(configured.count(rc.BEGIN.encode('ascii')), 1)
                self.assertEqual(len(self.backups()), count + 1)
                self.assertTrue(any(backup.read_bytes() == original for backup in self.backups()))
                identity = rc.identity(self.path.stat())
                self.assertFalse(self.configure())
                self.assertEqual(self.path.read_bytes(), configured)
                self.assertEqual(rc.identity(self.path.stat()), identity)
                self.assertEqual(len(self.backups()), count + 1)

    def test_pi_os_stock_plus_simple_custom_command_preserved(self):
        for fixture in STOCK_FIXTURES:
            with self.subTest(fixture=fixture.name):
                original = fixture.read_text().replace('exit 0\n', 'echo custom startup\nexit 0\n')
                self.put(original)
                self.assertTrue(self.configure())
                self.assertEqual(self.path.read_text().replace(rc.BLOCK, ''), original)

    def test_altered_or_duplicate_stock_ip_fragment_refused(self):
        original = STOCK_FIXTURES[0].read_text()
        for altered in (original.replace(' || true', ' || false'),
                        original.replace('My IP address', 'Custom IP address'),
                        original.replace('# Print the IP address', '# Custom IP display'),
                        original.replace('exit 0\n', rc.STOCK_IP_FRAGMENT + 'exit 0\n')):
            with self.subTest(altered=altered):
                self.put(altered)
                with self.assertRaises(rc.ConfigError):
                    self.configure()
                self.assertEqual(self.path.read_text(), altered)
                self.assertEqual(self.backups(), [])

    def test_exact_manual_block_in_complex_script_is_unchanged(self):
        original = '#!/bin/sh -e\nif [ -f /tmp/custom ]; then\n  echo custom\nfi\n' + rc.BLOCK + 'exit 0\n'
        self.put(original, 0o755)
        identity = rc.identity(self.path.stat())
        for attempt in range(2):
            self.assertFalse(self.configure())
            self.assertEqual(self.path.read_bytes(), original.encode('utf-8'))
            self.assertEqual(rc.identity(self.path.stat()), identity)
            self.assertEqual(self.backups(), [])
            self.assertFalse(Path(str(self.path) + '.iptables1_saved').exists())

    def test_modified_manual_block_with_complex_script_is_refused(self):
        modified = rc.BLOCK.replace('rhim_status=$?', 'rhim_status=2')
        original = '#!/bin/sh\nif true; then\n  echo custom\nfi\n' + modified + 'exit 0\n'
        self.put(original, 0o755)
        with self.assertRaises(rc.ConfigError):
            self.configure()
        self.assertEqual(self.path.read_text(), original)
        self.assertEqual(self.backups(), [])

    def test_exact_manual_block_with_historical_entries_is_refused(self):
        for historical in rc.HEADERS + rc.RULES + tuple('sudo ' + rule for rule in rc.RULES):
            with self.subTest(historical=historical):
                original = '#!/bin/sh\n' + historical + '\n' + rc.BLOCK + 'exit 0\n'
                self.put(original)
                with self.assertRaisesRegex(rc.ConfigError, 'Mixed historical'):
                    self.configure()
                self.assertEqual(self.path.read_text(), original)
                self.assertEqual(self.backups(), [])

    def test_crlf_refused_with_or_without_exact_block(self):
        for original in (STOCK_FIXTURES[0].read_text(), '#!/bin/sh\n' + rc.BLOCK + 'exit 0\n'):
            data = original.replace('\n', '\r\n').encode('utf-8')
            self.path.write_bytes(data)
            with self.assertRaisesRegex(rc.ConfigError, 'CRLF'):
                self.configure()
            self.assertEqual(self.path.read_bytes(), data)
            self.assertEqual(self.backups(), [])

    def test_manual_guidance_contains_exact_block_and_reachability_limits(self):
        self.assertIn(rc.BLOCK, rc.MANUAL)
        self.assertIn('outside conditionals', rc.MANUAL)
        self.assertIn('Verify syntax with the interpreter', rc.MANUAL)
        self.assertIn('does not verify startup reachability or application health', rc.MANUAL)
        # Exact manual placement is trusted even when unreachable; this is not a boot check.
        original = '#!/bin/sh\nexit 0\n' + rc.BLOCK
        self.assertEqual(rc.render(original), original)

    def test_current_user_commands_preserved_despite_old_backup(self):
        first = Path(str(self.path) + '.iptables1_saved')
        first.write_text('historical first backup')
        original = '#!/bin/sh\n# my server\necho "custom startup"\n/usr/bin/touch /tmp/example\n\nexit 0\n# trailing comment\n'
        self.put(original)
        self.configure()
        self.assertEqual(self.path.read_text().replace(rc.BLOCK, ''), original)
        self.assertEqual(first.read_text(), 'historical first backup')
        self.assertEqual(self.backups()[0].read_text(), original)

    def test_each_changed_revision_gets_unique_current_backup(self):
        original = '#!/bin/sh\nexit 0\n'
        self.put(original)
        self.configure()
        changed = self.path.read_text().replace(rc.BEGIN + '\n', rc.BEGIN + '\n# old own block\n')
        self.put(changed)
        self.configure()
        self.assertEqual(len(self.backups()), 2)
        self.assertEqual(set(path.read_text() for path in self.backups()), {original, changed})
        self.assertEqual(Path(str(self.path) + '.iptables1_saved').read_text(), original)

    def test_historical_headers_sudo_and_duplicate_blocks(self):
        for header in rc.HEADERS:
            for sudo in ('', 'sudo '):
                with self.subTest(header=header, sudo=sudo):
                    legacy = header + '\n' + '\n'.join(sudo + rule for rule in rc.RULES) + '\n' + sudo + 'iptables-save\n'
                    original = '#!/bin/bash\n# user\necho preserved\n' + legacy * 2 + '\nexit 0\n'
                    result = rc.render(original)
                    self.assertEqual(result.count(rc.BEGIN), 1)
                    self.assertNotIn('iptables-save', result)
                    self.assertIn('echo preserved\n', result)
                    self.assertEqual(rc.render(result), result)
        pairs = '\n'.join(rc.RULES) + '\n'
        result = rc.render('#!/bin/sh\n' + pairs * 2 + 'iptables-save\nexit 0\n')
        self.assertIn('\niptables-save\n', result)
        result = rc.render('#!/bin/sh\niptables-save\n' + legacy + 'sudo iptables-save\nexit 0\n')
        self.assertIn('\niptables-save\n', result)
        self.assertIn('\nsudo iptables-save\n', result)

    def test_managed_block_replaced_in_place_preserving_following_commands(self):
        original = '#!/bin/sh\n' + rc.BEGIN + '\n# obsolete own content\n' + rc.END + '\necho after\nexit 0\n'
        self.put(original)
        self.configure()
        self.assertEqual(self.path.read_text(), '#!/bin/sh\n' + rc.BLOCK + 'echo after\nexit 0\n')
        self.assertEqual(self.backups()[0].read_text(), original)

    def test_malformed_markers_and_complex_layout_refused_without_files(self):
        cases = [rc.BEGIN + '\n', rc.END + '\n' + rc.BEGIN + '\n', rc.BLOCK * 2,
                 '# BEGIN RHIM other\n', 'if true; then\necho x\nfi\n',
                 'echo a; exit 0\n', 'exec /bin/true\n', 'exit 1\n',
                 "cat <<EOF\ntext\nEOF\n", 'echo x > /tmp/file\n',
                 'f() {\necho x\n}\n', 'eval true\n', '. /tmp/file\n',
                 '[[ x ==\nx ]]\n',
                 rc.HEADERS[0] + '\n' + rc.RULES[0] + '\n']
        for body in cases:
            with self.subTest(body=body):
                original = '#!/bin/sh\n' + body + 'exit 0\n'
                self.put(original)
                with self.assertRaisesRegex(rc.ConfigError, 'manually.*port 5000'):
                    self.configure()
                self.assertEqual(self.path.read_text(), original)
                self.assertEqual(self.backups(), [])
                self.assertFalse(Path(str(self.path) + '.iptables1_saved').exists())
        with self.assertRaises(rc.ConfigError):
            rc.render('#!/bin/sh\nexit 0\n' + rc.BLOCK.replace('rhim_status=$?', 'rhim_status=2'))
        with self.assertRaises(rc.ConfigError):
            rc.render('#!/bin/sh\necho x\n')

    def test_symlink_fifo_directory_and_hardlink_refused(self):
        target = self.root / 'target'
        target.write_text('#!/bin/sh\nexit 0\n')
        self.path.symlink_to(target)
        with self.assertRaises(rc.ConfigError):
            self.configure()
        self.path.unlink()
        os.mkfifo(str(self.path))
        with self.assertRaises(rc.ConfigError):
            self.configure()
        self.path.unlink()
        self.path.mkdir()
        with self.assertRaises(rc.ConfigError):
            self.configure()
        self.path.rmdir()
        os.link(str(target), str(self.path))
        with self.assertRaises(rc.ConfigError):
            self.configure()
        self.assertEqual(target.read_text(), '#!/bin/sh\nexit 0\n')

    def test_write_and_replace_failure_leave_original_and_clean_temporary(self):
        original = '#!/bin/sh\nexit 0\n'
        for operation in ('write_file', 'replace'):
            with self.subTest(operation=operation):
                self.put(original)
                target = rc if operation == 'write_file' else rc.os
                with patch.object(target, operation, side_effect=OSError('injected write failure')):
                    with self.assertRaisesRegex(OSError, 'injected write failure'):
                        self.configure()
                self.assertEqual(self.path.read_text(), original)
                self.assertEqual(list(self.root.glob('.rhim-rc-local-*')), [])
        self.assertEqual(self.backups()[0].read_text(), original)

    def test_backup_failure_is_fatal_and_partial_first_backup_removed(self):
        original = '#!/bin/sh\nexit 0\n'
        self.put(original)
        write = rc.write_file
        count = [0]

        def fail_backup(fd, *args):
            count[0] += 1
            if count[0] == 2:
                os.close(fd)
                raise OSError('injected backup failure')
            return write(fd, *args)

        with patch.object(rc, 'write_file', side_effect=fail_backup):
            with self.assertRaisesRegex(OSError, 'backup failure'):
                self.configure()
        self.assertEqual(self.path.read_text(), original)
        self.assertFalse(Path(str(self.path) + '.iptables1_saved').exists())

    def test_latest_backup_failure_is_fatal_and_keeps_first_backup(self):
        original = '#!/bin/sh\nexit 0\n'
        self.put(original)
        first = Path(str(self.path) + '.iptables1_saved')
        first.write_text('old backup')
        mkstemp = rc.tempfile.mkstemp
        count = [0]

        def fail_backup(*args, **kwargs):
            count[0] += 1
            if count[0] == 2:
                raise OSError('latest backup unavailable')
            return mkstemp(*args, **kwargs)

        with patch.object(rc.tempfile, 'mkstemp', side_effect=fail_backup):
            with self.assertRaisesRegex(OSError, 'latest backup unavailable'):
                self.configure()
        self.assertEqual(self.path.read_text(), original)
        self.assertEqual(first.read_text(), 'old backup')
        self.assertEqual(list(self.root.glob('.rhim-rc-local-*')), [])
        write = rc.write_file
        count[0] = 0

        def fail_backup_write(*args):
            count[0] += 1
            write(*args)
            if count[0] == 2:
                raise OSError('backup write failed')

        with patch.object(rc, 'write_file', side_effect=fail_backup_write):
            with self.assertRaisesRegex(OSError, 'backup write failed'):
                self.configure()
        self.assertEqual(self.backups(), [])
        self.assertEqual(self.path.read_text(), original)
        self.assertEqual(first.read_text(), 'old backup')

    def test_concurrent_content_or_identity_change_not_overwritten(self):
        for replace in (False, True):
            with self.subTest(replace=replace):
                self.put('#!/bin/sh\nexit 0\n')
                write = rc.write_file
                updated = '#!/bin/sh\necho concurrent\nexit 0\n'

                def edit_during_write(*args):
                    write(*args)
                    if replace:
                        self.path.unlink()
                    self.path.write_text(updated)

                with patch.object(rc, 'write_file', side_effect=edit_during_write):
                    with self.assertRaisesRegex(rc.ConfigError, 'concurrently'):
                        self.configure()
                self.assertEqual(self.path.read_text(), updated)
                self.assertEqual(self.backups(), [])

    def test_final_verification_detects_edit_during_backup(self):
        self.put('#!/bin/sh\nexit 0\n')
        write = rc.write_file
        count = [0]
        updated = '#!/bin/sh\necho latest user edit\nexit 0\n'

        def edit_during_backup(*args):
            write(*args)
            count[0] += 1
            if count[0] == 3:
                self.path.write_text(updated)

        with patch.object(rc, 'write_file', side_effect=edit_during_backup):
            with self.assertRaisesRegex(rc.ConfigError, 'concurrently'):
                self.configure()
        self.assertEqual(self.path.read_text(), updated)

    def stub(self, name, content):
        path = self.root / name
        path.write_text(content)
        path.chmod(0o755)
        return path

    def environment(self, **extra):
        return dict(os.environ, PATH=str(self.root) + os.pathsep + os.environ['PATH'],
                    CALLS=str(self.root / 'calls'), FIXTURE=str(self.path), **extra)

    def firewall_stub(self):
        self.stub('iptables', '''#!/bin/sh
printf '%s\n' "$*" >> "$CALLS"
if [ "$1" = -C ]; then exit "${QUERY_STATUS:-1}"; fi
exit "${ADD_STATUS:-0}"
''')

    def test_actual_shell_entry_refuses_before_iptables_and_propagates_errors(self):
        self.stub('sudo', '#!/bin/sh\nexec "$@"\n')
        self.stub('python3', '#!' + sys.executable + '''
import os, runpy, sys
helper = runpy.run_path(sys.argv[-1])
try:
    helper['configure'](os.environ['FIXTURE'])
except Exception as error:
    print(str(error), file=sys.stderr)
    sys.exit(1)
''')
        self.stub('hostname', '#!/bin/sh\necho 127.0.0.1\n')
        self.firewall_stub()
        script = str(ROOT / 'scripts/iptables_conf.sh')
        self.put('#!/bin/sh\nif true; then\necho custom\nfi\nexit 0\n')
        result = subprocess.run(['bash', script], env=self.environment(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'port 5000', result.stderr)
        self.assertFalse((self.root / 'calls').exists())
        self.put('#!/bin/sh\nexit 0\n')
        result = subprocess.run(['bash', script], env=self.environment(QUERY_STATUS='2'), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(' -A ', ' ' + (self.root / 'calls').read_text())
        self.assertIn(b'Checking port 80', result.stderr)

    def test_persistent_shell_isolates_state_and_propagates_firewall_failures(self):
        self.firewall_stub()
        for shell in ('#!/bin/sh', '#!/bin/sh -e'):
            text = shell + '\n' + rc.BLOCK + 'env\n/usr/bin/printf "args:%s,%s\\n" "$1" "$2"\nexit 0\n'
            # The fixture after the managed block is deliberately richer than the accepted edit layout.
            self.put(text, 0o755)
            environment = self.environment(rhim_ports='original ports', rhim_status='original status')
            result = subprocess.run([str(self.path), 'first', 'second'], env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(b'args:first,second', result.stdout)
            self.assertIn(b'rhim_ports=original ports', result.stdout)
            self.assertIn(b'rhim_status=original status', result.stdout)
            (self.root / 'calls').write_text('')
            result = subprocess.run([str(self.path)], env=dict(environment, QUERY_STATUS='0'), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(all(line.startswith('-C ') for line in (self.root / 'calls').read_text().splitlines()))
            for failure in ({'QUERY_STATUS': '2'}, {'ADD_STATUS': '3'}):
                (self.root / 'calls').write_text('')
                result = subprocess.run([str(self.path)], env=dict(environment, **failure), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, b'')
                if 'QUERY_STATUS' in failure:
                    self.assertEqual(len((self.root / 'calls').read_text().splitlines()), 1)


if __name__ == '__main__':
    unittest.main()
