"""Actual Python functions with external effects replaced, never run installers."""
import ast
import contextlib
import io
import json
import os
import signal
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from test_version_selection import ROOT, load_function


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'rhim_config.json'
        self.original = '{"first_part_of_install": true}\n'
        self.path.write_text(self.original)
        self.output = io.StringIO()
        self.replace = Mock(side_effect=lambda source, target: os.replace(source, self.path))
        self.fsync = Mock(wraps=os.fsync)
        self.dump = Mock(wraps=json.dump)
        self.writer = load_function(
            'modules.py', 'write_rhim_sys_markers', tempfile=tempfile,
            json=SimpleNamespace(dump=self.dump),
            os=SimpleNamespace(path=SimpleNamespace(dirname=lambda path: self.directory.name,
                                                    exists=os.path.exists),
                               fsync=self.fsync, replace=self.replace, unlink=os.unlink))

    def write(self, value):
        with contextlib.redirect_stdout(self.output):
            return self.writer(value, 'pi')

    def assert_original_preserved(self):
        self.assertEqual(self.path.read_text(), self.original)
        self.assertEqual(list(Path(self.directory.name).iterdir()), [self.path])
        self.assertIn('Could not save installation progress', self.output.getvalue())

    def test_success_replaces_complete_json(self):
        self.assertTrue(self.write(SimpleNamespace(first_part_of_install=True, fresh_install_pending=True)))
        self.assertEqual(json.loads(self.path.read_text()),
                         dict(first_part_of_install=True, fresh_install_pending=True))
        self.replace.assert_called_once()
        self.assertEqual(self.replace.call_args.args[1], '/home/pi/.rhim_markers/rhim_config.json')
        self.fsync.assert_called_once()

    def test_partial_serialization_keeps_previous_valid_progress(self):
        self.assertFalse(self.write(SimpleNamespace(first_part_of_install=False, invalid=object())))
        self.assert_original_preserved()
        self.replace.assert_not_called()

    def test_disk_full_keeps_previous_valid_progress(self):
        self.fsync.side_effect = OSError('disk full')
        self.assertFalse(self.write(SimpleNamespace(first_part_of_install=False)))
        self.assert_original_preserved()
        self.assertIn('disk full', self.output.getvalue())
        self.replace.assert_not_called()

    def test_failed_replace_keeps_previous_valid_progress_and_can_retry(self):
        self.replace.side_effect = PermissionError('read-only storage')
        value = SimpleNamespace(first_part_of_install=False)
        self.assertFalse(self.write(value))
        self.assert_original_preserved()
        self.replace.side_effect = lambda source, target: os.replace(source, self.path)
        self.assertTrue(self.write(value))
        self.assertEqual(json.loads(self.path.read_text()), dict(first_part_of_install=False))

    def test_missing_storage_is_diagnosed_without_touching_previous_file(self):
        self.writer.__globals__['tempfile'] = SimpleNamespace(
            NamedTemporaryFile=Mock(side_effect=FileNotFoundError('progress directory missing')))
        self.assertFalse(self.write(SimpleNamespace(first_part_of_install=False)))
        self.assert_original_preserved()


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.config = SimpleNamespace(user='pi')
        self.system = Mock(return_value=0)
        self.apply_config = Mock()
        self.cleanup = Mock(return_value=True)
        self.start = Mock(return_value=True)
        self.colors = SimpleNamespace(GREEN='', ENDC='', UNDERLINE='', YELLOW='')
        self.output = io.StringIO()
        self.redirect = contextlib.redirect_stdout(self.output)
        self.redirect.__enter__()
        self.addCleanup(self.redirect.__exit__, None, None, None)

    def menu(self, name, replies):
        read = Mock(side_effect=replies)
        completion_input = load_function('rpi_update.py', 'completion_input', input=read)
        return load_function(
            'rpi_update.py', name, completion_input=completion_input, Bcolors=self.colors,
            os=SimpleNamespace(system=self.system, chdir=Mock()), sleep=Mock(),
            show_runtime_error=Mock(), server_start=self.start,
            apply_config_file=self.apply_config, cleanup_old=self.cleanup,
            glob=SimpleNamespace(glob=lambda pattern: []), show_update_completed=lambda: 'Update completed',
            clear_the_screen=Mock(), conf_rh=Mock(return_value=True),
            check_rotorhazard_config_status=lambda config: ('', True))

    def test_completion_menus_accept_eof(self):
        for name in ('end_of_part_1', 'end_normal_installation', 'end_quick_installation', 'end_update'):
            with self.subTest(name=name):
                menu = self.menu(name, EOFError())
                if name == 'end_update':
                    self.assertTrue(menu(self.config, False, True))
                elif name == 'end_quick_installation':
                    self.assertTrue(menu(self.config))
                else:
                    self.assertIsNot(menu(), False)

    def test_unconfigured_server_cannot_be_reported_as_running(self):
        menu = self.menu('end_update', ['s', 'e'])
        self.assertTrue(menu(self.config, False, True))
        self.start.assert_not_called()
        self.assertIn('Configuration is pending', self.output.getvalue())

    def test_start_failure_returns_failure_to_coordinator(self):
        menu = self.menu('end_update', ['s'])
        self.start.return_value = False
        self.assertFalse(menu(self.config, True, True))

    def test_incomplete_wizard_at_eof_reports_pending(self):
        menu = self.menu('end_normal_installation', ['c'])
        menu.__globals__['conf_rh'].side_effect = EOFError()
        self.assertTrue(menu())
        self.assertIn('Configuration is pending', self.output.getvalue())

    def test_configuration_failure_returns_failure(self):
        for name in ('end_normal_installation', 'end_update'):
            menu = self.menu(name, ['c'])
            menu.__globals__['conf_rh'].return_value = False
            self.assertFalse(menu(self.config, False, True) if name == 'end_update' else menu())

    def test_quick_configuration_copy_failure_stops_before_next_effect(self):
        menu = self.menu('end_quick_installation', [])
        self.apply_config.side_effect = OSError('write denied')
        self.assertFalse(menu(self.config))
        self.system.assert_not_called()
        self.assertNotIn('Default NuclearHazard configuration applied', self.output.getvalue())

    def test_quick_wifi_failure_is_propagated(self):
        menu = self.menu('end_quick_installation', ['y'])
        self.system.side_effect = [0, 1]
        self.assertFalse(menu(self.config))

    def test_failed_reboot_or_cleanup_is_not_reported_as_success(self):
        for selection in ('r', 'o'):
            menu = self.menu('end_update', [selection])
            self.system.return_value = 1
            self.cleanup.side_effect = ValueError("pending recovery")
            self.assertFalse(menu(self.config, True, True))
        self.assertNotIn('installations cleaned', self.output.getvalue())


