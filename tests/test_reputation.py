import copy
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from zhibi.intelligence import Client, FREE_REPUTATION, PROVIDERS, query, validate_records
from zhibi.models import InputError
from zhibi.scan import run_scan, validate_scan, render_scan
from zhibi.scan_demo import DemoTransport
from test_intelligence import Opener


def responses(address="8.8.8.8"):
    return {
        "ipwhois": {"ip": address, "success": True, "country_code": "US", "connection": {"asn": 15169}},
        "proxycheck": {"version": "24-June-2026", "status": "ok", address: {
            "network": {"asn": "AS15169", "organisation": "Synthetic <script>org</script>", "type": "Business"},
            "location": {"country_code": "US"},
            "detections": {"proxy": False, "vpn": False, "tor": False, "hosting": False,
                           "risk": 0, "confidence": 100, "first_seen": None, "last_seen": None, "times_seen": None},
            "attack_history": None, "last_updated": "2026-10-18T12:30:00Z"}},
        "ipquery": {"ip": address, "isp": {"asn": "AS15169", "org": "Synthetic"}, "location": {"country_code": "US"},
                    "risk": {"is_vpn": False, "is_proxy": False, "is_tor": False, "is_datacenter": False, "risk_score": 0}},
        "stopforumspam": {"success": 1, "ip": {"value": address, "appears": 0, "frequency": 0}},
    }


