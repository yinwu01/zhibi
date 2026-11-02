import io
import getpass
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from zhibi.intelligence import Client, QueryFailure, load_keys, parse, query, configure, configure_all
from zhibi.models import InputError
from zhibi.scan import interpret, run_scan, scan_plan
from zhibi.transport import Transport


class Response(io.BytesIO):
    pass


class Opener:
    def __init__(self, payload=None, error=None):
        self.payload, self.error, self.requests = payload, error, []

    def open(self, request, timeout):
        self.requests.append(request)
        if self.error:
            raise self.error
        return Response(json.dumps(self.payload).encode())


class IntelligenceTests(unittest.TestCase):
    def test_no_key_no_request(self):
        opener = Opener()
        r = query(Client(True, opener=opener), "ipqs", "8.8.8.8", "agent-ipv4")
        self.assertEqual(r["status"], "missing_key")
        self.assertEqual(opener.requests, [])
        self.assertFalse(r["facts"])

    def test_key_stays_out_of_url_and_result(self):
        for provider in ("ipapi", "ipqs", "abuseipdb"):
            opener = Opener({"success": False})
            client = Client(True, opener=opener)
            r = query(client, provider, "8.8.8.8", "agent-ipv4", "secret-sentinel")
            self.assertNotIn("secret-sentinel", opener.requests[0].full_url)
            self.assertNotIn("secret-sentinel", json.dumps(r) + json.dumps(client.flows))
            headers = dict((k.lower(), v) for k, v in opener.requests[0].header_items())
            self.assertNotIn("cookie", headers)

    def test_anonymous_ipapi_has_missing_flags_not_false(self):
        payload = {"ip": "8.8.8.8", "asn": "AS15169 Google LLC", "company": "Google", "docs": "https://ipapi.is/free-tier.html"}
        r = query(Client(True, opener=Opener(payload)), "ipapi", "8.8.8.8", "agent-ipv4")
        self.assertEqual(r["status"], "partial")
        self.assertIsNone(r["facts"]["flags"]["vpn"])
        self.assertEqual(r["product_tier"], "anonymous_identity_only")
        self.assertIsNone(r["source_updated_at"])

    def test_wrong_subject_rejected(self):
        r = query(Client(True, opener=Opener({"ip": "1.1.1.1", "success": True})), "ipwhois", "8.8.8.8", "agent-ipv4")
        self.assertEqual(r["status"], "invalid_response")

    def test_provider_failure_never_renders_as_zero(self):
        for code, state in ((429, "quota_exceeded"), (403, "auth_error"), (503, "error")):
            error = urllib.error.HTTPError("https://test.invalid/secret-sentinel", code, "secret-sentinel", {}, None)
            r = query(Client(True, opener=Opener(error=error)), "ipqs", "8.8.8.8", "agent-ipv4", "secret-sentinel")
            self.assertEqual(r["status"], state)
            self.assertIsNone(r["facts"])
            self.assertNotIn("secret-sentinel", json.dumps(r))
            self.assertEqual(interpret([r])[0]["state"], "unknown")

    def test_strict_types_and_no_untrusted_text_in_findings(self):
        for score in (True, float("nan"), 101, "0"):
            with self.assertRaises(QueryFailure):
                parse("ipqs", {"success": True, "fraud_score": score}, "8.8.8.8")
        payload = {"success": True, "fraud_score": 5, "organization": "<script>do_bad_things()</script>", "proxy": False}
        r = query(Client(True, opener=Opener(payload)), "ipqs", "8.8.8.8", "agent-ipv4", "key")
        self.assertNotIn("script", json.dumps(interpret([r])))

    def test_offline_and_duplicate_request_budget(self):
        opener = Opener({})
        with self.assertRaises(QueryFailure):
            Client(False, opener=opener).fetch("ipwhois", "8.8.8.8")
        self.assertEqual(opener.requests, [])
        client = Client(True, opener=opener)
        client.fetch("ipwhois", "8.8.8.8")
        with self.assertRaises(QueryFailure):
            client.fetch("ipwhois", "8.8.8.8")
        self.assertEqual(len(opener.requests), 1)
        with self.assertRaises(InputError):
            client.fetch("ipwhois", "127.0.0.1")

    def test_conflict_is_visible(self):
        records = []
        for provider, asn in (("ipwhois", 15169), ("ipapi", 13335)):
            data = {"success": True, "ip": "8.8.8.8", "country_code": "US", "connection": {"asn": asn}} if provider == "ipwhois" else {
                "ip": "8.8.8.8", "asn": {"asn": asn}, "location": {"country_code": "US"}}
            records.append(query(Client(True, opener=Opener(data)), provider, "8.8.8.8", "agent-ipv4"))
        self.assertTrue(any(f["id"].endswith("conflict:asn") for f in interpret(records)))

    def test_key_file_permissions_and_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keys.json"
            path.write_text('{"ipqs":"secret-sentinel"}')
            if os.name == "posix":
                path.chmod(0o644)
                with self.assertRaises(InputError):
                    load_keys(path)
                path.chmod(0o600)
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(load_keys(path), {"ipqs": "secret-sentinel"})

    def test_configure_does_not_persist_other_environment_keys(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"ZHIBI_IPQS_KEY": "environment-only"}), patch("zhibi.intelligence.config_path", return_value=Path(tmp) / "providers.json"), patch("getpass.getpass", return_value="new-local-key"):
            result = configure("ipapi")
            saved = (Path(tmp) / "providers.json").read_text()
            self.assertNotIn("environment-only", saved)
            self.assertEqual(json.loads(saved), {"ipapi": "new-local-key"})
            self.assertNotIn("new-local-key", json.dumps(result))

    def test_key_wizard_preserves_keys_skips_empty_and_never_echoes_secrets(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"ZHIBI_IPQS_KEY": "env-sentinel"}, clear=True), patch("zhibi.intelligence.config_path", return_value=Path(tmp) / "providers.json"), patch("getpass.getpass", side_effect=["", "local-sentinel"]), patch("sys.stdout", new_callable=io.StringIO) as output:
            result = configure_all()
            saved = Path(tmp) / "providers.json"
            self.assertEqual(json.loads(saved.read_text()), {"ipapi": "local-sentinel"})
            self.assertEqual([r["configured"] for r in result["providers"]], [True, False, True])
            for secret in ("env-sentinel", "local-sentinel"):
                self.assertNotIn(secret, output.getvalue() + json.dumps(result))
            if os.name == "posix":
                self.assertEqual(saved.stat().st_mode & 0o777, 0o600)

    def test_key_input_refuses_visible_fallback(self):
        with tempfile.TemporaryDirectory() as tmp, patch("zhibi.intelligence.config_path", return_value=Path(tmp) / "providers.json"), patch("getpass.getpass", side_effect=getpass.GetPassWarning("visible input unavailable")):
            with self.assertRaisesRegex(InputError, "无法隐藏输入"):
                configure("ipqs")
            self.assertFalse((Path(tmp) / "providers.json").exists())

    def test_oversize_and_duplicate_provider_payloads_are_rejected(self):
        class RawOpener:
            def __init__(self, raw):
                self.raw = raw
            def open(self, request, timeout):
                return Response(self.raw)
        for raw in (b"x" * (128 * 1024 + 1), b'{"ip":"8.8.8.8","ip":"1.1.1.1"}', b'{"success":true,"fraud_score":NaN}'):
            result = query(Client(True, opener=RawOpener(raw)), "ipqs", "8.8.8.8", "agent-ipv4", "secret")
            self.assertEqual(result["status"], "invalid_response")

    def test_offline_end_to_end_no_network(self):
        with tempfile.TemporaryDirectory() as tmp, patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("network")):
            result = run_scan(out=str(Path(tmp) / "run"))
            self.assertTrue(Path(result["report"]).is_file())
            self.assertEqual(result["summary"]["providers"], [])
            self.assertNotIn("ip", result["summary"])

    def test_plan_requires_network_for_enrichment(self):
        with self.assertRaises(InputError):
            scan_plan(providers=["ipqs"])
        plan = scan_plan(True, ["ipqs", "ipqs"], True)
        self.assertEqual(plan["providers"], ["ipqs"])
        self.assertEqual(plan["external_services"][-1]["max_requests"], 2)
        anonymous = scan_plan(True, ["ipwhois"])["external_services"][-1]
        self.assertFalse(any("key" in field for field in anonymous["fields"]))

    def test_keyless_source_does_not_read_key_store(self):
        from zhibi.scan_demo import DemoTransport, DemoClient
        with tempfile.TemporaryDirectory() as tmp, patch("zhibi.scan.load_keys", side_effect=AssertionError("key read")):
            result = run_scan(network=True, providers=["ipwhois"], transport=DemoTransport(), client=DemoClient(), out=Path(tmp) / "scan")
            self.assertEqual(result["summary"]["providers"][0]["status"], "ok")


if __name__ == "__main__":
    unittest.main()
