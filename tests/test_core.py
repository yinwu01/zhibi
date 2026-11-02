import io
import json
import os
import socket
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout, redirect_stderr
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from zhibi import reports
from zhibi.checks import collect, proxy_check
from zhibi.cli import main
from zhibi.demo import fixture
from zhibi.engine import bundle, evaluate, explain, source_state, validate_report
from zhibi.models import InputError, browser_input, profile, read_json, timestamp
from zhibi.privacy import agent_summary, compare_reports
from zhibi.storage import create_run, write
from zhibi.transport import NetworkError, NoRedirect, Transport


def result(scenario="route-mismatch", change=None):
    data = fixture(scenario)
    if change:
        change(data)
    return evaluate(data["observations"], data["profile"], sample=True, at=timestamp(data["evaluated_at"]))


def finding(report, rule):
    return next(f for f in report["findings"] if f["rule_id"] == rule)


class RuleTests(unittest.TestCase):
    def test_mismatch_is_not_a_ban_prediction(self):
        report = result()
        self.assertEqual(finding(report, "network.route")["assessment"], "needs_confirmation")
        self.assertNotIn("ban_probability", report)

    def test_intentional_routing_normal_counterexample(self):
        self.assertEqual(finding(result("intentional-routing"), "network.route")["assessment"], "verified")

    def test_all_failed_is_unavailable(self):
        report = result("measurement-failure")
        self.assertEqual(report["coverage"], "unavailable")
        self.assertFalse(any(f["assessment"] == "verified" for f in report["findings"]))

    def test_missing_measurements_are_unknown(self):
        report = evaluate([], at=timestamp(fixture()["evaluated_at"]))
        self.assertEqual(report["coverage"], "unavailable")
        self.assertEqual(finding(report, "network.route")["assessment"], "unknown")

    def test_stale_sources_do_not_produce_definite_network_conclusion(self):
        self.assertEqual(finding(result("stale-policy"), "network.route")["assessment"], "unknown")

    def test_future_policy_not_used_as_current(self):
        f = finding(result(), "policy.context")
        self.assertEqual(f["assessment"], "needs_confirmation")
        self.assertTrue(any("未生效" in x for x in f["limitations"]))

    def test_source_timezones_compare_instants(self):
        source = bundle("sources")[0]
        self.assertEqual(source_state(source, timestamp("2026-10-17T16:40:00Z")), "current")
        self.assertEqual(source_state(source, timestamp("2026-10-17T16:30:00Z")), "future")

    def test_automated_browser_cannot_stand_in_for_user(self):
        def mutate(data):
            data["observations"][4]["facts"]["automated"] = True
        self.assertEqual(finding(result(change=mutate), "network.route")["assessment"], "unknown")

    def test_old_or_future_browser_samples_are_not_comparable(self):
        for delta in (-1000, 1000):
            def mutate(data):
                data["observations"][5]["at"] = (timestamp(data["evaluated_at"]) + timedelta(seconds=delta)).isoformat()
            self.assertEqual(finding(result(change=mutate), "network.route")["assessment"], "unknown")

    def test_language_does_not_raise_risk(self):
        def mutate(data):
            data["observations"][4]["facts"]["language"] = "ru-RU"
        self.assertEqual(finding(result(change=mutate), "browser.context")["assessment"], "verified")

    def test_web_does_not_need_code(self):
        self.assertEqual(finding(result(), "client.installed")["assessment"], "not_applicable")
        def mutate(data):
            data["profile"]["product"] = "code"
        self.assertEqual(finding(result(change=mutate), "client.installed")["assessment"], "needs_action")

    def test_trace_graph_and_references(self):
        report = result()
        validate_report(report)
        self.assertTrue(explain("network.route")["edges"])
        report["findings"][0]["evidence_refs"] = ["not-a-source"]
        with self.assertRaises(InputError):
            validate_report(report)

    def test_compare_preserves_scope(self):
        changes = compare_reports(result(), result("intentional-routing"))
        self.assertEqual(changes["changes"], [{"rule_id": "network.route",
                                              "before": "needs_confirmation", "after": "verified"}])


