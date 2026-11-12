import json
import os
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from zhibi import pvm_backend as pvm, project
from zhibi.models import InputError


class AuditTests(unittest.TestCase):
    def test_zero_exit_with_warnings_is_not_pass(self):
        result = pvm.parse_audit("vm=warn: stopped\nroute=ok: via my-exit (per-vm)\n", "my-exit")
        self.assertFalse(result["protocol_checks_passed"])
        self.assertFalse(result["complete"])
        self.assertEqual(result["checks"]["udp"]["state"], "not_measured")

    def test_wrong_exit_and_prefix_match_rejected(self):
        for route in ("direct", "jp-other"):
            result = pvm.parse_audit("route=ok: via " + route + " (per-vm)\n", "jp")
            self.assertEqual(result["checks"]["route"]["state"], "fail")

    def test_protocol_success_still_needs_browser_and_failure_test(self):
        text = "\n".join(key + "=ok: " + ("via jp (per-vm)" if key == "route" else "checked") for key in pvm.REQUIRED)
        result = pvm.parse_audit(text, "jp")
        self.assertTrue(result["protocol_checks_passed"])
        self.assertFalse(result["complete"])

    def test_duplicate_observation_refused(self):
        with self.assertRaises(InputError):
            pvm.parse_audit("tcp=fail: no\ntcp=ok: yes\n", "jp")

    def test_per_vm_route_overrides_cluster_default(self):
        text = "INDEX TYPE PATTERN ACTION VIA\n0 cidr 10.0.0.0/8 direct\n vm work proxy jp\n cluster-default * route us\n"
        self.assertEqual(pvm.effective_route(text, "work"), "jp")
        self.assertEqual(pvm.effective_route(text, "other"), "us")
        self.assertIsNone(pvm.effective_route("unrecognized", "work"))


