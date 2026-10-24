"""Config saves exercise real temporary files without importing the application."""
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_version_selection import load_function


class ConfigWriteTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'updater-config.json'
        self.original = '{"user": "pi"}\n'
        self.path.write_text(self.original)
        self.writer = load_function('modules.py', 'write_json', os=os,
                                    tempfile=tempfile, json=json,
                                    SimpleNamespace=SimpleNamespace)

    def assert_preserved(self):
        self.assertEqual(self.path.read_text(), self.original)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_dict_and_namespace_keep_format_and_permissions(self):
        self.path.chmod(0o640)
        for value in ({'user': 'new'}, SimpleNamespace(user='new')):
            with self.subTest(value=value):
                self.assertIsNone(self.writer(value, self.path))
                self.assertEqual(self.path.read_text(), '{\n    "user": "new"\n}')
                self.assertEqual(self.path.stat().st_mode & 0o777, 0o640)

    def test_serialization_failure_preserves_previous_config(self):
        with self.assertRaises(TypeError):
            self.writer({'user': 'new', 'invalid': object()}, self.path)
        self.assert_preserved()

    def test_partial_write_failure_preserves_previous_config(self):
        def fail(value, output, **kwargs):
            output.write('{"partial":')
            raise OSError('disk full')

        with patch.object(json, 'dump', side_effect=fail):
            with self.assertRaisesRegex(OSError, 'disk full'):
                self.writer({'user': 'new'}, self.path)
        self.assert_preserved()

    def test_flush_failure_preserves_previous_config(self):
        with patch.object(os, 'fsync', side_effect=OSError('storage failed')):
            with self.assertRaisesRegex(OSError, 'storage failed'):
                self.writer({'user': 'new'}, self.path)
        self.assert_preserved()

    def test_failed_replace_preserves_config_and_allows_retry(self):
        with patch.object(os, 'replace', side_effect=PermissionError('read-only storage')):
            with self.assertRaises(PermissionError):
                self.writer({'user': 'new'}, self.path)
        self.assert_preserved()
        self.writer({'user': 'new'}, self.path)
        self.assertEqual(json.loads(self.path.read_text()), {'user': 'new'})

    def test_symlink_still_updates_its_target(self):
        link = self.path.parent / 'config-link.json'
        link.symlink_to(self.path.name)
        self.writer({'user': 'new'}, link)
        self.assertTrue(link.is_symlink())
        self.assertEqual(json.loads(self.path.read_text()), {'user': 'new'})

    def test_new_file_is_complete(self):
        self.path.unlink()
        self.writer({'user': 'new'}, self.path)
        self.assertEqual(json.loads(self.path.read_text()), {'user': 'new'})
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])
