"""No real systemctl, Python runtime, installer or /home files are accessed."""
import ast
import contextlib
import io
import json
from pathlib import Path
import shlex
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from test_version_selection import ROOT, load_function

sys.path.insert(0, str(ROOT))
import runtime_preflight as preflight


USER = "pi"
HOME = "/home/pi"
PYTHON = HOME + "/.venv/bin/python3"
WD = HOME + "/RotorHazard/src/server"
# Literal example of the effective systemctl show representation, including runtime metadata.
EXEC = ("{ path=/home/pi/.venv/bin/python3 ; argv[]=/home/pi/.venv/bin/python3 server.py ; "
        "ignore_errors=no ; start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }")


class RuntimeFixture(unittest.TestCase):
    def setUp(self):
        # Synthetic literal fixture, independent of the implementation's property list.
        fixture = (ROOT / "tests/fixtures/systemctl_show_standard.txt").read_text()
        self.properties = dict(line.split("=", 1) for line in fixture.splitlines())
        self.existing = True
        self.venv = True
        self.version = [3, 11, 2]
        self.prefix = HOME + "/.venv"
        self.base_prefix = "/usr"
        self.executable = PYTHON
        self.probe_error = ""
        self.system_error = False
        self.manager_environment = "LANG=C\n"
        self.marker_data = {}
        self.marker_error = None
        self.marker_text = None
        self.commands = []
        self.account = SimpleNamespace(pw_name=USER, pw_gid=1000)
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(preflight.pwd, "getpwuid", return_value=self.account))
        self.stack.enter_context(patch.object(preflight.grp, "getgrgid", return_value=SimpleNamespace(gr_name=USER)))
        self.stack.enter_context(patch.object(preflight.os.path, "lexists", side_effect=self.lexists))
        self.realpath = self.stack.enter_context(patch.object(preflight.os.path, "realpath", side_effect=lambda path: path))
        self.stack.enter_context(patch.object(preflight, "open", side_effect=self.open_markers, create=True))
        self.runner = self.stack.enter_context(patch.object(preflight.subprocess, "run", side_effect=self.command))
        self.output = self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.stack.enter_context(contextlib.redirect_stderr(io.StringIO()))

    def lexists(self, path):
        return self.venv if path == HOME + "/.venv" else self.existing

    def open_markers(self, path, mode):
        self.assertEqual(path, HOME + "/.rhim_markers/rhim_config.json")
        self.assertEqual(mode, "r")
        if self.marker_error is not None:
            raise self.marker_error
        return io.StringIO(json.dumps(self.marker_data) if self.marker_text is None else self.marker_text)

    def command(self, argv, **kwargs):
        self.commands.append(argv)
        self.assertEqual(kwargs["cwd"], "/")
        self.assertEqual(kwargs["timeout"], 15)
        self.assertNotIn("shell", kwargs)
        if argv[0] == "systemctl":
            if self.system_error:
                return subprocess.CompletedProcess(argv, 1, "", "No bus")
            if argv[1] == "show-environment":
                return subprocess.CompletedProcess(argv, 0, self.manager_environment, "")
            self.assertIn("--all", argv)
            self.assertTrue(any(arg.startswith("--property=LoadState,") for arg in argv))
            output = "\n".join(key + "=" + value for key, value in self.properties.items())
            code = 4 if self.properties["LoadState"] == "not-found" else 0
            return subprocess.CompletedProcess(argv, code, output, "")
        self.assertEqual(argv[1:4], ["-I", "-B", "-c"])
        output = json.dumps(dict(version=self.version, prefix=self.prefix,
                                 base_prefix=self.base_prefix, executable=self.executable))
        return subprocess.CompletedProcess(argv, int(bool(self.probe_error)), output, self.probe_error)

    def check(self, target="v4.5.0", stage="update", confirm=None):
        return preflight.check_runtime(USER, target, stage, confirm=confirm)

    def fresh(self):
        self.properties["LoadState"] = "not-found"
        self.existing = False


