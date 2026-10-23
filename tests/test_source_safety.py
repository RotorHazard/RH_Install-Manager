"""Real temporary filesystem checks; never execute installer payloads or systemd."""
import contextlib
import fcntl
import io
import json
import os
from pathlib import Path
import shutil
import select
import socket
import sqlite3
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import source_safety as safety


class FilesystemCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve() / "home"
        self.home.mkdir()
        self.source = self.home / "RotorHazard"
        self.server = self.source / "src/server"
        self.server.mkdir(parents=True)
        self.put(self.server / "server.py", "new program")
        self.put(self.server / "requirements.txt", "fixture")
        self.output = io.StringIO()
        redirect = contextlib.redirect_stdout(self.output)
        redirect.__enter__()
        self.addCleanup(redirect.__exit__, None, None, None)
        errors = contextlib.redirect_stderr(self.output)
        errors.__enter__()
        self.addCleanup(errors.__exit__, None, None, None)

    def put(self, path, content="data"):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def resolve(self):
        return safety.resolve_data(str(self.home))

    def legacy(self):
        self.put(self.server / "config.json", '{"old": true}')
        self.put(self.server / "database.db", "database")
        return self.resolve()

    def backup(self, data=None):
        return Path(safety.make_backup(str(self.home), str(self.source), data or self.resolve()))

    def archive(self, path, members=None):
        members = members or {"RotorHazard-ref/src/server/server.py": "new official program",
                              "RotorHazard-ref/src/server/requirements.txt": "fixture requirements"}
        with zipfile.ZipFile(path, "w") as stream:
            for name, value in members.items():
                stream.writestr(name, value)


class ResolverTests(FilesystemCase):
    def test_readonly_fresh_prospective_default(self):
        self.assertEqual(self.resolve()["kind"], "prospective")
        self.assertFalse((self.home / "rh-data").exists())

    def test_default_precedes_legacy_but_ini_precedes_default(self):
        self.legacy()
        default = self.home / "rh-data"
        default.mkdir()
        self.assertEqual(self.resolve()["real"], str(default))
        external = Path(self.temp.name).resolve() / "external"
        external.mkdir()
        self.put(self.server / "datapath.ini", str(external) + "\nignored second line")
        self.assertEqual(self.resolve()["real"], str(external))

    def test_absolute_relative_tilde_and_firstline(self):
        external = self.home / "data"
        external.mkdir()
        for ini in (str(external), "../../../data", "~/data"):
            with self.subTest(ini=ini):
                self.put(self.server / "datapath.ini", ini + "\nnot a path")
                self.assertEqual(self.resolve()["real"], str(external))

    def test_ini_must_exist_and_cannot_be_empty_or_a_file(self):
        for value in ("", "missing", str(self.server / "server.py")):
            with self.subTest(value=value):
                self.put(self.server / "datapath.ini", value)
                with self.assertRaises(safety.SafetyError):
                    self.resolve()
        self.assertFalse((self.server / "missing").exists())

    def test_legacy_database_without_config_requires_manual_choice(self):
        self.put(self.server / "database.db")
        with self.assertRaisesRegex(safety.SafetyError, "Choose.*datapath.ini"):
            self.resolve()
        self.assertFalse((self.home / "rh-data").exists())

    def test_empty_existing_default_cannot_hide_configless_legacy_database(self):
        self.put(self.server / "database.db", "legacy")
        (self.home / "rh-data").mkdir()
        with self.assertRaisesRegex(safety.SafetyError, "hidden.*datapath.ini"):
            self.resolve()
        self.put(self.home / "rh-data/database.db", "effective database")
        self.assertEqual(self.resolve()["kind"], "default")

    def test_symlink_default_external_target_and_dangling_link(self):
        external = Path(self.temp.name).resolve() / "external"
        external.mkdir()
        (self.home / "rh-data").symlink_to(external, target_is_directory=True)
        self.assertEqual(self.resolve()["real"], str(external))
        external.rmdir()
        with self.assertRaises(safety.SafetyError):
            self.resolve()

    def test_symlink_into_source_and_source_directory_alias_are_refused(self):
        (self.home / "rh-data").symlink_to(self.server, target_is_directory=True)
        with self.assertRaisesRegex(safety.SafetyError, "symlink"):
            self.resolve()
        (self.home / "rh-data").unlink()
        moved = self.home / "other"
        self.source.rename(moved)
        self.source.symlink_to(moved, target_is_directory=True)
        with self.assertRaisesRegex(safety.SafetyError, "symlinks"):
            self.resolve()

    def test_in_tree_directory_and_server_dot_are_explicit(self):
        data = self.source / "custom-data"
        data.mkdir()
        self.put(self.server / "datapath.ini", "../../custom-data")
        self.assertTrue(self.resolve()["in_tree"])
        self.assertEqual(self.resolve()["real"], str(data))
        self.put(self.server / "datapath.ini", ".")
        self.assertEqual(self.resolve()["real"], str(self.server))

    def test_ancestors_runtime_backup_and_stage_are_refused(self):
        for path in (self.home, self.source, self.source / "src", self.home / ".venv",
                     self.home / "rhim-backups", self.home / ".rhim-stage", self.home / ".rhim_markers"):
            path.mkdir(exist_ok=True)
            self.put(self.server / "datapath.ini", str(path))
            with self.subTest(path=path), self.assertRaises(safety.SafetyError):
                self.resolve()

    def test_shared_config_write_uses_external_path_and_read_does_not_create(self):
        external = self.home / "data"
        external.mkdir()
        self.put(self.server / "datapath.ini", "~/data")
        self.assertEqual(safety.config_path(str(self.home)), str(external / "config.json"))
        safety.write_config(str(self.home), {"GENERAL": {"HTTP_PORT": 5000}})
        self.assertEqual(json.loads((external / "config.json").read_text())["GENERAL"]["HTTP_PORT"], 5000)
        self.assertFalse((self.server / "config.json").exists())

    def test_external_critical_file_link_needs_explicit_data_choice(self):
        self.legacy()
        (self.server / "database.db").unlink()
        target = self.put(self.home / "outside.db", "database")
        (self.server / "database.db").symlink_to(target)
        with self.assertRaisesRegex(safety.SafetyError, "Critical data symlink"):
            self.resolve()

    def test_configuration_write_preserves_internal_file_link(self):
        target = self.put(self.server / "saved-config.json", '{"value": "old"}')
        link = self.server / "config.json"
        link.symlink_to("saved-config.json")
        safety.write_config(str(self.home), {"value": "new"})
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.readlink(str(link)), "saved-config.json")
        self.assertEqual(json.loads(target.read_text()), {"value": "new"})
        self.assertEqual(link.read_text(), target.read_text())



