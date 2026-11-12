"""Exercise actual guest transfer code with a local shell transport."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from zhibi.project_files import transfer
from zhibi.models import InputError


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.guest = self.root / "guest 中文's files"
        self.guest.mkdir()
        self.local = self.root / "picture.png"
        self.local.write_bytes(bytes(range(256)) * 1000)
        self.data = {"workdir": str(self.guest), "target": {"host": "example.org"}}
        self.args = SimpleNamespace(local=str(self.local), remote_file="图片 ' one.png",
                                    action="upload", apply=True)
        mock = patch("zhibi.remote.ssh_argv", side_effect=lambda item, script: ["sh", "-c", script])
        mock.start()
        self.addCleanup(mock.stop)

    def test_binary_upload_download_and_permissions(self):
        self.assertTrue(transfer(self.args, self.data)["applied"])
        remote = self.guest / self.args.remote_file
        self.assertEqual(remote.read_bytes(), self.local.read_bytes())
        self.assertEqual(remote.stat().st_mode & 0o777, 0o600)
        self.args.action = "download"
        self.args.local = str(self.root / "received.png")
        transfer(self.args, self.data)
        self.assertEqual(Path(self.args.local).read_bytes(), self.local.read_bytes())

    def test_upload_never_overwrites_existing_file(self):
        target = self.guest / self.args.remote_file
        target.write_text("original")
        with self.assertRaises(InputError):
            transfer(self.args, self.data)
        self.assertEqual(target.read_text(), "original")
        self.assertFalse(list(self.guest.glob(".zhibi-transfer-*")))

    def test_download_never_overwrites_existing_file(self):
        self.args.action = "download"
        original = self.local.read_bytes()
        with self.assertRaises(FileExistsError):
            transfer(self.args, self.data)
        self.assertEqual(self.local.read_bytes(), original)

    def test_symlink_escape_refused(self):
        (self.guest / "outside").symlink_to(self.root, target_is_directory=True)
        self.args.remote_file = "outside/escaped"
        with self.assertRaises(InputError):
            transfer(self.args, self.data)
        self.assertFalse((self.root / "escaped").exists())

    def test_download_symlink_refused_and_partial_removed(self):
        (self.guest / self.args.remote_file).symlink_to(self.local)
        self.args.action, self.args.local = "download", str(self.root / "received")
        with self.assertRaises(InputError):
            transfer(self.args, self.data)
        self.assertFalse(Path(self.args.local).exists())

    def test_parent_traversal_refused_before_network(self):
        self.args.remote_file = "../escaped"
        with patch("subprocess.run", side_effect=AssertionError("network")):
            with self.assertRaises(InputError):
                transfer(self.args, self.data)

    def test_dry_run_creates_no_files(self):
        self.args.apply = False
        with patch("subprocess.run", side_effect=AssertionError("network")):
            self.assertFalse(transfer(self.args, self.data)["applied"])
        self.assertEqual(list(self.guest.iterdir()), [])