class RuntimeTests(RuntimeFixture):
    def test_captured_systemd252_running_service(self):
        # Debian 12 systemd 252.39, real running dummy service; no property rewriting.
        fixture = (ROOT / "tests/fixtures/systemctl_show_systemd252_running.txt").read_text()
        self.properties = dict(line.split("=", 1) for line in fixture.splitlines())
        self.assertEqual(self.check()["python"], PYTHON)

    def test_standard_service_preserves_venv_executable(self):
        result = self.check()
        self.assertEqual(result["python"], PYTHON)
        self.assertEqual(result["base_python"], PYTHON)
        self.assertFalse(result["create_venv"])
        self.assertIn("import pip", self.commands[-1][-1])

    def test_same_effective_drop_in_and_absolute_server(self):
        # Drop-in origin is immaterial: only loaded effective values are inspected.
        self.properties["ExecStart"] = EXEC.replace(" server.py ;", " " + WD + "/server.py ;")
        self.properties["Group"] = USER
        self.assertEqual(self.check()["python"], PYTHON)

    def test_known_release_and_beta_require_310(self):
        for target in ("v4.4.0", "v4.5.0", "v4.5.0-beta.1", "4.4.1", "v4.4.0-rc.1"):
            for version in ([3, 9, 9], [3, 10, 0], [3, 13, 1]):
                with self.subTest(target=target, version=version):
                    self.version = version
                    consent = Mock(side_effect=AssertionError("Known target must not prompt"))
                    if version[:2] < [3, 10]:
                        with self.assertRaisesRegex(ValueError, "requires Python 3.10"):
                            self.check(target, confirm=consent)
                    else:
                        self.check(target, confirm=consent)
                    consent.assert_not_called()

    def test_absent_venv_is_not_recreated_existing_or_part2(self):
        self.venv = False
        for stage in ("part1", "part2", "update"):
            with self.subTest(stage=stage), self.assertRaisesRegex(ValueError, "venv is missing"):
                self.check(stage=stage)
        self.fresh()
        with self.assertRaisesRegex(ValueError, "venv is missing"):
            self.check(stage="part2")

    def test_loaded_leftover_service_without_source_or_venv_refuses_before_probe(self):
        self.existing = False
        self.venv = False
        for stage in ("part1", "part2", "update"):
            with self.subTest(stage=stage):
                self.commands.clear()
                with self.assertRaisesRegex(ValueError, "leftover rotorhazard.service is still loaded") as error:
                    self.check(stage=stage)
                self.assertIn("Review the service and runtime manually", str(error.exception))
                self.assertIn("verify whether the unit is still in use", str(error.exception))
                self.assertIn("will not be recreated", str(error.exception))
                self.assertTrue(all(command[0] == "systemctl" and command[1] in ("show", "show-environment")
                                    for command in self.commands))

    def test_existing_source_without_venv_keeps_generic_diagnosis(self):
        self.venv = False
        with self.assertRaisesRegex(ValueError, "RotorHazard venv is missing") as error:
            self.check(stage="part1")
        self.assertNotIn("leftover", str(error.exception))
        self.assertTrue(all(command[0] == "systemctl" for command in self.commands))

    def test_fresh_part1_validates_base_without_pip(self):
        self.fresh()
        self.venv = False
        self.prefix = self.base_prefix
        self.executable = "/usr/bin/python3"
        result = self.check(stage="part1")
        self.assertTrue(result["create_venv"])
        self.assertEqual(result["base_python"], "/usr/bin/python3")
        self.assertIn("import venv", self.commands[-1][-1])
        self.assertNotIn("import pip", self.commands[-1][-1])
        self.version = [3, 9, 2]
        with self.assertRaisesRegex(ValueError, "requires Python 3.10"):
            self.check(stage="part1")

    def test_resumed_fresh_part2_requires_existing_working_venv(self):
        self.fresh()
        self.assertEqual(self.check(stage="part2")["python"], PYTHON)
        self.probe_error = "No module named pip"
        with self.assertRaisesRegex(ValueError, "pip"):
            self.check(stage="part2")

    def test_broken_venv_or_missing_pip(self):
        for error in ("No module named pip", "broken interpreter"):
            self.probe_error = error
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                self.check()

    def test_venv_identity_mismatch(self):
        for field, value in (("prefix", "/usr"), ("base_prefix", HOME + "/.venv"),
                             ("executable", "/usr/bin/python3")):
            old = getattr(self, field)
            setattr(self, field, value)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "identity"):
                self.check()
            setattr(self, field, old)

    def test_wrong_current_user(self):
        self.account.pw_name = "other"
        with self.assertRaisesRegex(ValueError, "current account"):
            self.check()
        self.runner.assert_not_called()

    def test_unknown_account_has_an_actionable_error(self):
        with patch.object(preflight.pwd, "getpwuid", side_effect=KeyError("uid")):
            with self.assertRaisesRegex(ValueError, "current account or group"):
                self.check()
        self.runner.assert_not_called()

    def test_venv_inside_source_tree_is_refused(self):
        self.realpath.side_effect = lambda path: WD + "/venv" if path == HOME + "/.venv" else path
        with self.assertRaisesRegex(ValueError, "inside the RotorHazard source"):
            self.check()

    def test_effective_service_mismatches(self):
        for key, value in (("User", "root"), ("Group", "root"),
                           ("WorkingDirectory", "/srv/rh"), ("NeedDaemonReload", "yes"),
                           ("LoadState", "masked")):
            old = self.properties[key]
            self.properties[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check()
            self.properties[key] = old

    def test_reject_system_python_wrapper_and_extra_arguments(self):
        for command in (EXEC.replace(PYTHON, "/usr/bin/python3"),
                        EXEC.replace(PYTHON, "/home/pi/start.sh"),
                        EXEC.replace("server.py ;", "server.py --data /srv/data ;"),
                        EXEC.replace("ignore_errors=no", "ignore_errors=yes"), EXEC + " " + EXEC):
            self.properties["ExecStart"] = command
            with self.subTest(command=command), self.assertRaisesRegex(ValueError, "ExecStart"):
                self.check()

    def test_environment_and_sandbox_overrides(self):
        for key, value in (("Environment", "PYTHONHOME=/other"),
                           ("EnvironmentFiles", "/etc/rh.env (ignore_errors=no)"),
                           ("RootDirectory", "/srv/root"), ("BindPaths", "/srv:/home"),
                           ("ProtectHome", "yes"), ("ExecStartPre", "/bin/sh")):
            old = self.properties[key]
            self.properties[key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "environment or sandbox"):
                self.check()
            self.properties[key] = old

    def test_manager_python_environment(self):
        self.manager_environment = "PYTHONPATH=/other"
        with self.assertRaisesRegex(ValueError, "manager environment"):
            self.check()
        self.fresh()
        with self.assertRaisesRegex(ValueError, "manager environment"):
            self.check(stage="part1")

    def test_missing_service_existing_refused(self):
        self.properties["LoadState"] = "not-found"
        for stage in ("part1", "part2", "update"):
            with self.subTest(stage=stage), self.assertRaisesRegex(ValueError, "service is missing"):
                self.check(stage=stage)
        self.existing = False
        with self.assertRaisesRegex(ValueError, "service is missing"):
            self.check(stage="update")

    def test_partial_fresh_install_can_resume_without_guessing_existing_runtime(self):
        self.properties["LoadState"] = "not-found"
        self.marker_data = {"fresh_install_pending": True}
        for stage in ("part1", "part2"):
            with self.subTest(stage=stage):
                result = self.check(stage=stage)
                self.assertTrue(result["fresh_install"])
                self.assertFalse(result["create_venv"])
                self.assertEqual(result["python"], PYTHON)
        with self.assertRaisesRegex(ValueError, "service is missing"):
            self.check(stage="update")
        self.venv = False
        with self.assertRaisesRegex(ValueError, "venv is missing"):
            self.check(stage="part1")

    def test_old_or_invalid_markers_cannot_authorize_missing_service(self):
        self.properties["LoadState"] = "not-found"
        for markers in ({}, {"first_part_of_install": True}, {"fresh_install_pending": False},
                        {"fresh_install_pending": "true"}):
            self.marker_data = markers
            with self.subTest(markers=markers), self.assertRaisesRegex(ValueError, "service is missing"):
                self.check(stage="part2")
        self.marker_error = FileNotFoundError()
        with self.assertRaisesRegex(ValueError, "service is missing"):
            self.check(stage="part2")
        self.marker_error = PermissionError()
        with self.assertRaisesRegex(ValueError, "Cannot read installation progress"):
            self.check(stage="part2")
        self.marker_error = None
        self.marker_text = "{broken json"
        with self.assertRaisesRegex(ValueError, "Cannot read installation progress"):
            self.check(stage="part2")

    def test_systemctl_error_even_on_fresh(self):
        self.fresh()
        self.system_error = True
        with self.assertRaisesRegex(ValueError, "systemd access"):
            self.check(stage="part1")

    def test_incomplete_systemctl_properties(self):
        del self.properties["ExecStart"]
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            self.check()

    def test_optional_properties_may_be_absent_on_older_systemd(self):
        for key in ("NoExecPaths", "ExecPaths", "ExecCondition", "Group", "PrivateMounts"):
            del self.properties[key]
        self.assertEqual(self.check()["python"], PYTHON)

    def test_empty_deny_lists_are_not_treated_as_restrictions(self):
        self.assertEqual(self.properties["SystemCallFilter"], "~")
        self.assertEqual(self.properties["RestrictAddressFamilies"], "~")
        self.check()
        for key, value in (("SystemCallFilter", "~mount"), ("SystemCallFilter", "read write"),
                           ("RestrictAddressFamilies", "AF_UNIX"), ("RestrictAddressFamilies", "")):
            old = self.properties[key]
            self.properties[key] = value
            with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, "environment or sandbox"):
                self.check()
            self.properties[key] = old

    def test_timeout_and_missing_executable(self):
        for error in (subprocess.TimeoutExpired("systemctl", 15), FileNotFoundError("python")):
            self.runner.side_effect = error
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, "Cannot inspect runtime"):
                self.check()

    def test_malformed_probe(self):
        # Keep systemctl intact and replace only the interpreter response.
        def command(argv, **kw):
            if argv[0] == "systemctl":
                return self.command(argv, **kw)
            return subprocess.CompletedProcess(argv, 0, "[]", "")
        self.runner.side_effect = command
        with self.assertRaisesRegex(ValueError, "identity"):
            self.check()

    def test_unknown_targets_default_no_and_explicit_consent(self):
        for target in ("main", "feature/custom-rh", "v4.3.0", "v9.0.0"):
            for reply in (None, "", "n", "yes", "y"):
                consent = None if reply is None else Mock(return_value=reply)
                with self.subTest(target=target, reply=reply):
                    if reply in ("yes", "y"):
                        self.assertTrue(self.check(target, confirm=consent)["unknown_target"])
                    else:
                        with self.assertRaisesRegex(ValueError, "Unknown target"):
                            self.check(target, confirm=consent)
        for error in (EOFError(), OSError("no stdin")):
            with self.assertRaisesRegex(ValueError, "Unknown target"):
                self.check("main", confirm=Mock(side_effect=error))

    def test_invalid_target_and_user_before_commands(self):
        for target in ("--help", "v4.5.0;touch x", "$(id)", "../main", "foo\nbar", "x y"):
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, "Invalid RotorHazard"):
                self.check(target)
        with self.assertRaises(ValueError):
            preflight.check_runtime("../pi", "main", "part1")
        self.runner.assert_not_called()

    def test_cli_help_cannot_return_success_to_shell_guard(self):
        for args in (["part1", USER, "--help", PYTHON],
                     ["part1", USER, "v4.5.0", PYTHON, "--help"]):
            with self.subTest(args=args), self.assertRaises(SystemExit) as error:
                preflight.main(args)
            self.assertEqual(error.exception.code, 2)
        self.runner.assert_not_called()

    def test_cli_checks_expected_interpreter_and_never_auto_confirms_unknown(self):
        self.assertEqual(preflight.main(["update", USER, "v4.5.0", PYTHON]), 0)
        self.assertEqual(preflight.main(["update", USER, "v4.5.0", "/usr/bin/python3"]), 1)
        self.assertEqual(preflight.main(["update", USER, "main", PYTHON]), 1)
        self.assertEqual(preflight.main(["update", USER, "main", PYTHON, "--accept-unknown"]), 0)


