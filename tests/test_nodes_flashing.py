import ast
import builtins
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from contextlib import redirect_stdout


ROOT = Path(__file__).resolve().parents[1]


def load_functions(filename, **namespace):
    """Load only function definitions; never import application or hardware startup."""
    path = ROOT / filename
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


class NodeFlashingTests(unittest.TestCase):
    def setUp(self):
        self.config = SimpleNamespace(debug_mode=False, user="fixture", port_name="ttyS0",
                                      rh_version="stable", nodes_number=3, gpio_reset_pin=17,
                                      i2c_bus_number=1)
        colors = SimpleNamespace(**{name: "" for name in (
            "RED", "GREEN", "YELLOW", "ENDC", "BOLD", "BOLD_S", "ENDC_S", "GREEN_S",
            "YELLOW_S", "RED_S", "RED_MENU_HEADER", "UNDERLINE_S")})
        self.output = io.StringIO()
        self.redirect = redirect_stdout(self.output)
        self.redirect.__enter__()
        self.addCleanup(self.redirect.__exit__, None, None, None)
        self.command = Mock(side_effect=AssertionError("Unexpected external command"))
        self.ns = load_functions("nodes_flash.py", os=SimpleNamespace(system=self.command),
                                 sleep=Mock(), Bcolors=colors, clear_the_screen=Mock(),
                                 logo_top=Mock(), input=Mock(return_value=""),
                                 prepare_mate_node=Mock(), reset_gpio_pin=Mock(),
                                 rhim_load_config=Mock(return_value=self.config))
        self.common = load_functions("nodes_flash_common.py", sleep=Mock(), Bcolors=colors,
                                     rhim_load_config=Mock(return_value=self.config))

    def call(self, name, *args, **kwargs):
        return self.ns[name](self.config, *args, **kwargs)

    def test_smbus2_success_and_legacy_fallback(self):
        real_import = builtins.__import__
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                factory = Mock()
                imports = []

                def import_bus(name, *args, **kwargs):
                    imports.append(name)
                    if name == "smbus2" and legacy:
                        raise ImportError("no smbus2")
                    if name in ("smbus2", "smbus"):
                        return SimpleNamespace(SMBus=factory)
                    return real_import(name, *args, **kwargs)

                with patch("builtins.__import__", side_effect=import_bus):
                    self.assertIs(self.common["com_init"](1), factory.return_value)
                factory.assert_called_once_with(1)
                self.assertEqual(imports, ["smbus2", "smbus"] if legacy else ["smbus2"])

    def test_missing_libraries_and_bus_open_errors_propagate(self):
        for error in (ModuleNotFoundError("both libraries missing"),
                      PermissionError("permission denied"), OSError("bus missing")):
            for legacy in (False, True):
                with self.subTest(error=error, legacy=legacy):
                    def import_bus(name, *args, **kwargs):
                        if legacy and name == "smbus2":
                            raise ImportError("no smbus2")
                        if isinstance(error, ModuleNotFoundError):
                            raise error
                        return SimpleNamespace(SMBus=Mock(side_effect=error))

                    with patch("builtins.__import__", side_effect=import_bus):
                        with self.assertRaises(type(error)):
                            self.common["com_init"](1)
                    self.assertIn(str(error), self.output.getvalue())

    def test_i2c_reset_failure_propagates_and_closes_bus(self):
        bus = Mock()
        bus.write_i2c_block_data.side_effect = OSError("wire disconnected")
        self.common["com_init"] = Mock(return_value=bus)
        with self.assertRaisesRegex(OSError, "wire disconnected"):
            self.common["prepare_mate_node"](8)
        bus.close.assert_called_once_with()
        self.assertIn("wire disconnected", self.output.getvalue())

    def test_i2c_reset_sequence_and_legacy_bus_default(self):
        bus = Mock()
        self.common["com_init"] = Mock(return_value=bus)
        del self.config.i2c_bus_number
        self.common["prepare_mate_node"](10)
        self.common["com_init"].assert_called_once_with(1)
        self.assertEqual([call[0] for call in bus.write_i2c_block_data.call_args_list],
                         [(10, 0x79, [1, 1]), (10, 0x79, [0, 0]), (10, 0x79, [1, 1])])
        bus.close.assert_called_once_with()

    def test_gpio_reset_failure_propagates(self):
        gpio = Mock()
        gpio.output.side_effect = RuntimeError("GPIO unavailable")
        with patch("builtins.__import__", return_value=SimpleNamespace(GPIO=gpio)):
            with self.assertRaisesRegex(RuntimeError, "GPIO unavailable"):
                self.common["reset_gpio_pin"](17)
        self.assertIn("GPIO unavailable", self.output.getvalue())

    def test_reset_failure_prevents_flash_or_uart(self):
        for gpio in (False, True):
            for uart in (False, True):
                with self.subTest(gpio=gpio, uart=uart):
                    self.ns["reset_gpio_pin"].side_effect = OSError("reset failed")
                    self.ns["prepare_mate_node"].side_effect = OSError("reset failed")
                    self.assertFalse(self.call("node_operation", 1, gpio_node=gpio, uart=uart))
        self.command.assert_not_called()

    def test_retry_limits_and_bootloader_order(self):
        for initial in (0, 1):
            for codes, success in (([0], True), ([1, 0], True), ([1, 1], False)):
                with self.subTest(initial=initial, codes=codes):
                    self.command.reset_mock(side_effect=True)
                    self.command.side_effect = codes
                    self.ns["prepare_mate_node"].reset_mock()
                    self.assertEqual(self.call("node_operation", 1, initial_bootloader=initial), success)
                    self.assertEqual(self.command.call_count, len(codes))
                    self.assertEqual(self.ns["prepare_mate_node"].call_count, len(codes))
                    for index, call in enumerate(self.command.call_args_list):
                        boot = initial if index == 0 else 1 - initial
                        self.assertIn("-b {}".format(57600 if boot == 0 else 115200), call[0][0])
                        self.assertNotIn("||", call[0][0])
                        self.assertNotIn("touch", call[0][0])

    def test_firmware_targets_and_gpio_reset(self):
        for target, suffix in (("firmware", "stable/node_0.hex"), ("blink", "blink.hex"),
                               ("custom", "custom_firmware/custom_node.hex")):
            self.command.side_effect = [0]
            self.assertTrue(self.call("node_operation", 3, True, target))
            self.assertIn(suffix, self.command.call_args[0][0])
        self.assertEqual(self.ns["reset_gpio_pin"].call_count, 3)
        self.ns["prepare_mate_node"].assert_not_called()

    def test_aggregate_results_include_odd_gpio_node_and_continue_after_failure(self):
        for results in ([True, True, True], [False, True, True], [True, True, False]):
            with self.subTest(results=results):
                operation = self.ns["node_operation"] = Mock(side_effect=results)
                success_image = self.ns["successful_update_image"] = Mock()
                failure_image = self.ns["unsuccessful_update_image"] = Mock()
                self.assertEqual(self.call("all_nodes_flash"), all(results))
                self.assertEqual(operation.call_count, 3)
                self.assertEqual([call[0][2] for call in operation.call_args_list], [False, False, True])
                self.assertEqual(success_image.call_count, int(all(results)))
                self.assertEqual(failure_image.call_count, int(not all(results)))

    def test_one_and_even_node_series(self):
        for count in (1, 2, 8):
            self.config.nodes_number = count
            operation = self.ns["node_operation"] = Mock(return_value=True)
            self.assertTrue(self.call("all_nodes_flash"))
            self.assertEqual(operation.call_count, count)
            self.assertEqual(operation.call_args[0][2], count == 1)

    def test_individual_failure_message(self):
        self.command.side_effect = [1, 1]
        self.assertFalse(self.call("flash_firmware_onto_a_node", 1))
        self.assertIn("Node 1 - not flashed", self.output.getvalue())
        self.assertNotIn("Node 1 - flashed", self.output.getvalue())

    def test_uart_retries_use_result_without_marker_files(self):
        for codes, success in (([0], True), ([1, 0], True), ([1, 1], False)):
            with self.subTest(codes=codes):
                self.command.reset_mock(side_effect=True)
                self.command.side_effect = codes
                self.assertEqual(self.call("check_uart_con_with_a_node", 1), success)
                self.assertEqual(self.command.call_count, len(codes))
                self.assertNotIn("-U", self.command.call_args[0][0])
        self.assertIn("UART connection failed", self.output.getvalue())

    def test_debug_mode_never_runs_commands_or_claims_success(self):
        self.config.debug_mode = True
        self.assertFalse(self.call("all_nodes_flash"))
        self.assertFalse(self.call("firmware_flash"))
        self.assertFalse(self.call("check_uart_connection"))
        self.command.assert_not_called()
        self.ns["prepare_mate_node"].assert_not_called()
        self.ns["reset_gpio_pin"].assert_not_called()
        self.assertNotIn(" - flashed", self.output.getvalue())
        self.assertNotIn(" - DONE", self.output.getvalue())

    def test_legacy_main_entry_does_not_open_i2c(self):
        menu = self.ns["flashing_menu"] = Mock()
        self.ns["main"]()
        menu.assert_called_once_with(self.config)

    def test_first_time_series_retains_earlier_failure(self):
        self.command.side_effect = [1, 1, 0]
        self.ns["input"] = Mock(side_effect=["1", "", "", "e"])
        self.assertFalse(self.call("first_flashing"))
        self.assertNotIn("FIRMWARE FLASHING - DONE", self.output.getvalue())

    def test_menu_ignores_obsolete_marker_files(self):
        self.ns["input"] = Mock(return_value="e")
        self.call("flashing_menu")
        self.command.assert_not_called()

    def test_first_time_flashing_retries_and_debug(self):
        for codes, expected in (([0], "Node - flashed"), ([1, 0], "Node - flashed"),
                                ([1, 1], "Node - not flashed")):
            with self.subTest(codes=codes):
                self.command.reset_mock(side_effect=True)
                self.command.side_effect = codes
                self.ns["input"] = Mock(side_effect=["1", "", "e", "e"])
                self.output.seek(0)
                self.output.truncate()
                self.assertEqual(self.call("first_flashing"), codes[-1] == 0)
                self.assertEqual(self.command.call_count, len(codes))
                self.assertIn(expected, self.output.getvalue())
                self.assertEqual("FIRMWARE FLASHING - DONE" in self.output.getvalue(), codes[-1] == 0)
        self.config.debug_mode = True
        self.command.reset_mock()
        self.ns["input"] = Mock(side_effect=["1", "", "e", "e"])
        self.call("first_flashing")
        self.command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
