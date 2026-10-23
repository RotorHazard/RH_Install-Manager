import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import mock_open


ROOT = Path(__file__).resolve().parents[1]


def load_function(filename, name, **namespace):
    """Compile the real function without importing application startup code."""
    path = ROOT / filename
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    functions = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(functions) != 1:
        raise AssertionError(f"Expected one top-level function {name} in {path}")
    module = ast.Module(body=functions, type_ignores=[])
    exec(compile(module, str(path), "exec"), namespace)
    return namespace[name]


class PreferredVersionTests(unittest.TestCase):
    def select(self, channel, stable="6n4.440.36", beta="4.5.0-beta.1"):
        opened = mock_open(read_data=f"{stable}\n\n{beta}\nignored release notes\n")
        select = load_function("rpi_update.py", "check_preferred_rh_version", open=opened)
        result = select(SimpleNamespace(user="test-user", rh_version=channel))
        opened.assert_called_once_with(
            "/home/test-user/RH_Install-Manager/version.txt", "r")
        return result

    def test_stable(self):
        self.assertEqual(self.select("stable"), ("v4.4.0", "440", "v4.4.0"))

    def test_beta(self):
        self.assertEqual(self.select("beta"), ("v4.5.0-beta.1", "440", "v4.4.0"))

    def test_main_and_master(self):
        for channel in ("main", "master"):
            with self.subTest(channel=channel):
                self.assertEqual(self.select(channel), ("main", "440", "v4.4.0"))

    def test_custom_ref_is_preserved(self):
        for ref in ("custom", "v4.3.0", "feature/custom-rh"):
            with self.subTest(ref=ref):
                self.assertEqual(self.select(ref), (ref, "440", "v4.4.0"))

    def test_stable_ignores_beta_line(self):
        self.assertEqual(self.select("stable", beta="9.8.7-beta.2"),
                         ("v4.4.0", "440", "v4.4.0"))

    def test_beta_uses_third_line_independently(self):
        self.assertEqual(self.select("beta", stable="7a.450.36", beta="9.8.7-beta.2"),
                         ("v9.8.7-beta.2", "450", "v4.5.0"))

    def test_hypothetical_stable_bump_keeps_beta_target(self):
        for channel, target in (("stable", "v4.5.0"), ("beta", "v4.5.0-beta.1"),
                                ("main", "main"), ("master", "main"),
                                ("feature/custom-rh", "feature/custom-rh")):
            with self.subTest(channel=channel):
                self.assertEqual(self.select(channel, stable="6n4.450.36"),
                                 (target, "450", "v4.5.0"))


class FirmwareVersionTests(unittest.TestCase):
    def test_release_channels(self):
        select = load_function("nodes_flash.py", "firmware_version_selection")
        for channel, expected in (("stable", "stable"), ("beta", "beta"),
                                  ("main", "main"), ("master", "main")):
            with self.subTest(channel=channel):
                self.assertEqual(select(SimpleNamespace(rh_version=channel)), expected)

    def test_custom_refs_fall_back_to_stable(self):
        select = load_function("nodes_flash.py", "firmware_version_selection")
        for ref in ("custom", "v4.3.0", "feature/custom-rh"):
            with self.subTest(ref=ref):
                self.assertEqual(select(SimpleNamespace(rh_version=ref)), "stable")