class PendingReloadTests(RuntimeFixture):
    def test_reload_requires_verified_fresh_activated_state_and_keeps_other_guards(self):
        self.properties["NeedDaemonReload"] = "yes"
        state = {"stage": "part2", "target": "v4.5.0", "phase": "activated", "fresh_install": True}
        with patch("source_safety.read_state", return_value=state), patch("source_safety.check_activation") as verify:
            result = self.check(stage="part2")
            verify.assert_called_once_with(HOME, state)
            self.assertTrue(result["pending_daemon_reload"])
            self.properties["ExecStart"] = EXEC.replace("server.py", "server.py --data /tmp/other")
            with self.assertRaisesRegex(ValueError, "ExecStart"):
                self.check(stage="part2")
            self.properties["ExecStart"] = EXEC
            self.properties["Environment"] = "PYTHONPATH=/tmp/other"
            with self.assertRaisesRegex(ValueError, "environment"):
                self.check(stage="part2")
            self.properties["Environment"] = ""
            self.manager_environment = "LD_PRELOAD=/tmp/other"
            with self.assertRaisesRegex(ValueError, "manager environment"):
                self.check(stage="part2")

    def test_unproven_pending_state_never_allows_reload(self):
        self.properties["NeedDaemonReload"] = "yes"
        valid = {"stage": "part2", "target": "v4.5.0", "phase": "activated", "fresh_install": True}
        invalid = [None] + [dict(valid, **change) for change in (
            {"phase": "switching"}, {"fresh_install": False}, {"stage": "update"}, {"target": "main"})]
        for state in invalid:
            with self.subTest(state=state), patch("source_safety.read_state", return_value=state), patch("source_safety.check_activation") as verify:
                with self.assertRaisesRegex(ValueError, "pending changes"):
                    self.check(stage="part2")
                verify.assert_not_called()
        with patch("source_safety.read_state", return_value=valid), patch("source_safety.check_activation", side_effect=ValueError("identity changed")):
            with self.assertRaisesRegex(ValueError, "identity changed"):
                self.check(stage="part2")

    def test_cli_does_not_treat_pending_reload_as_a_completed_guard(self):
        self.properties["NeedDaemonReload"] = "yes"
        state = {"stage": "part2", "target": "v4.5.0", "phase": "activated", "fresh_install": True}
        with patch("source_safety.read_state", return_value=state), patch("source_safety.check_activation"):
            self.assertEqual(preflight.main(["part2", USER, "v4.5.0", PYTHON]), 1)

    def test_loaded_unit_is_checked_normally_after_reload(self):
        self.properties["NeedDaemonReload"] = "no"
        self.assertFalse(self.check(stage="part2")["pending_daemon_reload"])
        self.properties["ExecStart"] = EXEC.replace("server.py", "server.py --data /tmp/other")
        with self.assertRaisesRegex(ValueError, "ExecStart"):
            self.check(stage="part2")


