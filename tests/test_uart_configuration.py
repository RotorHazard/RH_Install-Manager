"""Run only the UART function, with host commands restricted to temporary files."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class UARTConfigurationTests(unittest.TestCase):
    def test_modern_legacy_and_failed_configuration(self):
        script = (ROOT / 'scripts/sys_conf.sh').read_text()
        function = 'uart_enabling() {' + script.split('uart_enabling() {', 1)[1].split('\nuart_error() {', 1)[0]
        harness = r'''
boot_directory_check() { printf '%s\n' "$WORK"; }
sleep() { return 0; }
sudo() {
  if [ "$1" = raspi-config ]; then
    printf '%s\n' "$3" >> "$WORK/calls"
    case "$3" in
      do_serial_hw) return "$HARDWARE_STATUS" ;;
      do_serial_cons) return "$CONSOLE_STATUS" ;;
      do_serial) [ "$4" = 2 ] || return 98; return "$LEGACY_STATUS" ;;
      *) return 98 ;;
    esac
  fi
  case "$1" in
    sed)
      shift
      if [ "$SED_STYLE" = bsd ]; then
        command sed -i '' "${@:2}"
      else
        command sed "$@"
      fi ;;
    cp|tee) "$@" ;;
    *) return 99 ;;
  esac
}
'''
        cases = [
            ('modern', 0, 0, 0, True, ['do_serial_hw', 'do_serial_cons']),
            ('legacy', 127, 0, 0, True, ['do_serial_hw', 'do_serial']),
            ('hardware failure', 1, 0, 0, False, ['do_serial_hw']),
            ('console failure', 0, 1, 0, False, ['do_serial_hw', 'do_serial_cons']),
            ('legacy failure', 127, 0, 1, False, ['do_serial_hw', 'do_serial']),
        ]
        bash = shutil.which('bash', path=os.defpath)
        self.assertIsNotNone(bash)
        for name, hardware, console, legacy, success, calls in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                boot = Path(directory)
                (boot / 'config.txt').write_text('[all]\n')
                (boot / 'cmdline.txt').write_text('console=serial0,115200 root=test\n')
                result = subprocess.run(
                    [bash, '--noprofile', '--norc'], input=harness + function + '\nuart_enabling\n',
                    cwd=directory, env={'PATH': os.defpath, 'LC_ALL': 'C', 'WORK': directory,
                                        'SED_STYLE': 'bsd' if os.uname().sysname == 'Darwin' else 'gnu',
                                        'HARDWARE_STATUS': str(hardware), 'CONSOLE_STATUS': str(console),
                                        'LEGACY_STATUS': str(legacy)},
                    capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode == 0, success, result.stderr)
                self.assertEqual((boot / 'calls').read_text().splitlines(), calls)
                self.assertEqual('enable_uart=1' in (boot / 'config.txt').read_text(), success)
                self.assertEqual('UART ENABLED' in result.stdout, success)
                if success:
                    self.assertNotIn('console=serial0,115200', (boot / 'cmdline.txt').read_text())