class ResumeMenuTests(unittest.TestCase):
    def test_completed_host_configuration_still_resumes_pending_part2(self):
        config = SimpleNamespace(user='pi', debug_mode=False, rh_version='stable')
        markers = SimpleNamespace(sys_config_done=True, first_part_of_install=True, second_part_of_install=False)
        install = Mock()
        menu = load_function(
            'rpi_update.py', 'main_window',
            Bcolors=SimpleNamespace(**dict.fromkeys(
                ('RED', 'GREEN', 'ENDC', 'YELLOW', 'UNDERLINE', 'BOLD', 'GREEN_S', 'BLUE', 'ORANGE'), '')),
            input=Mock(side_effect=['i', 'e']), sleep=Mock(), clear_the_screen=Mock(),
            os=SimpleNamespace(chdir=Mock()), installation=install,
            check_rotorhazard_config_status=lambda config: ('', False),
            get_rotorhazard_server_version=lambda config: (False, '0', False),
            rh_update_check=lambda config: False, rhim_config_check=lambda: True,
            check_preferred_rh_version=lambda config: ('v4.5.0', '450', 'v4.5.0'),
            load_rhim_sys_markers=lambda user: markers)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            menu(config)
        install.assert_called_once_with(True, config, '')
        self.assertNotIn('Force installation', output.getvalue())

    def test_uart_menu_does_not_record_failed_configuration_or_claim_success(self):
        config = SimpleNamespace(user='pi', debug_mode=False)
        status = SimpleNamespace(uart_support_added=False)
        save = Mock(return_value=True)
        menu = load_function(
            'update.py', 'serial_menu',
            load_rhim_sys_markers=lambda user: status, write_rhim_sys_markers=save,
            os=SimpleNamespace(system=Mock(return_value=1)),
            clear_the_screen=Mock(), logo_top=Mock(), sleep=Mock(),
            input=Mock(side_effect=['y']),
            Bcolors=SimpleNamespace(YELLOW_S='', GREEN_S='', ENDC=''))
        with contextlib.redirect_stdout(io.StringIO()) as output:
            menu(config)
        save.assert_not_called()
        self.assertFalse(status.uart_support_added)
        self.assertNotIn('enabled successfully', output.getvalue())


class ServerStartTests(unittest.TestCase):
    def start(self, statuses, reply='y'):
        self.system = Mock(side_effect=statuses)
        self.output = io.StringIO()
        start = load_function('modules.py', 'server_start',
                              os=SimpleNamespace(system=self.system, WIFEXITED=os.WIFEXITED,
                                                 WEXITSTATUS=os.WEXITSTATUS,
                                                 WIFSIGNALED=os.WIFSIGNALED, WTERMSIG=os.WTERMSIG),
                              signal=signal,
                              clear_the_screen=Mock(), input=Mock(return_value=reply))
        with contextlib.redirect_stdout(self.output):
            return start()

    def test_foreground_failure_is_returned(self):
        self.assertFalse(self.start([3, 256]))
        self.assertIn('did not exit successfully', self.output.getvalue())

    def test_stop_failure_does_not_start_second_server(self):
        self.assertFalse(self.start([0, 256]))
        self.assertEqual(self.system.call_count, 2)

    def test_clean_exit_is_success(self):
        self.assertTrue(self.start([3, 0]))

    def test_ctrl_c_does_not_report_operation_failure(self):
        for status in (130 << 8, signal.SIGINT):
            with self.subTest(status=status):
                self.assertTrue(self.start([3, status]))
                self.assertNotIn('did not exit successfully', self.output.getvalue())

    def test_other_signal_is_a_failure(self):
        self.assertFalse(self.start([3, signal.SIGTERM]))

    def test_running_service_can_be_kept(self):
        self.assertTrue(self.start([0], reply='n'))
        self.system.assert_called_once()


class WizardTests(unittest.TestCase):
    def test_wizard_status_stops_retry_loop_on_operation_failure(self):
        configure = Mock(return_value=-1)
        wizard = load_function('conf_wizard_rh.py', 'conf_rh', do_config=configure)
        self.assertFalse(wizard())
        configure.assert_called_once()

    def test_wizard_keeps_existing_change_and_exit_flow(self):
        wizard = load_function('conf_wizard_rh.py', 'conf_rh', do_config=Mock(side_effect=[1, 0]))
        self.assertTrue(wizard())

    def test_changed_production_python_parses_as_python36(self):
        for filename in ('modules.py', 'update.py', 'conf_wizard_rh.py'):
            ast.parse((ROOT / filename).read_text(), filename=filename, feature_version=(3, 6))