class CoordinatorTests(RuntimeFixture):
    # Use the real check and script argument builder; every external effect is mocked.
    def coordinator(self, name, marker=False, replies=None, stable_offer=False):
        self.config = SimpleNamespace(user=USER, debug_mode=False, rh_version="main" if stable_offer else "stable")
        self.markers = SimpleNamespace(first_part_of_install=marker, second_part_of_install=marker,
                                       sys_config_done=marker)
        self.effects = Mock()
        self.effects.system.return_value = 0
        self.effects.markers.side_effect = lambda markers, user: self.marker_data.update(vars(markers)) or True
        self.effects.end2.return_value = True
        self.effects.end_quick.return_value = True
        self.effects.end_update.return_value = True
        self.colors = SimpleNamespace(**dict.fromkeys(
            ("GREEN", "RED", "YELLOW", "ENDC", "BOLD", "BOLD_S", "GREEN_S", "ENDC_S", "UNDERLINE"), ""))
        namespace = dict(locked_operation=lambda function: function,
                         read_state=lambda home: getattr(self, "pending_source", None),
                         check_activation=self.effects.activation, os=SimpleNamespace(system=self.effects.system, path=SimpleNamespace(exists=lambda p: self.existing)),
                         Bcolors=self.colors, check_runtime=preflight.check_runtime,
                         load_rhim_sys_markers=lambda user: self.markers,
                         write_rhim_sys_markers=self.effects.markers, clear_the_screen=Mock(),
                         internet_check=lambda: True, sleep=Mock(), input=Mock(side_effect=(replies or []) + [""] * 5),
                         check_preferred_rh_version=lambda config: ("main" if stable_offer else "v4.5.0", "450", "v4.5.0"),
                         rh_update_check=lambda config: stable_offer,
                         end_of_part_1=self.effects.end1, end_normal_installation=self.effects.end2,
                         end_quick_installation=self.effects.end_quick, end_update=self.effects.end_update,
                         check_rotorhazard_config_status=lambda config: ("", True),
                         get_rotorhazard_server_version=lambda config: (True, "4.4.0", False))
        namespace["show_runtime_error"] = load_function("rpi_update.py", "show_runtime_error", input=namespace["input"])
        namespace["run_runtime_script"] = load_function("rpi_update.py", "run_runtime_script",
                                                        os=namespace["os"], quote=shlex.quote,
                                                        show_runtime_error=namespace["show_runtime_error"])
        namespace["show_runtime_result"] = load_function("rpi_update.py", "show_runtime_result")
        namespace["completion_input"] = load_function("rpi_update.py", "completion_input", input=namespace["input"])
        self.inputs = namespace["input"]
        return load_function("rpi_update.py", name, **namespace)

    def test_pending_switch_is_diagnosed_before_coordinator_runtime_check(self):
        install = self.coordinator("installation", marker=True)
        self.pending_source = {"stage": "part2", "target": "v4.5.0", "phase": "switching"}
        self.effects.activation.side_effect = ValueError("Interrupted source switch; keep previous and prepared")
        install(True, self.config, "", 0)
        self.effects.activation.assert_called_once_with(HOME, self.pending_source)
        self.assertEqual(self.commands, [])
        self.assert_denied()

    def assert_denied(self):
        self.effects.system.assert_not_called()
        self.effects.markers.assert_not_called()
        self.effects.end1.assert_not_called()
        self.effects.end2.assert_not_called()
        self.effects.end_quick.assert_not_called()
        self.effects.end_update.assert_not_called()

    def test_install_denial_normal_resume_and_quick_steps(self):
        self.version = [3, 9, 2]
        for marker, quick in ((False, False), (True, False), (True, 1), (False, 2)):
            with self.subTest(marker=marker, quick=quick):
                install = self.coordinator("installation", marker=marker)
                install(True, self.config, "", quick)
                self.assert_denied()

    def test_leftover_service_blocks_installation_without_effects_or_probe(self):
        self.existing = False
        self.venv = False
        install = self.coordinator("installation")
        self.assertFalse(install(True, self.config, "", 1))
        self.assert_denied()
        self.assertIn("leftover rotorhazard.service is still loaded", self.output.getvalue())
        self.assertTrue(all(command[0] == "systemctl" for command in self.commands))

    def test_debug_mode_cannot_bypass_denial(self):
        self.version = [3, 9, 2]
        install = self.coordinator("installation")
        self.config.debug_mode = True
        install(True, self.config, "", 1)
        self.assert_denied()

    def test_update_denial_no_stop_or_success(self):
        self.version = [3, 9, 2]
        update = self.coordinator("update")
        self.assertFalse(update(self.config, ""))
        self.assert_denied()
        self.inputs.assert_called_once_with("\nPress Enter to return.")
        self.assertIn("RH update not started:", self.output.getvalue())

    def test_noninteractive_denial_returns_failure_without_traceback(self):
        self.version = [3, 9, 2]
        update = self.coordinator("update")
        self.inputs.side_effect = EOFError()
        self.assertFalse(update(self.config, ""))
        self.assert_denied()

    def test_final_stable_target_checked_after_offer(self):
        update = self.coordinator("update", stable_offer=True, replies=["y"])
        update(self.config, "")
        commands = [call.args[0] for call in self.effects.system.call_args_list]
        self.assertIn("/scripts/update_rh.sh", commands[0])
        self.assertFalse(any("systemctl stop" in command for command in commands))
        args = shlex.split(commands[0])
        self.assertEqual(args[1:], [USER, "v4.5.0", "", PYTHON])
        self.effects.end_update.assert_called_once()
        # If checking main before selection, the only answer would be consumed as unknown consent.
        self.assertNotIn("unverified", self.output.getvalue())

    def test_final_stable_target_denied_on_old_runtime(self):
        self.version = [3, 9, 2]
        update = self.coordinator("update", stable_offer=True, replies=["y"])
        update(self.config, "")
        self.assert_denied()
        self.assertIn("v4.5.0 requires Python", self.output.getvalue())

    def test_pending_stable_update_uses_recorded_target_for_each_channel(self):
        for channel in ("main", "beta", "feature/custom-rh"):
            with self.subTest(channel=channel):
                update = self.coordinator("update")
                self.config.rh_version = channel
                self.pending_source = {"stage": "update", "target": "v4.5.0", "phase": "activated"}
                runtime = Mock(wraps=preflight.check_runtime)
                offer = Mock(side_effect=AssertionError("Pending updates must skip the stable offer"))
                choice = Mock(side_effect=AssertionError("Pending updates already have a target"))
                with patch.dict(update.__globals__, check_runtime=runtime,
                                rh_update_check=offer, check_preferred_rh_version=choice):
                    self.assertTrue(update(self.config, ""))
                self.effects.activation.assert_called_once_with(HOME, self.pending_source)
                runtime.assert_called_once_with(USER, "v4.5.0", "update", confirm=self.inputs)
                self.assertEqual(shlex.split(self.effects.system.call_args[0][0])[1:],
                                 [USER, "v4.5.0", "", PYTHON])
                self.assertEqual(self.config.rh_version, channel)
                self.inputs.assert_not_called()
                offer.assert_not_called()
                choice.assert_not_called()
                self.effects.end_update.assert_called_once()
                self.assertIn("Resuming pending update to v4.5.0.", self.output.getvalue())

    def test_pending_part2_uses_recorded_target_for_each_channel_and_entry(self):
        for channel in ("stable", "main", "beta", "feature/custom-rh"):
            for quick in (False, 2):
                with self.subTest(channel=channel, quick=quick):
                    install = self.coordinator("installation", marker=True)
                    self.config.rh_version = channel
                    self.pending_source = {"stage": "part2", "target": "v4.5.0", "phase": "activated"}
                    runtime = Mock(wraps=preflight.check_runtime)
                    choice = Mock(return_value=("v4.6.0", "460", "v4.6.0"))
                    with patch.dict(install.__globals__, check_runtime=runtime, check_preferred_rh_version=choice):
                        self.assertTrue(install(False, self.config, "git", quick))
                    self.effects.activation.assert_called_once_with(HOME, self.pending_source)
                    runtime.assert_called_once_with(USER, "v4.5.0", "part2", confirm=self.inputs)
                    self.assertEqual(shlex.split(self.effects.system.call_args[0][0])[1:],
                                     [USER, "v4.5.0", "git", PYTHON])
                    self.assertEqual(self.config.rh_version, channel)
                    choice.assert_not_called()
                    self.inputs.assert_called_once_with("\n\n\npress Enter to continue")
                    self.assertIn("Resuming pending part2 to v4.5.0.", self.output.getvalue())

    def test_pending_install_wrong_stage_or_switch_refuses_before_effects(self):
        for stage, phase in (("part2", "switching"), ("update", "activated")):
            with self.subTest(stage=stage, phase=phase):
                install = self.coordinator("installation", marker=True)
                self.config.rh_version = "main"
                self.pending_source = {"stage": stage, "target": "v4.5.0", "phase": phase}
                self.effects.activation.side_effect = ValueError("Interrupted source switch; manual recovery required")
                choice = Mock(side_effect=AssertionError("Pending recovery already has a target"))
                with patch.dict(install.__globals__, check_preferred_rh_version=choice):
                    self.assertFalse(install(False, self.config, "", 2))
                if stage == "part2":
                    self.effects.activation.assert_called_once_with(HOME, self.pending_source)
                else:
                    self.effects.activation.assert_not_called()
                    self.assertIn("Retry update for v4.5.0 first", self.output.getvalue())
                choice.assert_not_called()
                self.assertEqual(self.commands, [])
                self.assertEqual(self.config.rh_version, "main")
                self.assert_denied()

    def test_pending_update_switch_and_other_stage_refuse_without_effects(self):
        for stage, phase in (("update", "switching"), ("part2", "activated")):
            with self.subTest(stage=stage, phase=phase):
                update = self.coordinator("update", stable_offer=True)
                self.pending_source = {"stage": stage, "target": "v4.5.0", "phase": phase}
                self.effects.activation.side_effect = ValueError("Interrupted source switch; manual recovery required")
                offer = Mock(side_effect=AssertionError("Pending recovery must skip the offer"))
                with patch.dict(update.__globals__, rh_update_check=offer):
                    self.assertFalse(update(self.config, ""))
                if stage == "update":
                    self.effects.activation.assert_called_once_with(HOME, self.pending_source)
                    self.assertIn("manual recovery required", self.output.getvalue())
                else:
                    self.effects.activation.assert_not_called()
                    self.assertIn("Retry part2 for v4.5.0 first", self.output.getvalue())
                self.assertEqual(self.commands, [])
                offer.assert_not_called()
                self.assert_denied()

    def test_failed_one_time_stable_update_retries_after_live_becomes_stable(self):
        update = self.coordinator("update", stable_offer=True, replies=["y"])
        live_version = ["4.4.0"]
        offer = Mock(side_effect=lambda config: live_version[0] != "4.5.0")

        def activation_fails(command):
            live_version[0] = "4.5.0"
            self.pending_source = {"stage": "update", "target": "v4.5.0", "phase": "activated"}
            return 1

        self.effects.system.side_effect = activation_fails
        with patch.dict(update.__globals__, rh_update_check=offer):
            self.assertFalse(update(self.config, ""))
            self.effects.end_update.assert_not_called()
            self.assertEqual(live_version[0], "4.5.0")
            self.effects.system.side_effect = None
            self.assertTrue(update(self.config, ""))
        offer.assert_called_once_with(self.config)
        self.assertEqual(self.config.rh_version, "main")
        self.assertEqual(self.effects.system.call_count, 2)
        for call in self.effects.system.call_args_list:
            self.assertEqual(shlex.split(call.args[0])[1:], [USER, "v4.5.0", "", PYTHON])
        self.effects.activation.assert_called_once_with(HOME, self.pending_source)
        self.effects.end_update.assert_called_once()

    def test_unknown_update_default_no(self):
        update = self.coordinator("update", stable_offer=True, replies=["n", ""])
        update(self.config, "")
        self.assert_denied()

    def test_successful_install_stages_pass_validated_paths(self):
        for stage in (1, 2):
            with self.subTest(stage=stage):
                self.fresh()
                install = self.coordinator("installation", marker=(stage == 2))
                install(False, self.config, "", stage)
                commands = [call.args[0] for call in self.effects.system.call_args_list]
                script = next(command for command in commands if "/install_rh_part_" in command)
                self.assertEqual(shlex.split(script)[1:], [USER, "v4.5.0", "", PYTHON])
                self.assertNotIn("sudo systemctl stop rotorhazard", commands)
                self.effects.markers.assert_called_once()

    def test_successful_fresh_part1_passes_validated_system_base(self):
        self.fresh()
        self.venv = False
        self.prefix = self.base_prefix
        self.executable = "/usr/bin/python3"
        install = self.coordinator("installation")
        install(False, self.config, "", 1)
        commands = [call.args[0] for call in self.effects.system.call_args_list]
        script = next(command for command in commands if "/install_rh_part_1.sh" in command)
        self.assertEqual(shlex.split(script)[1:], [USER, "v4.5.0", "", "/usr/bin/python3"])
        self.effects.markers.assert_called_once()
        self.assertTrue(self.marker_data["fresh_install_pending"])

    def test_fresh_part1_then_failed_part2_can_be_retried(self):
        self.fresh()
        self.venv = False
        self.prefix = self.base_prefix
        self.executable = "/usr/bin/python3"
        install = self.coordinator("installation")
        self.assertTrue(install(False, self.config, "", 1))
        self.assertTrue(self.marker_data["fresh_install_pending"])
        self.venv = True
        self.prefix = HOME + "/.venv"
        self.executable = PYTHON
        self.existing = True  # Part 2 downloaded code, but pip failed before service creation.
        install = self.coordinator("installation", marker=True)
        self.effects.system.side_effect = lambda cmd: 1 if "install_rh_part_2" in cmd else 0
        self.assertFalse(install(False, self.config, "", 2))
        self.effects.markers.assert_not_called()
        self.assertTrue(self.marker_data["fresh_install_pending"])
        install = self.coordinator("installation", marker=True)
        self.assertTrue(install(False, self.config, "", 2))
        self.assertFalse(self.marker_data["fresh_install_pending"])
        events = [call[0] for call in self.effects.mock_calls]
        self.assertLess(events.index("markers"), events.index("end_quick"))

    def test_script_failure_has_no_success_or_marker(self):
        install = self.coordinator("installation")
        self.effects.system.side_effect = lambda cmd: 1 if "install_rh_part_1" in cmd else 0
        install(False, self.config, "")
        self.effects.markers.assert_not_called()
        self.effects.end1.assert_not_called()

    def test_failed_stop_does_not_start_script(self):
        update = self.coordinator("update")
        self.effects.system.return_value = 1
        update(self.config, "")
        self.assertEqual(self.effects.system.call_count, 1)
        self.effects.end_update.assert_not_called()

    def test_restart_does_not_reset_markers_before_guard(self):
        self.version = [3, 9, 2]
        install = self.coordinator("installation", marker=True)
        install(True, self.config, "", restart=True)
        self.assertTrue(self.markers.first_part_of_install)
        self.assertTrue(self.markers.second_part_of_install)
        self.assert_denied()

    def test_failed_host_configuration_does_not_run_install_or_record_uart(self):
        install = self.coordinator("installation")
        self.effects.system.side_effect = lambda cmd: 1 if "sys_conf.sh" in cmd else 0
        self.assertFalse(install(True, self.config, ""))
        self.effects.markers.assert_not_called()
        self.effects.end1.assert_not_called()
        self.assertFalse(self.markers.first_part_of_install)
        self.assertFalse(hasattr(self.markers, "uart_support_added"))
        self.assertTrue(any("install_rh_part_1" in call.args[0] for call in self.effects.system.call_args_list))

    def test_restart_script_failure_preserves_completed_state(self):
        install = self.coordinator("installation", marker=True)
        self.effects.system.side_effect = lambda cmd: 1 if "install_rh_part_1" in cmd else 0
        self.assertFalse(install(True, self.config, "", restart=True))
        self.assertTrue(self.markers.first_part_of_install)
        self.assertTrue(self.markers.second_part_of_install)
        self.assertTrue(self.markers.sys_config_done)
        self.effects.markers.assert_not_called()

    def test_no_uart_claim_when_system_configuration_is_skipped_or_debug(self):
        for allowed, debug in ((False, False), (True, True)):
            with self.subTest(allowed=allowed, debug=debug):
                install = self.coordinator("installation")
                self.config.debug_mode = debug
                self.assertTrue(install(allowed, self.config, ""))
                self.assertFalse(hasattr(self.markers, "uart_support_added"))
                self.assertFalse(self.markers.sys_config_done)

    def test_progress_write_failure_has_no_completion_menu(self):
        for stage in (1, 2):
            with self.subTest(stage=stage):
                install = self.coordinator("installation", marker=(stage == 2))
                self.effects.markers.side_effect = None
                self.effects.markers.return_value = False
                self.assertFalse(install(False, self.config, "", stage))
                self.effects.end1.assert_not_called()
                self.effects.end_quick.assert_not_called()

    def test_successful_stages_accept_eof_and_return_actual_completion_status(self):
        for stage in (1, 2):
            install = self.coordinator("installation", marker=(stage == 2))
            self.inputs.side_effect = EOFError()
            self.assertTrue(install(False, self.config, "", stage))
        update = self.coordinator("update")
        self.effects.end_update.return_value = False
        self.assertFalse(update(self.config, ""))
        self.effects.end_update.assert_called_once_with(self.config, True, True)

    def test_quick_configuration_failure_is_not_reported_as_completed(self):
        install = self.coordinator("installation", marker=True)
        self.effects.end_quick.return_value = False
        self.assertFalse(install(False, self.config, "", 2))
        self.assertNotIn("Installation completed", self.output.getvalue())


