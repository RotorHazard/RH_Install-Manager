"""Banner queries never execute host commands in these fixtures."""
import contextlib
import io
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from test_version_selection import load_function


class BannerTests(unittest.TestCase):
    def banner(self, addresses=None, error=None):
        query = Mock(return_value=addresses or b'', side_effect=error)
        host = load_function('modules.py', 'get_host_info',
                             socket=SimpleNamespace(gethostname=lambda: 'test-pi'),
                             subprocess=SimpleNamespace(check_output=query))
        colors = SimpleNamespace(**dict.fromkeys(
            ('PROMPT', 'ENDC', 'BOLD_S', 'ENDC_S', 'YELLOW_S', 'BOLD', 'ORANGE'), ''))
        logo = load_function('modules.py', 'logo_top', get_host_info=host, Bcolors=colors)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            logo(False)
        query.assert_called_once_with(['hostname', '-I'])
        return output.getvalue()

    def test_three_addresses_share_one_query(self):
        output = self.banner(b'10.0.0.1 10.0.0.2 10.0.0.3\n')
        self.assertIn('Hostname: test-pi', output)
        for ip in ('10.0.0.1', '10.0.0.2', '10.0.0.3'):
            self.assertIn('IP: ' + ip, output)

    def test_missing_addresses_do_not_break_banner(self):
        for addresses in (b'', b'10.0.0.1\n'):
            with self.subTest(addresses=addresses):
                output = self.banner(addresses)
                self.assertEqual(output.count('IP:'), 1)

    def test_command_failure_has_safe_fallback(self):
        output = self.banner(error=OSError('hostname unavailable'))
        self.assertIn('IP: no IP info', output)
        self.assertIn('Hostname: no hostname info', output)
