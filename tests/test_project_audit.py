import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from zhibi import project_audit as audit


def observation(ip=None, execution="ok"):
    return {"execution": execution, "egress": {"state": "observed", "ip": ip} if ip else {"state": "error"}}


class OutageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.script = Path(self.tmp.name) / "control"
        self.script.write_text("true\n"); self.script.chmod(0o600)
        self.before = observation("203.0.113.1")

    def run_cycle(self, during, after=None):
        with patch.object(audit, "control", return_value=True), patch.object(audit, "measure", side_effect=[during, after or self.before]):
            return audit.outage({}, self.before, self.script, self.script)

    def test_live_probe_sees_network_fail_and_restore(self):
        self.assertEqual(self.run_cycle(observation())["state"], "ok")

    def test_lost_ssh_is_not_evidence_of_network_blocking(self):
        self.assertEqual(self.run_cycle(observation(execution="error"))["state"], "not_measured")

    def test_direct_fallback_or_unbroken_tunnel_fails(self):
        self.assertEqual(self.run_cycle(observation("203.0.113.2"))["state"], "fail")

    def test_restoration_must_use_original_exit(self):
        self.assertEqual(self.run_cycle(observation(), observation("203.0.113.3"))["reason"], "exit_changed_after_restoration")

    def test_restore_runs_even_if_measurement_raises(self):
        with patch.object(audit, "control", return_value=True) as control, \
                patch.object(audit, "measure", side_effect=[RuntimeError("failed"), self.before]):
            with self.assertRaises(RuntimeError):
                audit.outage({}, self.before, self.script, self.script)
        self.assertEqual(control.call_count, 2)

    def test_no_baseline_no_disconnection(self):
        with patch.object(audit, "control", side_effect=AssertionError("disconnected")):
            result = audit.outage({}, observation(), self.script, self.script)
        self.assertEqual(result["state"], "not_measured")

    def test_missing_browser_or_runner_never_passes(self):
        args = SimpleNamespace(network=True, expected_ip="203.0.113.1", browser=None,
            disconnect_file=None, reconnect_file=None, out=None)
        with patch.object(audit, "measure", return_value=self.before):
            result = audit.audit(args, {"backend": "remote"})
        self.assertEqual(result["checks"]["egress"]["state"], "ok")
        self.assertEqual(result["checks"]["application_scope"]["state"], "not_measured")
        self.assertFalse(result["complete"])

    def test_offline_audit_never_connects(self):
        with patch.object(audit, "measure", side_effect=AssertionError("network")):
            self.assertFalse(audit.audit(SimpleNamespace(network=False), {})["attempted"])