class SyntaxTests(unittest.TestCase):
    def test_isolated_cli_reports_pending_reload_without_import_traceback(self):
        fixture = (ROOT / "tests/fixtures/systemctl_show_standard.txt").read_text()
        fixture = fixture.replace("NeedDaemonReload=no", "NeedDaemonReload=yes")
        code = """
import runpy, sys
from types import SimpleNamespace
guard = runpy.run_path(sys.argv[1])["check_runtime"].__globals__
guard["pwd"].getpwuid = lambda uid: SimpleNamespace(pw_name="pi", pw_gid=1000)
guard["grp"].getgrgid = lambda gid: SimpleNamespace(gr_name="pi")
guard["os"].path.lexists = lambda path: False
guard["run"] = lambda argv: SimpleNamespace(returncode=0, stdout=sys.argv[2], stderr="")
sys.exit(guard["main"](["update", "pi", "v4.5.0", "/home/pi/.venv/bin/python3"]))
"""
        result = subprocess.run([sys.executable, "-I", "-B", "-c", code,
                                 str(ROOT / "runtime_preflight.py"), fixture],
                                cwd="/tmp", capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertIn("pending changes", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_python36_syntax(self):
        for filename in ("runtime_preflight.py", "rpi_update.py", "NuclearHazard/nh-quick-install.py", "NuclearHazard/nh-quick-update.py", "source_safety.py"):
            ast.parse((ROOT / filename).read_text(), filename=filename, feature_version=(3, 6))


class NuclearHazardTests(unittest.TestCase):
    def test_coordinator_failure_is_returned_as_a_nonzero_exit_status(self):
        for filename, operation in (("nh-quick-install.py", "installation"), ("nh-quick-update.py", "update")):
            for success in (True, False):
                config = SimpleNamespace(user=USER, rh_version="stable")
                namespace = dict(os=SimpleNamespace(getenv=lambda key: "2" if key == "INSTALL_STEP" else "stable",
                                                     path=SimpleNamespace(exists=lambda path: True)),
                                 name_check=lambda: USER, compatibility_check=Mock(),
                                 load_json=lambda path: config, write_json=Mock())
                namespace[operation] = Mock(return_value=success)
                main = load_function("NuclearHazard/" + filename, "main", **namespace)
                with self.subTest(filename=filename, success=success):
                    self.assertEqual(main(), 0 if success else 1)
