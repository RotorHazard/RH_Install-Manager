import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
SHELL_SHEBANG = re.compile(rb"^#!\s*(?:/\S*/(?:ba)?sh|/usr/bin/env\s+(?:ba)?sh)(?:\s|$)")


class ShellSyntaxTests(unittest.TestCase):
    def test_tracked_shell_scripts(self):
        tracked = subprocess.run(
            ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
        ).stdout.split(b"\0")
        scripts = []
        for entry in filter(None, tracked):
            path = ROOT / os.fsdecode(entry)
            with path.open("rb") as source:
                first_line = source.readline()
            if path.suffix == ".sh" or SHELL_SHEBANG.match(first_line):
                scripts.append(path)
        self.assertTrue(scripts, "No tracked shell scripts found")
        bash = shutil.which("bash", path=os.defpath)
        self.assertIsNotNone(bash, "Bash is required for syntax checks")
        for path in scripts:
            with self.subTest(script=str(path.relative_to(ROOT))):
                result = subprocess.run(
                    [bash, "--noprofile", "--norc", "-n", "--", str(path)],
                    cwd=ROOT, env={"PATH": os.defpath, "LC_ALL": "C"},
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
        print(f"Bash syntax checked {len(scripts)} tracked shell scripts")