class PrivacyTests(unittest.TestCase):
    def test_proxy_credentials_and_hosts_never_enter_observation(self):
        obs = proxy_check({"https_proxy": "http://user:SUPERSECRET@example.internal:8080"})
        serialized = json.dumps(obs)
        for sensitive in ("SUPERSECRET", "example.internal", "user:"):
            self.assertNotIn(sensitive, serialized)
        self.assertTrue(obs["facts"]["authenticated"])

    def test_export_rebuilds_from_fixed_vocabulary(self):
        report = result()
        report["findings"][0]["statement"] = "PRIVATE_TOKEN_123"
        report["findings"][0]["limitations"] = ["198.51.100.20"]
        report["observations"][0]["summary"] = "someone@example.com"
        text = json.dumps(agent_summary(report))
        for token in ("PRIVATE_TOKEN", "198.51.100.20", "someone@example"):
            self.assertNotIn(token, text)

    def test_html_cannot_execute_untrusted_text(self):
        report = result()
        report["findings"][0]["statement"] = '<script>alert("bad")</script>'
        content = reports.html(report)
        self.assertNotIn('<script>alert', content)
        self.assertIn("&lt;script&gt;", content)
        self.assertIn("default-src 'none'", content)

    def test_sensitive_profile_fields_rejected(self):
        with self.assertRaises(InputError):
            profile({"cookie": "secret"})

    def test_arbitrary_browser_properties_rejected(self):
        data = fixture()
        browser = {"schema_version": "1", "context": "user_opened_browser",
                   "observations": data["observations"][4:6]}
        browser["observations"][0]["facts"]["token"] = "secret"
        with self.assertRaises(InputError):
            browser_input(browser)

    def test_oversized_and_duplicate_json_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "input.json"
            target.write_text('{"a":1,"a":2}')
            with self.assertRaises(InputError):
                read_json(target)
            target.write_text(" " * 131073)
            with self.assertRaises(InputError):
                read_json(target)

    def test_no_overwrite_and_private_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = create_run(Path(tmp) / "run")
            write(path / "report.txt", "private")
            with self.assertRaises(FileExistsError):
                write(path / "report.txt", "replacement")
            self.assertEqual((path / "report.txt").read_text(), "private")
            if os.name == "posix":
                self.assertEqual(path.stat().st_mode & 0o777, 0o700)
                self.assertEqual((path / "report.txt").stat().st_mode & 0o777, 0o600)


class NetworkTests(unittest.TestCase):
    def test_default_collect_never_opens_network(self):
        with patch("urllib.request.OpenerDirector.open") as open_call:
            collect(Transport())
            open_call.assert_not_called()

    def test_network_disable_and_unknown_services_are_closed(self):
        for transport, service in ((Transport(), "ipify"), (Transport(True), "unknown"),
                                   (Transport(True), "ipwhois")):
            with self.assertRaises(NetworkError):
                transport.get(service, "8.8.8.8")
            self.assertEqual(transport.flows, [])

    def test_timeout_is_not_success_and_budget_is_finite(self):
        transport = Transport(True)
        with patch("urllib.request.OpenerDirector.open", side_effect=urllib.error.URLError(socket.timeout())) as call:
            with self.assertRaises(NetworkError) as error:
                transport.get("ipify")
            self.assertEqual(error.exception.status, "timeout")
            with self.assertRaises(NetworkError):
                transport.get("ipify")
            self.assertEqual(call.call_count, 1)
        self.assertTrue(transport.flows[0]["sent"])

    def test_redirect_is_not_followed(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.example"))

    def test_metadata_rejects_private_address(self):
        with patch("urllib.request.OpenerDirector.open") as call:
            with self.assertRaises(NetworkError):
                Transport(True, True).get("ipwhois", "127.0.0.1")
            call.assert_not_called()

    def test_successful_ip_response_and_metadata(self):
        class Response:
            def __init__(self, payload):
                self.payload = payload
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self, n):
                return json.dumps(self.payload).encode()
        payloads = [Response({"ip": "8.8.8.8"}), Response({"success": True, "country_code": "US", "connection": {"asn": 15169}})]
        transport = Transport(True, True)
        with patch("urllib.request.OpenerDirector.open", side_effect=payloads):
            items = collect(transport)
        by_id = {i["check_id"]: i for i in items}
        self.assertEqual(by_id["network.metadata"]["status"], "ok")
        self.assertEqual(len(transport.flows), 2)

    def test_malformed_ip_response_does_not_become_a_finding(self):
        transport = Transport(True)
        with patch.object(transport, "get", return_value={"ip": "<secret>"}):
            items = collect(transport)
        egress = next(i for i in items if i["check_id"] == "network.egress")
        self.assertEqual(egress["status"], "error")
        self.assertEqual(egress["facts"], {})


class CLITests(unittest.TestCase):
    def test_demo_roundtrip_and_schema(self):
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(io.StringIO()):
            path = Path(tmp) / "demo"
            self.assertEqual(main(["demo", "--out", str(path)]), 0)
            report = read_json(path / "report.json")
            try:
                import jsonschema
            except ImportError:
                self.skipTest("Optional jsonschema development dependency not installed.")
            schema = read_json(Path(__file__).resolve().parents[1] / "schemas/report.schema.json")
            jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(report)
            self.assertEqual(main(["report", str(path / "report.json"), "--out", str(Path(tmp) / "again.html")]), 0)
            self.assertEqual((path / "report.html").read_text(encoding="utf-8"), (Path(tmp) / "again.html").read_text(encoding="utf-8"))

    def test_nested_report_corruption_is_rejected(self):
        for field, bad in (("findings", [None]), ("observations", ["not-an-object"])):
            report = result()
            report[field] = bad
            with self.assertRaises(InputError):
                validate_report(report)

    def test_invalid_request_returns_nonzero_without_input_echo(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "profile.json"
            source.write_text('{"cookie":"PRIVATE_SECRET"}')
            stream = io.StringIO()
            with redirect_stderr(stream):
                self.assertEqual(main(["check", "--profile", str(source)]), 2)
            self.assertNotIn("PRIVATE_SECRET", stream.getvalue())

    def test_metadata_requires_network(self):
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(["plan", "--ip-metadata"]), 2)


if __name__ == "__main__":
    unittest.main()
