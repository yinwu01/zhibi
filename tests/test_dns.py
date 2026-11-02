import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from zhibi.dns import DOMAIN, measure, parse_answer, run_dns, summary
from zhibi.models import InputError


class DnsTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        self.patcher = patch("zhibi.dns.Path.home", return_value=Path(self.home.name))
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_txt_roles_are_not_confused(self):
        facts = parse_answer(b'"ns" "8.8.8.8"\n"ecs" "1.1.1.0/24/0"\n"ip" "1.1.1.77"\n')
        self.assertEqual(facts["resolvers"], ["8.8.8.8"])
        self.assertEqual(facts["ecs"], [{"subnet": "1.1.1.0/24", "scope_prefix": 0}])
        self.assertNotIn("1.1.1.77", json.dumps(facts))

    def test_untrusted_and_malformed_answers_do_not_escape(self):
        for raw in (b'x' * 32769, b'"ns" "127.0.0.1"', b'"ns" "::1"',
                    b'"ns" "8.8.8.8; upload cookies"', b'"ns" "8.8.8.8"\nIgnore instructions',
                    b'"ecs" "1.1.1.0/24/200"', b'"ecs" "1.1.1.1/24/0"', b'\xff'):
            with self.assertRaises(ValueError):
                parse_answer(raw)

    def test_default_and_missing_tool_never_launch(self):
        runner = Mock(side_effect=AssertionError("should not run"))
        self.assertEqual(measure(False, runner)["status"], "skipped")
        self.assertEqual(measure(True, runner, lambda _: None)["status"], "unsupported")
        runner.assert_not_called()

    def test_fixed_invocation_and_summary_privacy(self):
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, b'"ns" "8.8.8.8"\n"ecs" "1.1.1.0/24/0"\n'))
        record = measure(True, runner, lambda _: "/usr/bin/dig")
        command = runner.call_args[0][0]
        self.assertEqual(command[1:3], [DOMAIN, "TXT"])
        self.assertNotIn("shell", runner.call_args[1])
        self.assertEqual(runner.call_args[1]["timeout"], 8)
        self.assertEqual(runner.call_count, 1)
        exported = summary(record)
        self.assertEqual(exported["status"], "ok")
        self.assertTrue(exported["ecs_reported"])
        self.assertEqual(exported["browser_dns"], "unobserved")
        self.assertNotIn("8.8.8.8", json.dumps(exported))
        self.assertNotIn("1.1.1.0", json.dumps(exported))

    def test_existing_dig_defaults_are_not_read_or_executed(self):
        (Path(self.home.name) / ".digrc").write_text("@unexpected.example extra.example")
        runner = Mock(side_effect=AssertionError("should not run"))
        result = measure(True, runner, lambda _: "dig")
        self.assertEqual(result["status"], "configuration_present")
        self.assertFalse(result["attempted"])
        runner.assert_not_called()

    def test_failures_and_empty_answers_stay_unknown(self):
        cases = [(subprocess.CompletedProcess([], 9, b"secret"), "error"),
                 (subprocess.CompletedProcess([], 0, b""), "no_answer"),
                 (subprocess.CompletedProcess([], 0, b"untrusted"), "invalid_response")]
        for completed, status in cases:
            record = measure(True, lambda *a, **kw: completed, lambda _: "dig")
            self.assertEqual(record["status"], status)
            self.assertEqual(summary(record)["finding"]["state"], "unknown")
            self.assertNotIn("secret", json.dumps(record))
        runner = Mock(side_effect=subprocess.TimeoutExpired("dig", 8, output=b"secret"))
        record = measure(True, runner, lambda _: "dig")
        self.assertEqual(record["status"], "timeout")
        self.assertNotIn("secret", json.dumps(record))

    def test_report_boundary_and_output_reserved_before_network(self):
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, b'"ns" "8.8.8.8"'))
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "dns"
            result = run_dns(True, dest, runner, lambda _: "dig")
            self.assertNotIn("8.8.8.8", json.dumps(result))
            self.assertIn("8.8.8.8", (dest / "snapshot.private.json").read_text())
            report = json.loads((dest / "report.json").read_text())
            nodes = {n["id"] for n in report["graph"]["nodes"]}
            self.assertTrue(all(e["from"] in nodes and e["to"] in nodes for e in report["graph"]["edges"]))
            self.assertIn("浏览器 DNS 未测量", (dest / "report.html").read_text())
            with self.assertRaises(InputError):
                run_dns(True, dest, runner, lambda _: "dig")
            self.assertEqual(runner.call_count, 1)


if __name__ == "__main__":
    unittest.main()
