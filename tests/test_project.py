import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from zhibi import project
from zhibi.models import InputError


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.checkout = self.root / "项目 with spaces"
        self.checkout.mkdir()
        self.script = self.root / "start.sh"
        self.script.write_text("exec app 'private argument'\n")
        self.script.chmod(0o600)
        self.args = SimpleNamespace(action="bind", project=str(self.checkout),
                                    state_dir=str(self.root / "state"), host="example.org",
                                    user="worker", port=22, identity=None,
                                    workdir="/srv/project's files", command_file=str(self.script),
                                    resume_file=None, local_port=10818, interactive=False,
                                    apply=False, live=False, network=False)

    def bind(self):
        project.run(self.args)
        return project.location(self.args)[1]

    def test_binding_stays_outside_checkout_and_is_private(self):
        folder = self.bind()
        self.assertEqual(list(self.checkout.iterdir()), [])
        self.assertEqual(folder.stat().st_mode & 0o777, 0o700)
        self.assertEqual((folder / "binding.private.json").stat().st_mode & 0o777, 0o600)
        self.args.action = "status"
        result = project.run(self.args)
        self.assertFalse(result["live_checked"])
        self.assertNotIn("private argument", json.dumps(result))

    def test_saved_command_survives_original_removal_and_new_session(self):
        self.bind()
        self.script.unlink()
        self.args.action = "start"
        self.args.apply = True
        with patch("zhibi.remote.execute", return_value={"state": "ok"}) as check, \
                patch("zhibi.connect.foreground", return_value=19) as process:
            result = project.run(self.args)
        self.assertEqual(result["exit_status"], 19)
        self.assertIn("'\"'\"'", check.call_args.args[1])
        command = process.call_args.args[0]
        self.assertIn("private argument", command[-1])
        self.assertIn("127.0.0.1:10818", command)

    def test_dry_run_no_network_or_execution(self):
        self.bind()
        self.args.action = "start"
        with patch("zhibi.remote.execute", side_effect=AssertionError("network")), \
                patch("zhibi.connect.foreground", side_effect=AssertionError("process")):
            self.assertFalse(project.run(self.args)["applied"])

    def test_unavailable_directory_never_launches(self):
        self.bind()
        self.args.action, self.args.apply = "start", True
        with patch("zhibi.remote.execute", return_value={"state": "error"}), \
                patch("zhibi.connect.foreground", side_effect=AssertionError("process")):
            with self.assertRaises(InputError):
                project.run(self.args)

    def test_no_implicit_resume(self):
        self.bind()
        self.args.action = "resume"
        with self.assertRaises(InputError):
            project.run(self.args)

    def test_resume_uses_explicit_application_command(self):
        resume = self.root / "resume.sh"
        resume.write_text("exec app --continue\n")
        resume.chmod(0o600)
        self.args.resume_file = str(resume)
        self.bind()
        self.args.action, self.args.apply = "resume", True
        with patch("zhibi.remote.execute", return_value={"state": "ok"}), \
                patch("zhibi.connect.foreground", return_value=0) as process:
            project.run(self.args)
        self.assertIn("app --continue", process.call_args.args[0][-1])

    def test_tampered_script_or_symlink_refused(self):
        folder = self.bind()
        self.args.action = "start"
        script = folder / "start.sh"
        script.write_text("unexpected command")
        with self.assertRaises(InputError):
            project.run(self.args)
        script.unlink()
        script.symlink_to(self.script)
        with self.assertRaises((InputError, OSError)):
            project.run(self.args)

    def test_existing_binding_never_overwritten(self):
        folder = self.bind()
        original = (folder / "binding.private.json").read_bytes()
        with self.assertRaises(InputError):
            project.run(self.args)
        self.assertEqual((folder / "binding.private.json").read_bytes(), original)

    def test_unbind_only_removes_binding(self):
        self.bind()
        self.args.action = "unbind"
        self.assertFalse(project.run(self.args)["applied"])
        self.args.apply = True
        self.assertTrue(project.run(self.args)["remote_unchanged"])
        self.assertTrue(self.checkout.is_dir())
        self.assertTrue(self.script.exists())

    def test_unbind_refuses_unexpected_files(self):
        folder = self.bind()
        (folder / "keep.txt").write_text("keep")
        self.args.action, self.args.apply = "unbind", True
        with self.assertRaises(InputError):
            project.run(self.args)
        self.assertEqual((folder / "keep.txt").read_text(), "keep")

    @unittest.skipUnless(os.name == "posix", "POSIX permissions")
    def test_public_state_rejected(self):
        state = self.root / "state"
        state.mkdir(mode=0o755)
        with self.assertRaises(InputError):
            self.bind()