class SourceTests(FilesystemCase):
    def test_zip_extracts_one_exact_root_and_required_files(self):
        archive = self.home / "source.zip"
        self.archive(archive)
        destination = self.home / "stage"
        destination.mkdir()
        result = safety.extract_zip(str(archive), str(destination))
        self.assertEqual(Path(result).name, "RotorHazard-ref")
        self.assertEqual((Path(result) / "src/server/server.py").read_text(), "new official program")

    def test_zip_rejects_traversal_multiple_roots_missing_structure_and_symlinks(self):
        cases = ({"../escape": "bad"}, {"/absolute": "bad"}, {"a/x": "a", "b/y": "b"},
                 {"one/server.py": "bad"}, {"a/../x": "bad"}, {"a\\x": "bad"})
        for index, members in enumerate(cases):
            archive = self.home / (str(index) + ".zip")
            self.archive(archive, members)
            with self.subTest(members=members), self.assertRaises(safety.SafetyError):
                safety.extract_zip(str(archive), str(self.home))
        archive = self.home / "link.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            info = zipfile.ZipInfo("one/link")
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            bundle.writestr(info, "outside")
        with self.assertRaises(safety.SafetyError):
            safety.extract_zip(str(archive), str(self.home))

    def test_zip_preserves_program_executable_bits_without_special_permission_bits(self):
        archive = self.home / "source.zip"
        self.archive(archive)
        with zipfile.ZipFile(archive, "a") as bundle:
            info = zipfile.ZipInfo("RotorHazard-ref/tool.sh")
            info.external_attr = (stat.S_IFREG | 0o4755) << 16
            bundle.writestr(info, "#!/bin/sh\n")
        destination = self.home / "stage"
        destination.mkdir()
        source = safety.extract_zip(str(archive), str(destination))
        self.assertEqual(stat.S_IMODE((Path(source) / "tool.sh").stat().st_mode), 0o755)

    def test_corrupt_archive_and_duplicate_entries_are_rejected(self):
        archive = self.home / "bad.zip"
        archive.write_bytes(b"broken ZIP")
        with self.assertRaises(zipfile.BadZipFile):
            safety.extract_zip(str(archive), str(self.home))
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("one/file", "a")
            with self.assertWarns(UserWarning):
                bundle.writestr("one/file", "b")
        with self.assertRaisesRegex(safety.SafetyError, "duplicate"):
            safety.extract_zip(str(archive), str(self.home))

    def test_preparation_failure_does_not_touch_live_or_stale_stages(self):
        self.legacy()
        before = safety.tree_manifest(str(self.source))
        stale = self.home / ".rhim-stage"
        stale.mkdir(mode=0o700)
        self.put(stale / "stale/sentinel")
        with patch.object(safety.shutil, "which", return_value="tool"), patch.object(
                safety, "urlopen", side_effect=OSError("download failed")):
            with self.assertRaisesRegex(OSError, "download failed"):
                safety.prepare_source(str(self.home), "v4.5.0", "")
        self.assertEqual(safety.tree_manifest(str(self.source)), before)
        self.assertEqual(list(stale.iterdir()), [stale / "stale"])

    def test_default_zip_bootstrap_needs_neither_wget_nor_unzip(self):
        archive = self.home / "fixture.zip"
        self.archive(archive)
        content = archive.read_bytes()
        with patch.dict(os.environ, {"PATH": ""}), patch.object(safety, "urlopen", return_value=io.BytesIO(content)) as download:
            stage, source, revision = safety.prepare_source(str(self.home), "v4.5.0", "")
        download.assert_called_once_with("https://codeload.github.com/RotorHazard/RotorHazard/zip/v4.5.0", timeout=60)
        self.assertEqual((Path(source) / "src/server/server.py").read_text(), "new official program")
        self.assertTrue(revision.startswith("zip-sha256:"))
        shutil.rmtree(stage)
        with patch.object(safety.shutil, "which", side_effect=lambda name: None if name in ("wget", "unzip") else "/fixture/" + name):
            safety.check_tools("part1", "")
        with patch.object(safety.shutil, "which", return_value=None), patch.object(safety, "urlopen") as download:
            with self.assertRaisesRegex(safety.SafetyError, "git is required"):
                safety.prepare_source(str(self.home), "v4.5.0", "git")
            download.assert_not_called()

    def test_git_binds_tag_and_checkout_and_rejects_missing_ref(self):
        repo = Path(self.temp.name) / "upstream"
        repo.mkdir()
        for args in (["init", "-q", str(repo)], ["-C", str(repo), "config", "user.email", "fixture@example.invalid"],
                     ["-C", str(repo), "config", "user.name", "Fixture"]):
            subprocess.run(["git"] + args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.put(repo / "src/server/server.py", "official")
        self.put(repo / "src/server/requirements.txt", "requirements")
        for args in (["add", "."], ["commit", "-qm", "fixture"], ["tag", "v4.5.0"]):
            subprocess.run(["git", "-C", str(repo)] + args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        original = safety.command
        def clone_local(argv, **kwargs):
            if argv[1] == "clone":
                argv = argv[:-2] + [str(repo), argv[-1]]
            return original(argv, stdout=kwargs.pop("stdout", subprocess.PIPE), stderr=subprocess.PIPE, **kwargs)
        with patch.object(safety, "command", side_effect=clone_local):
            stage, source, revision = safety.prepare_source(str(self.home), "v4.5.0", "git")
            self.assertEqual(subprocess.check_output(["git", "-C", source, "rev-parse", "HEAD"]).decode().strip(), revision)
            shutil.rmtree(stage)
            with self.assertRaisesRegex(safety.SafetyError, "missing or ambiguous"):
                safety.prepare_source(str(self.home), "absent", "git")


class BackupTests(FilesystemCase):
    def test_full_data_backup_includes_wal_plugins_images_and_links_without_following(self):
        data = self.legacy()
        for relative in ("database.db-wal", "database.db-shm", "cfg_bkp/config", "db_bkp/db",
                         "static/user/file", "static/image/custom.png", "plugins/custom/plugin.py",
                         "shared/file", "logs/log", "unknown-plugin/state"):
            self.put(self.server / relative, relative)
        outside = self.put(Path(self.temp.name) / "outside/secret", "private")
        (self.server / "link").symlink_to(outside.parent, target_is_directory=True)
        backup = self.backup(data)
        self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o700)
        self.assertFalse(backup.name.startswith("RotorHazard_"))
        self.assertEqual(safety.tree_manifest(str(self.server)), safety.tree_manifest(str(backup / "data")))
        self.assertTrue((backup / "data/link").is_symlink())
        self.assertEqual(os.readlink(backup / "data/link"), str(outside.parent))
        self.assertEqual(safety.tree_manifest(str(backup / "data"))["link"][0], "link")

    def test_external_data_has_independent_verified_backup(self):
        external = self.home / "data"
        self.put(external / "database.db", "external db")
        self.put(self.server / "datapath.ini", "~/data")
        backup = self.backup()
        self.assertEqual((backup / "data/database.db").read_text(), "external db")
        self.assertFalse((backup / "source/src/server/database.db").exists())

    def test_names_are_unique_and_existing_destinations_never_nest(self):
        self.legacy()
        first, second = self.backup(), self.backup()
        self.assertNotEqual(first, second)
        before = safety.tree_manifest(str(first))
        with self.assertRaisesRegex(safety.SafetyError, "already exists"):
            safety.copy_verified(str(self.source), str(first))
        self.assertEqual(safety.tree_manifest(str(first)), before)
        self.assertFalse((first / "RotorHazard").exists())

    def test_space_permission_and_copy_errors_have_no_verified_manifest(self):
        self.legacy()
        with self.assertRaisesRegex(safety.SafetyError, "free space"):
            safety.disk_check(str(self.home), 1, statvfs=lambda path: SimpleNamespace(f_bavail=0, f_frsize=4096))
        with patch.object(safety.shutil, "copytree", side_effect=PermissionError("read denied")):
            with self.assertRaisesRegex(safety.SafetyError, "incomplete copy removed: read denied"):
                self.backup()
        self.assertEqual(list((self.home / "rhim-backups").iterdir()), [])
        self.assertNotIn("Protected RH backup:", self.output.getvalue())
        self.backup()
        self.assertEqual((self.server / "database.db").read_text(), "database")

    def test_backup_storage_symlinks_and_public_permissions_are_refused(self):
        root = self.home / "rhim-backups"
        root.mkdir(mode=0o755)
        with self.assertRaisesRegex(safety.SafetyError, "0700"):
            self.backup()
        root.rmdir()
        root.symlink_to(self.home, target_is_directory=True)
        with self.assertRaisesRegex(safety.SafetyError, "symlink|Unsafe"):
            self.backup()

    def test_new_program_wins_data_wins_custom_plugins_merge_without_image_nesting(self):
        data = self.legacy()
        for relative in ("cfg_bkp/config", "db_bkp/db", "database.db-wal", "database.db-shm",
                         "static/user/a", "static/image/my.png", "plugins/custom/main.py", "shared/state", "unknown/data"):
            self.put(self.server / relative, relative)
        backup = self.backup(data)
        new = self.home / "stage"
        self.put(new / "src/server/server.py", "new bundled")
        self.put(new / "src/server/requirements.txt", "new requirements")
        self.put(new / "src/server/static/image/bundled.png", "new bundled image")
        self.put(new / "src/server/static/image/my.png", "bundled counterpart")
        self.put(new / "src/server/plugins/bundled/main.py", "new plugin")
        self.put(self.server / "plugins/bundled/main.py", "old modified bundled plugin")
        # Rebuild backup after adding the conflicting bundled plugin.
        backup = self.backup(data)
        safety.restore_to_stage(str(self.home), str(new), str(backup), data)
        self.assertEqual((new / "src/server/server.py").read_text(), "new bundled")
        for relative in safety.USER_PATHS:
            original = self.server / relative
            if original.exists():
                before = safety.tree_manifest(str(original))
                after = safety.tree_manifest(str(new / "src/server" / relative))
                for name, entry in before.items():
                    self.assertEqual(after[name], entry)
        self.assertTrue((new / "src/server/plugins/custom/main.py").is_file())
        self.assertEqual((new / "src/server/plugins/bundled/main.py").read_text(), "new plugin")
        self.assertIn("src/server/plugins/bundled/main.py", (backup / "conflicts.txt").read_text())
        self.assertFalse((new / "src/server/static/image/image").exists())
        self.assertEqual((new / "src/server/static/image/my.png").read_text(), "static/image/my.png")
        self.assertEqual((new / "src/server/static/image/bundled.png").read_text(), "new bundled image")

    def test_in_tree_data_is_restored_and_relative_ini_is_unchanged(self):
        data_path = self.source / "local-data"
        self.put(data_path / "config.json", "config")
        self.put(data_path / "database.db-wal", "wal")
        self.put(self.server / "datapath.ini", "../../local-data\n")
        data = self.resolve()
        backup = self.backup(data)
        new = self.home / "stage"
        self.put(new / "src/server/server.py", "new")
        self.put(new / "src/server/requirements.txt", "new")
        safety.restore_to_stage(str(self.home), str(new), str(backup), data)
        safety.switch_source(str(self.home), str(new), str(backup))
        self.assertEqual(self.resolve()["real"], str(data_path))
        self.assertEqual((self.server / "datapath.ini").read_text(), "../../local-data\n")
        self.assertEqual((data_path / "database.db-wal").read_text(), "wal")

    def test_internal_critical_symlink_target_is_preserved_or_conflict_refused(self):
        self.legacy()
        (self.server / "config.json").unlink()
        self.put(self.server / "custom-config.json", '{"actual": true}')
        (self.server / "config.json").symlink_to("custom-config.json")
        data = self.resolve()
        backup = self.backup(data)
        for conflict in (False, True):
            new = self.home / ("prepared-conflict" if conflict else "prepared")
            self.put(new / "src/server/server.py", "new")
            self.put(new / "src/server/requirements.txt", "new")
            if conflict:
                self.put(new / "src/server/custom-config.json", "new bundled file")
                with self.assertRaisesRegex(safety.SafetyError, "link target conflicts"):
                    safety.restore_to_stage(str(self.home), str(new), str(backup), data)
            else:
                safety.restore_to_stage(str(self.home), str(new), str(backup), data)
                self.assertEqual((new / "src/server/config.json").read_text(), '{"actual": true}')
                self.assertEqual(safety.resolve_data(str(self.home), read_source=str(new))["real"], data["real"])

    def test_second_move_failure_restores_original_path(self):
        self.legacy()
        backup = self.backup()
        staged = self.home / "staged"
        self.put(staged / "src/server/server.py", "replacement")
        before = safety.tree_manifest(str(self.source))
        rename = os.rename
        def failing(source, destination):
            if source == str(staged):
                raise OSError("second move failed")
            return rename(source, destination)
        with patch.object(safety.os, "rename", side_effect=failing):
            with self.assertRaisesRegex(OSError, "second move failed"):
                safety.switch_source(str(self.home), str(staged), str(backup))
        self.assertEqual(safety.tree_manifest(str(self.source)), before)
        self.assertTrue(staged.exists())

    def test_sqlite_wal_copy_is_readable_and_only_the_copy_is_opened(self):
        self.put(self.server / "config.json", "{}")
        database = self.server / "database.db"
        connection = sqlite3.connect(str(database))
        self.addCleanup(connection.close)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE fixture (value TEXT)")
        connection.execute("INSERT INTO fixture VALUES ('preserved WAL row')")
        connection.commit()
        self.assertGreater((self.server / "database.db-wal").stat().st_size, 0)
        before = safety.tree_manifest(str(self.server))
        backup = self.backup()
        with sqlite3.connect(str(backup / "data/database.db")) as copy:
            self.assertEqual(copy.execute("SELECT value FROM fixture").fetchone()[0], "preserved WAL row")
            self.assertEqual(copy.execute("PRAGMA quick_check").fetchone()[0], "ok")
        self.assertEqual(safety.tree_manifest(str(self.server)), before)

    def test_post_stop_lgpio_fifo_is_backed_up_without_stream_reads_and_not_revived(self):
        data = self.legacy()
        fifo = self.server / ".lgd-nfy0"
        os.mkfifo(str(fifo), 0o640)
        os.utime(str(fifo), ns=(1234567890000000000, 1234567890000000000))
        # A subprocess deadline catches accidental open/read of either FIFO stream.
        code = ("import sys; sys.path.insert(0, " + repr(str(ROOT)) + "); import source_safety as s; "
                "s.make_backup(" + repr(str(self.home)) + ", " + repr(str(self.source)) + ", s.resolve_data(" + repr(str(self.home)) + "))")
        result = subprocess.run([sys.executable, "-c", code], timeout=10, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(result.returncode, 0, result.stderr)
        backup = next((self.home / "rhim-backups").iterdir())
        copied = backup / "source/src/server/.lgd-nfy0"
        self.assertTrue(stat.S_ISFIFO(copied.lstat().st_mode))
        self.assertEqual(stat.S_IMODE(copied.lstat().st_mode), 0o640)
        self.assertEqual(copied.lstat().st_mtime_ns, fifo.lstat().st_mtime_ns)
        self.assertEqual(copied.lstat().st_atime_ns, fifo.lstat().st_atime_ns)
        new = self.home / "prepared"
        self.put(new / "src/server/server.py", "new")
        self.put(new / "src/server/requirements.txt", "new")
        safety.restore_to_stage(str(self.home), str(new), str(backup), data)
        self.assertFalse((new / "src/server/.lgd-nfy0").exists())
        self.assertTrue(stat.S_ISFIFO((backup / "data/.lgd-nfy0").lstat().st_mode))

    def test_unknown_fifo_is_preserved_in_backup_but_requires_manual_active_merge(self):
        data = self.legacy()
        os.mkfifo(str(self.server / "unknown-stream"))
        backup = self.backup(data)
        new = self.home / "prepared"
        self.put(new / "src/server/server.py", "new")
        self.put(new / "src/server/requirements.txt", "new")
        with self.assertRaisesRegex(safety.SafetyError, "Unknown FIFO"):
            safety.restore_to_stage(str(self.home), str(new), str(backup), data)
        self.assertTrue(stat.S_ISFIFO((backup / "data/unknown-stream").lstat().st_mode))

    def test_other_special_files_are_refused_without_reading(self):
        self.legacy()
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(sock.close)
        path = Path(self.temp.name) / "socket"
        sock.bind(str(path))
        with self.assertRaisesRegex(safety.SafetyError, "special file"):
            safety.tree_manifest(str(path))
        with self.assertRaisesRegex(safety.SafetyError, "special file"):
            safety.copy_verified(str(path), str(self.home / "socket-copy"))
        self.assertFalse((self.home / "socket-copy").exists())

    def test_symlink_parent_cannot_redirect_data_merge(self):
        data = self.legacy()
        self.put(self.server / "static/user/image", "old image")
        backup = self.backup(data)
        new = self.home / "prepared"
        self.put(new / "src/server/server.py", "new")
        outside = self.home / "outside"
        outside.mkdir()
        (new / "src/server/static").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(safety.SafetyError, "symlink"):
            safety.restore_to_stage(str(self.home), str(new), str(backup), data)
        self.assertEqual(list(outside.iterdir()), [])


class OperationTests(FilesystemCase):
    def setUp(self):
        super().setUp()
        self.events = []
        self.runtime = {"base_python": "/fixture/python", "python": "/fixture/python", "service_present": True, "version": [3, 11, 2], "create_venv": False}
        self.guard = patch("runtime_preflight.check_runtime", side_effect=self.check_runtime)
        self.guard.start()
        self.addCleanup(self.guard.stop)
        self.stop = patch.object(safety, "stop_and_confirm", side_effect=lambda *args: self.events.append("stop"))
        self.stop.start()
        self.addCleanup(self.stop.stop)
        self.prepare = patch.object(safety, "prepare_source", side_effect=self.prepare_fixture)
        self.prepare.start()
        self.addCleanup(self.prepare.stop)
        self.payload = patch.object(safety, "command", side_effect=self.run_payload)
        self.payload.start()
        self.addCleanup(self.payload.stop)
        self.failure = None
        self.runtime_failure = False
        self.attempts = 0

    def check_runtime(self, *args):
        self.events.append("runtime")
        if self.runtime_failure and self.events.count("runtime") > 1:
            raise safety.SafetyError("host Python changed")
        return self.runtime

    def prepare_fixture(self, home, target, method):
        self.events.append("prepare")
        root = Path(tempfile.mkdtemp(dir=home, prefix="stage-"))
        archive = root / "source.zip"
        self.archive(archive)
        source = safety.extract_zip(str(archive), str(root))
        archive.unlink()
        return str(root), source, "fixture-ref"

    def run_payload(self, argv, **kwargs):
        if argv == ["sudo", "systemctl", "daemon-reload"]:
            self.events.append("reload")
            if self.failure == "reload":
                raise safety.SafetyError("injected daemon-reload failure")
            self.runtime.pop("pending_daemon_reload", None)
            return subprocess.CompletedProcess(argv, 0)
        phase = kwargs["env"]["RHIM_SOURCE_PAYLOAD"]
        self.events.append(phase)
        safety.inherited_lock(str(self.home))
        if phase == "host":
            self.assertTrue(Path(kwargs["env"]["RHIM_PREPARED_SOURCE"]).exists())
        if phase == "activate" and self.failure != phase:
            self.runtime["service_present"] = True
        if self.failure == phase:
            if phase == "activate":
                data = safety.resolve_data(str(self.home))
                self.put(Path(data["real"]) / "config.json", '{}')
                self.put(Path(data["real"]) / "database.db", "partial new data")
            raise safety.SafetyError("injected " + phase + " failure")
        return subprocess.CompletedProcess(argv, 0)

    def run_operation(self, stage="update", target="v4.5.0"):
        return safety.run_operation(str(self.home), stage, "fixture", target, "zip", "/fixture/python")

    def test_update_order_backup_completion_and_config_evidence(self):
        self.legacy()
        self.run_operation()
        self.assertLess(self.events.index("prepare"), self.events.index("stop"))
        self.assertLess(self.events.index("host"), self.events.index("activate"))
        self.assertEqual(self.events.count("runtime"), 3)
        self.assertEqual((self.server / "database.db").read_text(), "database")
        self.assertEqual((self.server / "server.py").read_text(), "new official program")
        self.assertFalse(Path(safety.state_path(str(self.home))).exists())
        receipt = json.loads((self.home / ".rhim_markers/source-completed.json").read_text())
        self.assertEqual(receipt["data"]["real"], str(self.server))
        self.assertEqual(receipt["revision"], "fixture-ref")
        self.assertTrue(Path(receipt["backup"], "source/src/server/database.db").exists())

    def test_fresh_part1_does_not_move_working_source_and_part2_can_resume(self):
        self.legacy()
        before = safety.tree_manifest(str(self.source))
        self.run_operation("part1")
        self.assertEqual(safety.tree_manifest(str(self.source)), before)
        self.assertNotIn("activate", self.events)
        self.run_operation("part2")
        self.assertEqual((self.server / "database.db").read_text(), "database")

    def test_fresh_part2_uses_prospective_data_without_creating_it(self):
        shutil.rmtree(self.source)
        self.runtime["service_present"] = False
        self.run_operation("part2")
        self.assertTrue((self.server / "server.py").exists())
        self.assertFalse((self.home / "rh-data").exists())

    def test_fresh_partial_activation_retains_retry_flag_until_success(self):
        shutil.rmtree(self.source)
        self.runtime.update(service_present=False, fresh_install=True)
        self.failure = "activate"
        with self.assertRaises(safety.SafetyError):
            self.run_operation("part2")
        marker = self.home / ".rhim_markers/rhim_config.json"
        self.assertTrue(json.loads(marker.read_text())["fresh_install_pending"])
        self.failure = None
        self.run_operation("part2")
        self.assertFalse(json.loads(marker.read_text())["fresh_install_pending"])

    def test_fresh_pending_finalization_after_daemon_reload_failure_preserves_live_data(self):
        shutil.rmtree(self.source)
        self.runtime.update(service_present=False, fresh_install=True)
        self.failure = "activate"
        with self.assertRaises(safety.SafetyError):
            self.run_operation("part2")
        pending = safety.read_state(str(self.home))
        data = Path(pending["data"]["real"])
        self.put(data / "database.db", "races after service setup failure")
        marker = self.home / ".rhim_markers/rhim_config.json"
        self.runtime.update(service_present=True, pending_daemon_reload=True)
        self.failure = "reload"
        self.events.clear()
        with self.assertRaisesRegex(safety.SafetyError, "daemon-reload failure"):
            self.run_operation("part2")
        self.assertTrue(json.loads(marker.read_text())["fresh_install_pending"])
        self.assertEqual(safety.read_state(str(self.home)), pending)
        self.assertNotIn("host", self.events)
        self.assertNotIn("prepare", self.events)
        self.failure = None
        self.events.clear()
        self.run_operation("part2")
        self.assertEqual(data.joinpath("database.db").read_text(), "races after service setup failure")
        self.assertFalse(json.loads(marker.read_text())["fresh_install_pending"])
        self.assertLess(self.events.index("reload"), self.events.index("activate"))
        self.assertNotIn("host", self.events)
        self.assertNotIn("prepare", self.events)

    def test_reload_rechecks_runtime_before_any_activation_payload(self):
        self.legacy()
        self.runtime["fresh_install"] = True
        self.failure = "activate"
        with self.assertRaises(safety.SafetyError):
            self.run_operation("part2")
        self.failure = None
        self.runtime["pending_daemon_reload"] = True
        self.events.clear()
        self.runtime_failure = True
        with self.assertRaisesRegex(safety.SafetyError, "Python changed"):
            self.run_operation("part2")
        self.assertIn("reload", self.events)
        self.assertNotIn("activate", self.events)
        self.assertEqual((self.server / "database.db").read_text(), "partial new data")

    def test_pending_unit_changes_after_activation_cannot_clear_fresh_marker(self):
        shutil.rmtree(self.source)
        self.runtime.update(service_present=False, fresh_install=True)
        payload = self.run_payload
        def pending_reload_after_activation(argv, **kwargs):
            result = payload(argv, **kwargs)
            if kwargs.get("env", {}).get("RHIM_SOURCE_PAYLOAD") == "activate":
                self.runtime["pending_daemon_reload"] = True
            return result
        with patch.object(safety, "command", side_effect=pending_reload_after_activation):
            with self.assertRaisesRegex(safety.SafetyError, "checked, loaded service"):
                self.run_operation("part2")
        self.assertTrue(json.loads((self.home / ".rhim_markers/rhim_config.json").read_text())["fresh_install_pending"])
        self.assertEqual(safety.read_state(str(self.home))["phase"], "activated")
        self.assertFalse((self.home / ".rhim_markers/source-completed.json").exists())

    def test_failed_preparation_never_stops_service_or_changes_source(self):
        self.legacy()
        before = safety.tree_manifest(str(self.source))
        with patch.object(safety, "prepare_source", side_effect=safety.SafetyError("download failed")):
            with self.assertRaises(safety.SafetyError):
                self.run_operation()
        self.assertNotIn("stop", self.events)
        self.assertNotIn("host", self.events)
        self.assertEqual(safety.tree_manifest(str(self.source)), before)

    def test_copy_failure_never_records_state_completion_or_switch(self):
        self.legacy()
        before = safety.tree_manifest(str(self.source))
        with patch.object(safety.shutil, "copytree", side_effect=OSError("copy failed")):
            with self.assertRaisesRegex(safety.SafetyError, "incomplete copy removed: copy failed"):
                self.run_operation()
        self.assertEqual(safety.tree_manifest(str(self.source)), before)
        self.assertIsNone(safety.read_state(str(self.home)))
        self.assertNotIn("host", self.events)
        self.assertFalse((self.home / ".rhim_markers/source-completed.json").exists())

    def test_host_failure_and_revalidation_failure_keep_original_source(self):
        self.legacy()
        before = safety.tree_manifest(str(self.source))
        self.failure = "host"
        with self.assertRaises(safety.SafetyError):
            self.run_operation()
        self.assertEqual(safety.tree_manifest(str(self.source)), before)
        self.assertIsNone(safety.read_state(str(self.home)))
        self.failure = None
        self.runtime_failure = True
        self.events.clear()
        with self.assertRaisesRegex(safety.SafetyError, "Python changed"):
            self.run_operation()
        self.assertEqual(safety.tree_manifest(str(self.source)), before)
        self.assertNotIn("activate", self.events)

    def test_part1_cannot_complete_if_venv_creation_did_not_persist(self):
        self.legacy()
        original = self.check_runtime
        def missing_after_host(*args):
            result = dict(original(*args))
            if self.events.count("runtime") > 1:
                result["create_venv"] = True
            return result
        with patch("runtime_preflight.check_runtime", side_effect=missing_after_host):
            with self.assertRaisesRegex(safety.SafetyError, "venv is still missing"):
                self.run_operation("part1")
        self.assertIsNone(safety.read_state(str(self.home)))
        self.assertFalse((self.home / ".rhim_markers/source-completed.json").exists())

    def test_partial_activation_retry_finalizes_without_rewinding_live_data(self):
        self.legacy()
        self.failure = "activate"
        with self.assertRaises(safety.SafetyError):
            self.run_operation()
        state = safety.read_state(str(self.home))
        backup = Path(state["backup"])
        self.assertEqual((self.server / "database.db").read_text(), "partial new data")
        self.failure = None
        self.events.clear()
        self.run_operation()
        self.assertEqual((self.server / "database.db").read_text(), "partial new data")
        self.assertEqual((backup / "source/src/server/database.db").read_text(), "database")
        self.assertEqual(len(list((self.home / "rhim-backups").iterdir())), 1)
        self.assertNotIn("prepare", self.events)
        self.assertNotIn("host", self.events)
        self.assertEqual(self.events.count("activate"), 1)
        self.assertEqual(len(list(backup.glob("previous-*"))), 1)


    def interrupt_switch(self, external=False):
        if external:
            self.put(self.home / "rh-data/database.db", "external before switch")
        else:
            self.legacy()
        rename = safety.os.rename
        def interrupted(source, destination):
            if str(destination) == str(self.source):
                raise KeyboardInterrupt("power loss")
            return rename(source, destination)
        # Simulate process death after the first rename, without the ordinary error rollback.
        with patch.object(safety.os, "rename", side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                self.run_operation()
        return safety.read_state(str(self.home))

    def test_interruption_between_moves_retains_copies_and_concrete_manual_steps(self):
        state = self.interrupt_switch()
        self.assertEqual(state["phase"], "switching")
        self.assertTrue(Path(state["previous"]).is_dir())
        self.assertTrue(Path(state["prepared"]).is_dir())
        self.events.clear()
        with self.assertRaisesRegex(safety.SafetyError, "Stop all RH writers"):
            self.run_operation()
        self.assertNotIn("host", self.events)
        self.assertNotIn("prepare", self.events)
        self.assertEqual((Path(state["previous"]) / "src/server/database.db").read_text(), "database")

    def test_switching_with_changed_external_data_preserves_it_and_identifies_recovery_paths(self):
        state = self.interrupt_switch(external=True)
        external = self.home / "rh-data/database.db"
        external.write_text("newer external data")
        with self.assertRaises(safety.SafetyError) as raised:
            self.run_operation()
        for path in (state["backup"], state["prepared"], state["previous"], str(external.parent), safety.state_path(str(self.home))):
            self.assertIn(path, str(raised.exception))
        self.assertEqual(external.read_text(), "newer external data")

    def test_other_target_fresh_restart_config_and_cleanup_cannot_bypass_recovery(self):
        self.legacy()
        self.failure = "activate"
        with self.assertRaises(safety.SafetyError):
            self.run_operation()
        for stage, target in (("part1", "v4.5.0"), ("part2", "v4.5.0"), ("update", "main")):
            with self.subTest(stage=stage, target=target), self.assertRaisesRegex(safety.SafetyError, "Unfinished"):
                self.run_operation(stage, target)
        with self.assertRaisesRegex(safety.SafetyError, "pending"):
            safety.write_config(str(self.home), {})
        with self.assertRaisesRegex(safety.SafetyError, "pending"):
            safety.cleanup_old(str(self.home))

    def test_changed_data_after_host_failure_gets_new_backup_on_retry(self):
        for external in (False, True):
            with self.subTest(external=external):
                data = self.home / "rh-data" if external else self.server
                self.put(data / "config.json", '{}')
                self.put(data / "database.db", "before host")
                self.failure = "host"
                with self.assertRaises(safety.SafetyError):
                    self.run_operation()
                self.assertIsNone(safety.read_state(str(self.home)))
                old_backups = set((self.home / "rhim-backups").iterdir())
                self.put(data / "database.db", "races after reboot")
                self.failure = None
                self.run_operation()
                self.assertEqual((data / "database.db").read_text(), "races after reboot")
                new_backup, = set((self.home / "rhim-backups").iterdir()) - old_backups
                self.assertEqual((new_backup / "data/database.db").read_text(), "races after reboot")
                self.assertTrue(any((path / "data/database.db").read_text() == "before host" for path in old_backups))

    def test_unknown_fifo_can_be_removed_from_live_then_retried_without_state_edits(self):
        self.legacy()
        fifo = self.server / "unknown-stream"
        os.mkfifo(str(fifo))
        with self.assertRaisesRegex(safety.SafetyError, "Unknown FIFO"):
            self.run_operation()
        self.assertIsNone(safety.read_state(str(self.home)))
        old_backup, = (self.home / "rhim-backups").iterdir()
        fifo.unlink()
        self.put(self.server / "database.db", "new races")
        self.run_operation()
        self.assertEqual((self.server / "database.db").read_text(), "new races")
        self.assertTrue(stat.S_ISFIFO((old_backup / "data/unknown-stream").lstat().st_mode))

    def test_review_without_completion_receipt_lists_retained_paths(self):
        safety.cleanup_old(str(self.home))
        backup = self.backup()
        safety.cleanup_old(str(self.home))
        self.assertIn(str(backup), self.output.getvalue())
        self.assertTrue(backup.exists())

    def test_activated_identity_change_blocks_finalization_without_effects(self):
        self.legacy()
        self.failure = "activate"
        with self.assertRaises(safety.SafetyError):
            self.run_operation()
        self.put(self.server / "server.py", "unrecognized program")
        self.events.clear()
        with self.assertRaisesRegex(safety.SafetyError, "identity changed"):
            self.run_operation()
        self.assertEqual(self.events, [])

    def test_tampered_backup_is_refused_before_service_stop(self):
        self.legacy()
        self.failure = "activate"
        with self.assertRaises(safety.SafetyError):
            self.run_operation()
        state = safety.read_state(str(self.home))
        self.put(Path(state["backup"]) / "source/src/server/database.db", "damaged")
        self.events.clear()
        with self.assertRaisesRegex(safety.SafetyError, "verification failed"):
            self.run_operation()
        self.assertNotIn("stop", self.events)


class ForwardingTests(unittest.TestCase):
    def test_repeated_activation_adds_each_rule_once_and_propagates_errors(self):
        script = (ROOT / "scripts/iptables_conf.sh").read_text()
        function = script[script.index("ensure_forwarding_rule() {"):script.index("\nensure_forwarding_rule 80")]
        with tempfile.TemporaryDirectory() as directory:
            fixture = r'''sudo() {
  if [ "$2" = "-C" ]; then
    [ "${QUERY_ERROR:-0}" = 0 ] || return "$QUERY_ERROR"
    grep -qxF -- "${*:3}" "$RULES" && return 0
    return 1
  fi
  [ "${ADD_ERROR:-0}" = 0 ] || return "$ADD_ERROR"
  echo "${*:3}" >> "$RULES"
}
'''
            environment = dict(os.environ, RULES=str(Path(directory) / "rules"))
            Path(environment["RULES"]).touch()
            calls = "\nensure_forwarding_rule 80 5000 || exit 1\nensure_forwarding_rule 8080 80 || exit 1\n"
            for attempt in range(2):
                result = subprocess.run(["bash", "--noprofile", "--norc", "-c", function + "\n" + fixture + calls],
                                        env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.assertEqual(result.returncode, 0, result.stderr)
            before = Path(environment["RULES"]).read_text()
            self.assertEqual(len(before.splitlines()), 2)
            for failure in ({"QUERY_ERROR": "2"}, {"ADD_ERROR": "1"}):
                Path(environment["RULES"]).write_text("")
                result = subprocess.run(["bash", "--noprofile", "--norc", "-c", function + "\n" + fixture + calls],
                                        env=dict(environment, **failure), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(Path(environment["RULES"]).read_text(), "")


class LockTests(FilesystemCase):
    def child(self, code, pass_fds=(), env=None):
        return subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, " + repr(str(ROOT)) + "); import source_safety as s; " + code],
                              pass_fds=pass_fds, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, timeout=10)

    def test_child_reuses_validated_descriptor_and_simultaneous_attempt_refused(self):
        with safety.operation_lock(str(self.home)) as fd:
            result = self.child("s.inherited_lock(" + repr(str(self.home)) + ")", pass_fds=(fd,))
            self.assertEqual(result.returncode, 0, result.stderr)
            env = dict(os.environ)
            env.pop("RHIM_LOCK_FD")
            result = self.child("s.operation_lock(" + repr(str(self.home)) + ").__enter__()", env=env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Another RHIM", result.stderr)
        with safety.operation_lock(str(self.home)):
            pass

    def test_env_flag_or_unlocked_wrong_descriptor_cannot_bypass_lock(self):
        with patch.dict(os.environ, {"RHIM_OP_LOCKED": "1", "RHIM_LOCK_FD": "99999"}):
            with self.assertRaisesRegex(safety.SafetyError, "Invalid inherited"):
                with safety.operation_lock(str(self.home)):
                    self.fail("invalid descriptor accepted")
        wrong = os.open(str(self.home / "unrelated"), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            with patch.dict(os.environ, {"RHIM_LOCK_FD": str(wrong)}):
                with self.assertRaisesRegex(safety.SafetyError, "does not name"):
                    safety.inherited_lock(str(self.home))
        finally:
            os.close(wrong)

    def test_unlocked_descriptor_for_correct_file_is_not_acquired_by_validation(self):
        fd = safety.lock_file(str(self.home))
        try:
            with patch.dict(os.environ, {"RHIM_LOCK_FD": str(fd)}):
                with self.assertRaisesRegex(safety.SafetyError, "does not hold"):
                    safety.inherited_lock(str(self.home))
            other = safety.lock_file(str(self.home))
            try:
                fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                os.close(other)
        finally:
            os.close(fd)

    def test_another_holders_lock_does_not_validate_an_unlocked_descriptor(self):
        with safety.operation_lock(str(self.home)):
            fd = safety.lock_file(str(self.home))
            try:
                with patch.dict(os.environ, {"RHIM_LOCK_FD": str(fd)}):
                    with self.assertRaisesRegex(safety.SafetyError, "Invalid inherited"):
                        safety.inherited_lock(str(self.home))
            finally:
                os.close(fd)

    def test_failure_releases_lock(self):
        with self.assertRaises(RuntimeError):
            with safety.operation_lock(str(self.home)):
                raise RuntimeError("interrupted")
        self.assertNotIn("RHIM_LOCK_FD", os.environ)
        with safety.operation_lock(str(self.home)):
            pass

    def test_killed_process_releases_kernel_lock(self):
        env = dict(os.environ)
        env.pop("RHIM_LOCK_FD", None)
        code = ("import sys; sys.path.insert(0, " + repr(str(ROOT)) + "); import source_safety as s; "
                "context = s.operation_lock(" + repr(str(self.home)) + "); context.__enter__(); "
                "print('locked', flush=True); sys.stdin.read()")
        process = subprocess.Popen([sys.executable, "-c", code], env=env, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertTrue(select.select([process.stdout], [], [], 10)[0], "child did not acquire lock")
            self.assertEqual(process.stdout.readline().strip(), "locked")
            with self.assertRaisesRegex(safety.SafetyError, "Another RHIM"):
                with safety.operation_lock(str(self.home)):
                    self.fail("simultaneous operation accepted")
            process.kill()
            process.wait(timeout=10)
            with safety.operation_lock(str(self.home)):
                pass
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=10)


class StopTests(FilesystemCase):
    def test_stop_failure_or_nonzero_pid_refuses_copy(self):
        data = self.resolve()
        with patch.object(safety, "assert_no_writers") as writers:
            with patch.object(safety, "command", side_effect=safety.SafetyError("stop failed")):
                with self.assertRaises(safety.SafetyError):
                    safety.stop_and_confirm(True, str(self.source), data)
            writers.assert_not_called()
            for stdout in ("ActiveState=active\nMainPID=0", "ActiveState=inactive\nMainPID=12", ""):
                with patch.object(safety, "command", return_value=SimpleNamespace(stdout=stdout)):
                    with self.assertRaisesRegex(safety.SafetyError, "did not stop"):
                        safety.stop_and_confirm(True, str(self.source), data)
            writers.assert_not_called()

    def test_inactive_zero_pid_and_fresh_missing_service_use_privileged_writer_check(self):
        data = self.resolve()
        with patch.object(safety, "command", return_value=SimpleNamespace(stdout="ActiveState=inactive\nMainPID=0")) as command:
            safety.stop_and_confirm(True, str(self.source), data)
            self.assertEqual(command.call_count, 3)
            self.assertEqual(command.call_args.args[0][-3:], ["check-writers", str(self.source), data["real"]])
            self.assertEqual(command.call_args.args[0][:2], ["sudo", "/usr/bin/python3"])
            safety.stop_and_confirm(False, str(self.source), data)
            self.assertEqual(command.call_count, 4)

    def test_manual_writer_in_proc_fixture_is_refused(self):
        proc = self.home / "proc"
        self.put(proc / "123/status", "Uid:\t{}\t{}\t{}\t{}\n".format(*([os.getuid()] * 4)))
        self.put(proc / "123/cmdline", "python3\0server.py\0")
        (proc / "123/fd").mkdir()
        (proc / "123/cwd").symlink_to(self.server, target_is_directory=True)
        with self.assertRaisesRegex(safety.SafetyError, "manual.*123"):
            safety.assert_no_writers(str(self.source), self.resolve(), str(proc))

    def test_open_data_file_in_proc_fixture_is_refused(self):
        proc = self.home / "proc"
        self.put(proc / "123/status", "Uid:\t{}\n".format(os.getuid()))
        self.put(proc / "123/cmdline", "plugin-writer")
        (proc / "123/fd").mkdir()
        (proc / "123/fd/4").symlink_to(self.server / "database.db")
        with self.assertRaisesRegex(safety.SafetyError, "open RH"):
            safety.assert_no_writers(str(self.source), self.legacy(), str(proc))
