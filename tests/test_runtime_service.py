import hashlib
import json
import os
import socket
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from zhibi.runtime_service import export, load, rollback, target_path, write_private, remember_gateway, remove_stale_gateway


@unittest.skipUnless(hasattr(os, 'getuid'), 'POSIX user service exporter')
class RuntimeServiceTests(unittest.TestCase):
    def test_socket_cleanup_checks_receipt_and_live_listener(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            path = root / 'gateway.sock'; config = {'socket': str(path)}
            with socket.socket(socket.AF_UNIX) as endpoint:
                endpoint.bind(str(path)); endpoint.listen()
                with self.assertRaises(ValueError):
                    remove_stale_gateway(root, config)
                remember_gateway(root, config)
                with self.assertRaises(ValueError):
                    remove_stale_gateway(root, config)
                self.assertTrue(path.exists())
            remove_stale_gateway(root, config)
            self.assertFalse(path.exists())

    def bundle(self, root):
        profile = root / 'profile'; profile.mkdir(mode=0o700)
        (profile / 'profile.json').write_text(json.dumps({'network': 'proxy', 'proxy': {'socket': str(root / 'gateway.sock')}}))
        (profile / 'run.py').write_text('raise SystemExit(0)\n')
        with patch('sys.platform', 'linux'):
            return export(root / 'bundle', profile, 'zhibi-test', ['/bin/sleep', '60'])

    def test_standalone_export_without_install_or_credential_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            result = self.bundle(root)
            self.assertFalse(result['installed'])
            bundle = Path(result['directory'])
            self.assertEqual(set(p.name for p in bundle.iterdir()),
                             {'manage.py', 'gateway.py', 'service.json', 'zhibi-test.service'})
            self.assertEqual((bundle / 'service.json').stat().st_mode & 0o777, 0o600)
            for name in ('manage.py', 'gateway.py'):
                compile((bundle / name).read_text(), name, 'exec')

    def test_rollback_refuses_changed_unit_before_stopping_any_service(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'XDG_CONFIG_HOME': str(Path(tmp).resolve() / 'config')}):
            root = Path(tmp).resolve()
            bundle = Path(self.bundle(root)['directory']); config = load(bundle)
            target = target_path(config); target.parent.mkdir(parents=True)
            target.write_text('changed by another operation')
            write_private(bundle / 'receipt.json', {'target': str(target), 'name': config['name'], 'unit_sha256': config['unit_sha256']})
            with patch('zhibi.runtime_service.ctl') as ctl:
                with self.assertRaises(ValueError):
                    rollback(bundle, config)
                ctl.assert_not_called()
            self.assertEqual(target.read_text(), 'changed by another operation')
