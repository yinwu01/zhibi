import errno
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from zhibi import guest_ipv6


class GuestIPv6Tests(unittest.TestCase):
    def inspect(self, values, cmdline='', addresses=''):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conf = root / 'proc/sys/net/ipv6/conf'
            conf.mkdir(parents=True)
            for name, value in values.items():
                (conf / name).mkdir()
                (conf / name / 'disable_ipv6').write_text(str(value))
            (root / 'proc/cmdline').write_text(cmdline)
            (root / 'proc/net').mkdir()
            (root / 'proc/net/if_inet6').write_text(addresses)
            with patch.object(guest_ipv6, 'Path', side_effect=lambda p: root / p.lstrip('/')), \
                    patch.object(guest_ipv6.socket, 'socket', side_effect=OSError(errno.EAFNOSUPPORT, 'disabled')):
                return guest_ipv6.inspect()

    def test_all_flag_does_not_hide_enabled_interface(self):
        result = self.inspect({'all': 1, 'default': 1, 'lo': 1, 'eth0': 0})
        self.assertEqual(result['state'], 'fail')

    def test_boot_disabled_without_ipv6_module_passes(self):
        self.assertEqual(self.inspect({}, 'quiet ipv6.disable=1')['state'], 'ok')
        self.assertEqual(self.inspect({})['state'], 'fail')

    def test_disabled_interfaces_must_also_have_no_addresses(self):
        values = {'all': 1, 'default': 1, 'lo': 1, 'eth0': 1}
        self.assertEqual(self.inspect(values)['state'], 'ok')
        self.assertEqual(self.inspect(values, addresses='fe80::1')['state'], 'fail')