@unittest.skipUnless(os.name == "posix", "PVM adapter supports macOS/Linux")
class BackendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="zpv-", dir="/tmp")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.checkout = self.root / "project 中文"
        self.checkout.mkdir()
        self.binary = self.root / "pvm"
        self.binary.write_text("#!/bin/sh\nprintf 'v1.1.6\\n'\n")
        self.binary.chmod(0o700)
        self.args = SimpleNamespace(workspace=str(self.root / "workspace"), project=str(self.checkout),
            pvm_binary=str(self.binary), pvm_home=str(self.root / "state"), name="work", exit="jp",
            image="ubuntu:24.04", user="dev", cpus=2, memory=2048, disk=12,
            timezone="Asia/Tokyo", locale="en_US.UTF-8")

    def prepare(self):
        result = pvm.prepare(self.args)
        return pvm.load(result["workspace"])

    def test_prepare_is_private_and_does_not_create_vm(self):
        folder, data = self.prepare()
        self.assertEqual(data["phase"], "prepared")
        self.assertFalse((self.root / "state").exists())
        self.assertEqual((folder / "vm.private.json").stat().st_mode & 0o777, 0o600)
        steps = pvm.provision_steps(data)
        self.assertIn("--no-start", steps[0])
        self.assertEqual([s[0] for s in steps], ["create", "start", "route", "ssh", "mount"])
        self.assertEqual(steps[2][-1], "jp")

    def test_unsupported_version_creates_no_workspace(self):
        self.binary.write_text("#!/bin/sh\necho v0\n")
        with self.assertRaises(InputError):
            self.prepare()
        self.assertFalse(Path(self.args.workspace).exists())

    def test_existing_instance_never_modified(self):
        folder, data = self.prepare()
        def call(data, *args, **kwargs):
            return SimpleNamespace(returncode=0, stdout="v1.1.6\n" if args == ("version",) else "work image user running\n")
        with patch.object(pvm, "call", side_effect=call), patch("subprocess.run", side_effect=AssertionError("mutation")):
            with self.assertRaises(InputError):
                pvm.provision(folder, data, True)
        self.assertEqual(pvm.load(folder)[1]["phase"], "prepared")

    def test_failed_step_persists_and_never_auto_replays(self):
        folder, data = self.prepare()
        with patch.object(pvm, "check_version"), patch.object(pvm, "call", return_value=SimpleNamespace(returncode=0, stdout="NAME IMAGE\n")), \
                patch("subprocess.run", return_value=SimpleNamespace(returncode=7)) as execute:
            with self.assertRaises(InputError):
                pvm.provision(folder, data, True)
            self.assertEqual(execute.call_count, 1)
        failed = pvm.load(folder)[1]
        self.assertEqual(failed["phase"], "interrupted")
        self.assertEqual(failed["current_step"], "create")
        with patch.object(pvm, "check_version"), patch("subprocess.run", side_effect=AssertionError("replayed")):
            with self.assertRaises(InputError):
                pvm.provision(folder, failed, True)

    def test_application_quotes_shell_once_and_preserves_shared_cwd(self):
        _, data = self.prepare()
        data["guest_workdir"] = str(self.checkout)
        text = "cd -- " + shlex.quote(str(self.checkout)) + " && printf '%s' 'a b;$(false)'"
        argv = pvm.guest_command(data, text)
        # Same join performed by upstream CmdSSH; execute its result locally.
        done = subprocess.run(["sh", "-lc", " ".join(argv[4:])], capture_output=True)
        self.assertEqual(done.stdout, b"a b;$(false)")
        self.assertEqual(done.returncode, 0)

    def test_route_drift_blocks_application(self):
        folder, data = self.prepare()
        data["phase"] = "ready"
        pvm.write_state(folder, data)
        with patch.object(pvm, "check_version"), patch.object(pvm, "call", return_value=SimpleNamespace(returncode=0, stdout="cluster-default * route direct\n")), \
                patch.object(pvm, "foreground", side_effect=AssertionError("launched")):
            with self.assertRaises(InputError):
                pvm.run_application(folder, "true", False, True)

    def test_project_binding_uses_same_entrypoint(self):
        folder, data = self.prepare()
        script = self.root / "start.sh"
        script.write_text("exec app\n"); script.chmod(0o600)
        args = SimpleNamespace(action="bind", backend="pvm", vm_workspace=str(folder), project=str(self.checkout),
            state_dir=str(self.root / "bindings"), local_port=10818, command_file=str(script), resume_file=None,
            interactive=False, apply=False)
        self.assertEqual(project.run(args)["backend"], "pvm")
        args.action = "start"
        result = project.run(args)
        self.assertEqual(result["name"], "work")
        self.assertFalse(result["applied"])

    def test_desktop_secret_not_returned(self):
        folder, data = self.prepare()
        data["phase"] = "ready"; pvm.write_state(folder, data)
        with patch.object(pvm, "ipv6_policy"), patch.object(pvm, "check_version"), patch.object(pvm, "call", return_value=SimpleNamespace(returncode=0, stdout="desktop ready: http://localhost/#password=secret")):
            result = pvm.dispatch(SimpleNamespace(action="desktop", workspace=str(folder), apply=True))
        self.assertNotIn("secret", json.dumps(result))

    def test_reconcile_reads_live_state_before_accepting_recovery(self):
        folder, data = self.prepare()
        data["phase"] = "interrupted"; pvm.write_state(folder, data)
        def call(data, *parts, **kwargs):
            text = {("ls",): "NAME IMAGE ROLE STATUS IP CPU MEM USER UPTIME\nwork ubuntu:24.04 user running 100.99.1.10 2 2G dev 1m\n",
                    ("mount", "ls", "work"): "HOST GUEST PROFILE ACCESS\n" + data["project"] + " /workspace coherent rw\n",
                    ("route", "ls"): "vm work proxy jp\ncluster-default * route direct\n"}[parts]
            return SimpleNamespace(returncode=0, stdout=text)
        with patch.object(pvm, "ipv6_policy"), patch.object(pvm, "check_version"), patch.object(pvm, "call", side_effect=call), \
                patch("subprocess.run", return_value=SimpleNamespace(returncode=0)):
            result = pvm.reconcile(folder, data, True)
        self.assertTrue(result["reconciled"])
        self.assertEqual(pvm.load(folder)[1]["phase"], "ready")

    def test_reconcile_rejects_wrong_vm_user(self):
        folder, data = self.prepare()
        with patch.object(pvm, "check_version"), patch.object(pvm, "call", return_value=SimpleNamespace(returncode=0,
                stdout="work ubuntu:24.04 user running 100.99.1.10 2 2G another 1m\n")):
            with self.assertRaises(InputError):
                pvm.reconcile(folder, data, True)
        self.assertEqual(pvm.load(folder)[1]["phase"], "prepared")

    def test_ipv6_failure_blocks_application_and_desktop(self):
        folder, data = self.prepare()
        data['phase'] = 'ready'; pvm.write_state(folder, data)
        with patch.object(pvm, 'check_version'), patch.object(pvm, 'call', return_value=SimpleNamespace(returncode=0, stdout='vm work proxy jp\n')), \
                patch.object(pvm, 'ipv6_policy', side_effect=InputError('IPv6 enabled')), \
                patch.object(pvm, 'foreground', side_effect=AssertionError('application launched')):
            with self.assertRaises(InputError):
                pvm.run_application(folder, 'true', False, True)
            with self.assertRaises(InputError):
                pvm.dispatch(SimpleNamespace(action='desktop', workspace=str(folder), apply=True))

    def test_ipv6_readback_failure_is_not_success(self):
        _, data = self.prepare()
        for code, output in [(1, '{"state":"ok"}'), (0, '{"state":"fail"}'), (0, '')]:
            with patch.object(pvm, 'call', return_value=SimpleNamespace(returncode=code, stdout=output)):
                with self.assertRaises(InputError):
                    pvm.ipv6_policy(data)