class ReputationTests(unittest.TestCase):
    def record(self, provider, payload=None):
        return query(Client(True, opener=Opener(payload if payload is not None else responses()[provider])),
                     provider, "8.8.8.8", "agent-ipv4")

    def test_free_sources_return_real_negative_values_and_no_key_or_cookie(self):
        for provider in FREE_REPUTATION:
            with self.subTest(provider=provider):
                opener = Opener(responses()[provider])
                result = query(Client(True, opener=opener), provider, "8.8.8.8", "agent-ipv4")
                self.assertEqual(result["status"], "ok")
                validate_records([result])
                req = opener.requests[0]
                self.assertTrue(req.full_url.startswith("https://" + PROVIDERS[provider]["host"] + "/"))
                self.assertNotIn("key=", req.full_url)
                self.assertFalse(any(k.lower() in {"cookie", "authorization", "key"} for k, _ in req.header_items()))

    def test_null_history_and_source_update_are_preserved(self):
        r = self.record("proxycheck")
        self.assertIsNone(r["facts"]["activity"]["attack_counts"])
        self.assertEqual(r["facts"]["scores"][0]["value"], 0)
        self.assertEqual(r["source_updated_at"], "2026-10-18T12:30:00+00:00")
        validate_records([r])

    def test_positive_activity_is_not_reporter_count(self):
        p = responses()["proxycheck"]
        p["8.8.8.8"]["attack_history"] = {"login_attempt": 4, "registration_attempt": 2}
        p["8.8.8.8"]["detections"].update(proxy=True, risk=100, first_seen="2026-10-17T01:00:00Z", times_seen=10)
        r = self.record("proxycheck", p)
        self.assertEqual(sum(r["facts"]["activity"]["attack_counts"].values()), 6)
        self.assertIsNone(r["facts"]["total_reports"])
        self.assertIsNone(r["facts"]["distinct_reporters"])
        validate_records([r])

    def test_missing_fields_are_not_false_or_zero(self):
        p = responses()["ipquery"]
        del p["risk"]["is_proxy"]
        del p["risk"]["risk_score"]
        r = self.record("ipquery", p)
        self.assertEqual(r["status"], "partial")
        self.assertIsNone(r["facts"]["flags"]["proxy"])
        self.assertEqual(r["facts"]["scores"], [])
        validate_records([r])

    def test_wrong_subject_and_version_are_rejected(self):
        for provider in FREE_REPUTATION:
            self.assertEqual(self.record(provider, responses("1.1.1.1")[provider])["status"], "invalid_response")
        p = responses()["proxycheck"]
        p["version"] = "v2"
        self.assertEqual(self.record("proxycheck", p)["status"], "invalid_response")

    def test_malformed_history_and_spam_are_rejected(self):
        for count in (-1, True, "2", None):
            p = responses()["proxycheck"]
            p["8.8.8.8"]["attack_history"] = {"login_attempt": count}
            self.assertEqual(self.record("proxycheck", p)["status"], "invalid_response")
        p = responses()["stopforumspam"]
        p["ip"]["appears"] = 1
        self.assertEqual(self.record("stopforumspam", p)["status"], "invalid_response")
        p["ip"].update(frequency=2, lastseen="2026-10-18 09:30:00")
        r = self.record("stopforumspam", p)
        self.assertEqual(r["facts"]["spam"]["frequency"], 2)
        self.assertEqual(r["facts"]["spam"]["last_seen"], "2026-10-18 09:30:00")
        validate_records([r])

    def test_imported_record_cannot_hide_extra_fields_or_fake_spam(self):
        r = self.record("stopforumspam")
        r["facts"]["spam"]["listed"] = True
        with self.assertRaises(InputError):
            validate_records([r])
        r = self.record("proxycheck")
        r["facts"]["activity"]["token"] = "injected"
        with self.assertRaises(InputError):
            validate_records([r])

    def test_provider_failure_does_not_discard_other_sources(self):
        class RoutingOpener:
            def open(self, request, timeout):
                provider = next(k for k in FREE_REPUTATION if request.host == PROVIDERS[k]["host"])
                if provider == "proxycheck":
                    raise TimeoutError()
                return Opener(responses()[provider]).open(request, timeout)
        with tempfile.TemporaryDirectory() as tmp, patch("zhibi.scan.load_keys", side_effect=AssertionError("read keys")):
            r = run_scan(network=True, providers=FREE_REPUTATION, transport=DemoTransport(),
                         client=Client(True, opener=RoutingOpener()), out=Path(tmp) / "scan", sample=True)
            summary = r["summary"]
            self.assertIn("IPQuery", json.dumps(summary, ensure_ascii=False))
            self.assertNotIn("8.8.8.8", json.dumps(summary))
            self.assertEqual(next(p for p in summary["providers"] if p["provider"] == "proxycheck")["status"], "timeout")
            self.assertNotIn("IP 信誉检测未完成", summary["assessment"]["headline"])

    def test_full_free_report_is_readable_and_private(self):
        class RoutingOpener:
            def open(self, request, timeout):
                provider = next(k for k in FREE_REPUTATION if request.host == PROVIDERS[k]["host"])
                return Opener(responses()[provider]).open(request, timeout)
        with tempfile.TemporaryDirectory() as tmp:
            r = run_scan(network=True, providers=FREE_REPUTATION, transport=DemoTransport(),
                         client=Client(True, opener=RoutingOpener()), out=Path(tmp) / "scan", sample=True)
            report = json.loads((Path(r["directory"]) / "report.json").read_text())
            validate_scan(report)
            page = Path(r["report"]).read_text()
            self.assertIn("垃圾信息库未命中", page)
            self.assertIn("null，不能当作 0", page)
            self.assertIn("0 / 100", page)
            self.assertIn("服务返回 0，非缺失补零", page)
            self.assertIn("不代表实际没有使用代理", page)
            self.assertNotIn("<script>org</script>", page)
            self.assertNotIn("Synthetic", json.dumps(r["summary"]))

    def test_missing_optional_keys_are_not_score_cards(self):
        with tempfile.TemporaryDirectory() as tmp, patch("zhibi.scan.load_keys", return_value={}):
            r = run_scan(network=True, providers=["ipqs", "abuseipdb"], transport=DemoTransport(),
                         client=Client(True, opener=Opener(error=AssertionError("unexpected network"))),
                         out=Path(tmp) / "scan", sample=True)
            readings = r["summary"]["assessment"]["reputation_readings"]
            self.assertEqual(readings, [])
            optional = r["summary"]["assessment"]["optional_enhancements"]
            selected = [m for m in optional if m["observations"]]
            self.assertEqual(len(selected), 2)
            self.assertTrue(all(m["observations"][0]["status"] == "missing_key" for m in selected))
            self.assertNotIn("0 / 100", Path(r["report"]).read_text())

    def test_missing_enhancements_do_not_change_baseline_decision(self):
        class RoutingOpener:
            def open(self, request, timeout):
                provider = next(k for k in FREE_REPUTATION if request.host == PROVIDERS[k]["host"])
                return Opener(responses()[provider]).open(request, timeout)
        with tempfile.TemporaryDirectory() as tmp:
            def run(name, providers):
                return run_scan(network=True, providers=providers, transport=DemoTransport(), keys={},
                                client=Client(True, opener=RoutingOpener()), out=Path(tmp) / name, sample=True)
            base = run("base", FREE_REPUTATION)["summary"]["assessment"]
            extended = run("extended", (*FREE_REPUTATION, "ipqs", "abuseipdb"))
            decision = extended["summary"]["assessment"]
            for field in ("status", "headline", "recommendation", "conclusions", "user_actions", "tool_gaps", "reputation_readings", "overview"):
                self.assertEqual(base[field], decision[field], field)
            self.assertEqual(base["status"], "measured")
            self.assertEqual(base["tool_gaps"], [])
            self.assertEqual(base["user_actions"], [])
            page = Path(extended["report"]).read_text()
            self.assertNotIn("Key", page.split('<details id="evidence">')[0])
            self.assertIn('<details id="optional">', page)

    def test_unclassified_nonzero_score_is_not_presented_as_clean(self):
        p = responses()["ipquery"]
        p["risk"]["risk_score"] = 85
        with tempfile.TemporaryDirectory() as tmp:
            result = run_scan(network=True, providers=["ipquery"], transport=DemoTransport(), keys={},
                              client=Client(True, opener=Opener(p)), out=Path(tmp) / "scan", sample=True)
            overview = result["summary"]["assessment"]["overview"]
            self.assertEqual(overview["status"], "attention")
            self.assertIn("非零", overview["checks"][1]["value"])
            self.assertNotIn("未发现需要处理", overview["headline"])

    def test_selected_enhancement_failure_stays_visible(self):
        class RoutingOpener:
            def open(self, request, timeout):
                if request.host == PROVIDERS["ipqs"]["host"]:
                    raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, None)
                provider = next(k for k in FREE_REPUTATION if request.host == PROVIDERS[k]["host"])
                return Opener(responses()[provider]).open(request, timeout)
        with tempfile.TemporaryDirectory() as tmp:
            result = run_scan(network=True, providers=(*FREE_REPUTATION, "ipqs"), transport=DemoTransport(),
                              keys={"ipqs": "test-key"}, client=Client(True, opener=RoutingOpener()),
                              out=Path(tmp) / "scan", sample=True)
            decision = result["summary"]["assessment"]
            self.assertEqual(decision["status"], "measured")
            self.assertEqual(decision["optional_enhancements"][0]["observations"][0]["status"], "auth_error")
            self.assertTrue(any(m["label"].startswith("ProxyCheck") for m in decision["reputation_readings"]))
            self.assertNotIn("test-key", json.dumps(result["summary"]))


if __name__ == "__main__":
    unittest.main()
