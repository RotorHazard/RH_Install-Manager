"""Narrow stdlib-only runtime check, also runnable on RHIM's minimum Python."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def main():
    paths = sorted(ROOT.glob('*.py')) + sorted((ROOT / 'NuclearHazard').glob('*.py'))
    for path in paths:
        compile(path.read_text(encoding='utf-8'), str(path), 'exec')
    print('Compiled {} runtime files'.format(len(paths)), flush=True)
    suite = unittest.TestSuite()
    for pattern in ('test_config_writes.py', 'test_banner.py'):
        suite.addTests(unittest.defaultTestLoader.discover(str(ROOT / 'tests'), pattern=pattern))
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
