import json
import tempfile
import unittest
import subprocess
import os
import socket
import hashlib
from pathlib import Path
from unittest.mock import patch
from zhibi.sandbox import prepare, command, install_entry, proxy_files


class SandboxTests(unittest.TestCase):
    @unittest.skipUnless(hasattr(os, 'getuid') and hasattr(socket, 'AF_UNIX'), 'POSIX Unix socket')
    def test_proxy_requires_pinned_binary_and_private_owned_socket(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            binary = root / 'graftcp'
            binary.write_bytes(b'verified-binary'); binary.chmod(0o700)
            digest = hashlib.sha256(binary.read_bytes()).hexdigest()
            endpoint = root / 'proxy.sock'
            with socket.socket(socket.AF_UNIX) as sock:
                sock.bind(str(endpoint))
                self.assertEqual(proxy_files(str(binary), digest, str(endpoint)), (str(binary), str(endpoint)))
                prepare(root / 'profile', root, network='proxy', graftcp=str(binary),
                        graftcp_sha256=digest, proxy_socket=str(endpoint))
                binary.write_bytes(b'replaced-binary')
                with self.assertRaises(ValueError):
                    proxy_files(str(binary), digest, str(endpoint))
                binary.write_bytes(b'verified-binary')
                root.chmod(0o755)
                try:
                    with self.assertRaises(ValueError):
                        proxy_files(str(binary), digest, str(endpoint))
                finally:
                    root.chmod(0o700)

    @unittest.skipIf(os.name == 'nt', 'POSIX command entry')
    def test_entry_forwards_literal_arguments_and_runner_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / 'space and quote\'s'
            root.mkdir()
            runner = root / 'run.py'
            runner.write_text('import json, sys\nprint(json.dumps(sys.argv[1:]))\nsys.exit(17)\n')
            result = install_entry(root, 'demo', '/opt/app/bin/demo')
            proc = subprocess.run([result['entry'], 'a b', '$(touch never)', "a'b"], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 17)
            self.assertEqual(json.loads(proc.stdout), ['--', '/opt/app/bin/demo', 'a b', '$(touch never)', "a'b"])
            with self.assertRaises(FileExistsError):
                install_entry(root, 'demo', '/opt/app/bin/demo')
            runner.unlink()
            self.assertNotEqual(subprocess.run([result['entry']], capture_output=True).returncode, 0)

    def test_entry_refuses_ambiguous_program_or_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            for name, program in [('demo', 'demo'), ('../demo', '/bin/true'), ('demo', '/opt/app/../../bin/true')]:
                with self.assertRaises(ValueError):
                    install_entry(root, name, program)

    def test_export_has_private_home_and_preserves_program_arguments(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            work = root / 'work'; work.mkdir()
            out = root / 'profile'
            prepare(out, work)
            with patch('sys.platform', 'linux'), patch('shutil.which', return_value='/usr/bin/bwrap'):
                argv = command(out, ['/bin/echo', 'a b', '$(do-not-execute)'])
            self.assertEqual(argv[-4:], ['--', '/bin/echo', 'a b', '$(do-not-execute)'])
            self.assertIn('--clearenv', argv)
            self.assertIn('--unshare-all', argv)
            self.assertNotIn('--share-net', argv)
            self.assertNotIn(str(Path.home()), argv)
            self.assertEqual((out / 'profile.json').stat().st_mode & 0o777, 0o600)
            compile((out / 'run.py').read_text(), 'run.py', 'exec')

    def test_missing_bwrap_refuses_direct_fallback(self):
        with patch('sys.platform', 'linux'), patch('shutil.which', return_value=None):
            with self.assertRaises(ValueError):
                command('/tmp', ['/bin/true'])

    def test_existing_workspace_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            with self.assertRaises(FileExistsError):
                prepare(root, root)

    def test_host_network_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            prepare(root / 'profile', root, network='host')
            with patch('sys.platform', 'linux'), patch('shutil.which', return_value='/usr/bin/bwrap'):
                self.assertIn('--share-net', command(root / 'profile', ['/bin/true']))
