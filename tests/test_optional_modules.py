import copy
import io
import json
import os
import struct
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import patch

from test_intelligence import Opener
from test_scan import browser_bundle
from test_browser_details import details
from zhibi import diagnostics as d, maintenance, vault, suite
from zhibi.browser import parse_bundle
from zhibi.browser_extras import LABELS, validate
from zhibi.checkcc_model import evaluate
from zhibi.dns_observer import Observer
from zhibi.intelligence import Client, query, validate_records, QueryFailure, parse
from zhibi.models import InputError, now
from zhibi.scan import run_scan
from zhibi.session import handler


def bundle4():
    b = browser_bundle()
    b.update(schema_version="4", details=details(), extras={"at": now(), "checks": {k: {"status": "skipped", "facts": None} for k in LABELS}})
    return b


class ProviderExtensionTests(unittest.TestCase):
    def test_official_endpoints_auth_and_response_contract(self):
        values = {
            "ipinfo": {"ip": "8.8.8.8", "country_code": "US", "asn": "AS15169", "as_name": "Google"},
            "ipregistry": {"ip": "8.8.8.8", "location": {"country": {"code": "US"}}, "connection": {"asn": 15169}, "security": {"is_proxy": False, "is_vpn": False}},
            "ip2location": {"ip": "8.8.8.8", "country_code": "US", "asn": "15169", "is_proxy": False, "fraud_score": 0},
            "dbip": {"ipAddress": "8.8.8.8", "countryCode": "US"},
            "scamalytics": {"scamalytics": {"status": "ok", "ip": "8.8.8.8", "scamalytics_score": 0, "scamalytics_org": "PREMIUM FIELD - upgrade to view", "scamalytics_proxy": {"is_vpn": False}}},
        }
        for provider, value in values.items():
            with self.subTest(provider=provider):
                op = Opener(value)
                key = "user:sentinel-key" if provider == "scamalytics" else None if provider == "dbip" else "sentinel-key"
                client = Client(True, opener=op)
                record = query(client, provider, "8.8.8.8", "agent-ipv4", key)
                self.assertEqual(record["status"], "ok")
                validate_records([record])
                self.assertNotIn("sentinel-key", json.dumps(record) + json.dumps(client.flows))
                if provider not in ("scamalytics", "dbip"):
                    self.assertNotIn("sentinel-key", op.requests[0].full_url)
                if provider == "ip2location":
                    self.assertEqual(record["facts"]["scores"][0]["scale"], 99)
                if provider == "scamalytics":
                    self.assertIsNone(record["facts"]["organization"])

    def test_missing_credentials_never_make_requests(self):
        for provider in ("ipinfo", "ipregistry", "scamalytics", "scamalytics-us"):
            op = Opener()
            record = query(Client(True, opener=op), provider, "8.8.8.8", "agent-ipv4")
            self.assertEqual(record["status"], "missing_key")
            self.assertEqual(op.requests, [])

    def test_missing_is_not_zero_and_address_mismatch_rejected(self):
        facts, _ = parse("ip2location", {"ip": "8.8.8.8", "country_code": "US"}, "8.8.8.8")
        self.assertEqual(facts["scores"], [])
        self.assertIsNone(facts["flags"]["proxy"])
        with self.assertRaises(QueryFailure):
            parse("dbip", {"ipAddress": "1.1.1.1", "countryCode": "US"}, "8.8.8.8")
        with self.assertRaises(QueryFailure):
            parse("ip2location", {"ip": "8.8.8.8", "fraud_score": 100}, "8.8.8.8")


class DiagnosticsTests(unittest.TestCase):
    def test_smtp_fixed_targets_and_never_sends_mail(self):
        class Connection:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def send(self, *args): raise AssertionError("Must not send mail")
        calls = []
        def connect(target, timeout):
            calls.append(target)
            return Connection()
        r = d.smtp("gmail", 587, connect)
        self.assertFalse(r["facts"]["mail_sent"])
        self.assertEqual(calls, [("smtp.gmail.com", 587)])
        with self.assertRaises(InputError):
            d.smtp("arbitrary", 22, connect)

    def test_dnsbl_error_codes_not_listed(self):
        with patch("shutil.which", return_value="dig"), patch("pathlib.Path.exists", return_value=False):
            for code, expected in (("127.255.255.254", "access_restricted"), ("127.0.0.10", "review"), ("8.8.8.8", "access_restricted")):
                output = ";; status: NOERROR\nx. 2 IN A " + code
                def runner(args, **kw):
                    if args[-2].startswith("2.0.0.127."):
                        return ";; status: NOERROR\nx. 2 IN A 127.0.0.2", "ok"
                    if args[-2].startswith("1.0.0.127."):
                        return ";; status: NXDOMAIN", "ok"
                    return output, "ok"
                r = d.dnsbl("8.8.8.8", "spamhaus", runner=runner)
                self.assertEqual(r["status"], expected)
            r = d.dnsbl("8.8.8.8", "spamcop", runner=lambda *a, **kw: (";; status: SERVFAIL", "ok"))
            self.assertEqual(r["status"], "error")

    def test_route_credentials_only_in_stdin_and_no_fallback(self):
        calls = []
        def run(args, **kw):
            calls.append((args, kw))
            return json.dumps({"ip": "8.8.8.8"}), "ok"
        record = d.route({"proxy_url": "socks5h://user:secret@127.0.0.1:1080", "expected_ip": "1.1.1.1"}, runner=run)
        self.assertEqual(record["status"], "review")
        self.assertNotIn("secret", json.dumps(calls[0][0]) + json.dumps(record))
        self.assertIn("secret", calls[0][1]["stdin"])
        self.assertEqual(len(calls), 1)
        with self.assertRaises(InputError):
            d.route({"proxy_url": 'http://host\nurl="evil"'}, runner=run)


class ResearchAndBrowserTests(unittest.TestCase):
    def test_checkcc_port_original_weights_rounding_and_no_verdict_change(self):
        value = evaluate({"timezone": "Asia/Shanghai", "languages": ["zh-CN"], "locale": "zh-CN", "userAgent": "huawei quark"}, "CN")
        self.assertEqual(value["score"], 98)
        self.assertEqual(next(x["contribution"] for x in value["contributions"] if x["feature"] == "device"), 6)
        self.assertFalse(value["changes_zhibi_verdict"])
        self.assertFalse(value["platform_rule"])

    def test_v4_roundtrip_private_render_attributes_not_agent_summary(self):
        b = bundle4()
        b["extras"]["checks"]["canvas"] = {"status": "ok", "facts": {"sha256": "a" * 64, "repeated_equal": False, "width": 240, "height": 80}}
        parse_bundle(b)
        with tempfile.TemporaryDirectory() as tmp, patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("network")):
            source = Path(tmp) / "browser.json"
            source.write_text(json.dumps(b))
            r = suite.run("custom", ["browser-extras", "checkcc-model"], False, source, "browser", out=Path(tmp) / "report")
            self.assertIn("两次渲染不同", Path(r["report"]).read_text())
            self.assertNotIn("a" * 64, json.dumps(r["summary"]))
            self.assertNotIn("zh-CN", json.dumps(r["summary"]))
            page = Path(r["report"]).read_text()
            front, optional = page.split('<details id="optional-results">', 1)
            self.assertNotIn("两次渲染不同", front)
            self.assertIn("两次渲染不同", optional)
            self.assertNotIn('<details id="optional-results" open', page)
            baseline = r["summary"]["base"]["assessment"]["overview"]
            self.assertEqual(sum(baseline["counts"].values()), len(baseline["table_rows"]))

    def test_v4_rejects_nonfinite_audio_and_unrequested_data(self):
        b = bundle4()["extras"]
        b["checks"]["audio"] = {"status": "ok", "facts": {"samples": 5000, "sample_rate": 44100, "absolute_sum": float("nan")}}
        with self.assertRaises(InputError): validate(b)
        b["checks"]["audio"]["status"] = "skipped"
        with self.assertRaises(InputError): validate(b)


class MaintenanceTests(unittest.TestCase):
    def test_plan_does_not_mutate_and_restore_reobserves(self):
        state, calls = {"zone": "UTC"}, []
        def runner(args, **kw):
            calls.append(args)
            if "-gettimezone" in args:
                return "Time Zone: " + state["zone"], "ok"
            state["zone"] = args[-1]
            return "", "ok"
        with patch("platform.system", return_value="Darwin"), tempfile.TemporaryDirectory() as tmp:
            plan = maintenance.settings("timezone", "", "Asia/Taipei", runner=runner)
            self.assertFalse(plan["applied"])
            self.assertEqual(state["zone"], "UTC")
            applied = maintenance.settings("timezone", "", "Asia/Taipei", True, Path(tmp) / "change", runner)
            self.assertTrue(applied["applied"])
            restored = maintenance.restore(Path(tmp) / "change/receipt.private.json", True, Path(tmp) / "restore", runner)
            self.assertTrue(restored["applied"])
            self.assertEqual(state["zone"], "UTC")

    def test_changed_setting_not_overwritten_by_restore(self):
        with tempfile.TemporaryDirectory() as tmp, patch("platform.system", return_value="Darwin"):
            path = Path(tmp) / "receipt"
            path.write_text(json.dumps({"format": "zhibi-setting-1", "platform": "Darwin", "action": "timezone", "scope": "", "before": "UTC", "after": "Asia/Taipei", "command": ["malicious"]}))
            with self.assertRaises(InputError):
                maintenance.restore(path, True, runner=lambda *a, **kw: ("Time Zone: Europe/London", "ok"))


class VaultTests(unittest.TestCase):
    def test_encrypted_roundtrip_and_authentication_before_mutation(self):
        try: vault.crypto()
        except InputError: self.skipTest("optional cryptography not installed")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "profile"; root.mkdir(); (root / "data").write_text("private-sentinel")
            archive = Path(tmp) / "backup"
            result = vault.backup(root, archive, True, "test-password-long")
            self.assertTrue(result["roundtrip_verified"])
            self.assertNotIn(b"private-sentinel", (archive / "profile.enc").read_bytes())
            with self.assertRaises(InputError):
                vault.restore(archive / "profile.enc", root, True, True, secret="wrong-password")
            self.assertEqual((root / "data").read_text(), "private-sentinel")
            (root / "data").write_text("new-value")
            restored = vault.restore(archive / "profile.enc", root, True, True, secret="test-password-long")
            self.assertEqual((root / "data").read_text(), "private-sentinel")
            self.assertEqual((Path(restored["previous_directory"]) / "data").read_text(), "new-value")

    def test_zip_traversal_and_active_profile_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "profile"; root.mkdir(); (root / "SingletonLock").touch()
            with self.assertRaises(InputError): vault.root_path(root, True)
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w") as z: z.writestr("../outside", "x")
            with self.assertRaises(InputError): vault.unpack(stream.getvalue(), root)
            self.assertFalse((Path(tmp) / "outside").exists())

    def test_cache_quarantine_restore_keeps_authentication_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "profile"; root.mkdir(); (root / "Cache").mkdir(); (root / "Cache/test").write_text("cache")
            (root / "Cookies").write_text("must-not-read-or-change")
            dest = Path(tmp) / "quarantine"
            vault.cache(root, True, True, dest)
            self.assertFalse((root / "Cache").exists())
            self.assertEqual((root / "Cookies").read_text(), "must-not-read-or-change")
            vault.cache_restore(dest, True, True)
            self.assertEqual((root / "Cache/test").read_text(), "cache")


class LocalSessionTests(unittest.TestCase):
    def test_receiver_rejects_foreign_origin_bad_host_and_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = {}
            server = HTTPServer(("127.0.0.1", 0), handler(Path(tmp), "test-token", state))
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            base = "http://127.0.0.1:" + str(server.server_port)
            try:
                for origin in ("https://evil.example", None):
                    headers = {"Content-Type": "application/json"}
                    if origin: headers["Origin"] = origin
                    req = urllib.request.Request(base + "/test-token/result", data=json.dumps(bundle4()).encode(), headers=headers)
                    with self.assertRaises(urllib.error.HTTPError): urllib.request.urlopen(req)
                req = urllib.request.Request(base + "/test-token/result", data=json.dumps(bundle4()).encode(), headers={"Content-Type": "application/json", "Origin": base})
                with urllib.request.urlopen(req) as response: self.assertEqual(response.status, 200)
                self.assertTrue(state["received"])
                with self.assertRaises(urllib.error.HTTPError): urllib.request.urlopen(req)
            finally:
                server.shutdown(); server.server_close(); thread.join()

    def test_dns_authority_correlates_nonce_without_open_recursion(self):
        o = Observer("dns.example.org", "8.8.8.8"); token = o.ticket()
        def packet(name):
            q = b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\x00"
            return struct.pack("!6H", 1, 0x0100, 1, 0, 0, 0) + q + struct.pack("!HH", 1, 1)
        answer = o.answer(packet(token + ".dns.example.org"), "1.1.1.1")
        self.assertEqual(answer[-4:], bytes([8, 8, 8, 8]))
        self.assertEqual(o.report(token)["resolvers"], ["1.1.1.1"])
        denied = o.answer(packet("unrelated.example.org"), "1.1.1.1")
        self.assertEqual(struct.unpack("!H", denied[2:4])[0] & 15, 5)
        self.assertIsNone(o.answer(b"bad", "1.1.1.1"))


class DeliveryTests(unittest.TestCase):
    def test_install_update_rollback_and_digest_mismatch(self):
        from zhibi.delivery import install, rollback
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            archive = base / "skill.zip"
            with zipfile.ZipFile(archive, "w") as z:
                for name, value in (("SKILL.md", "new"), ("assets/zhibi-core.pyz", "stub"), ("scripts/zhibi.py", "stub")):
                    z.writestr("zhibi/" + name, value)
            destination = base / "zhibi"
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            with self.assertRaises(InputError): install(archive, "0" * 64, destination)
            install(archive, digest, destination)
            (destination / "SKILL.md").write_text("old")
            result = install(archive, digest, destination, True)
            self.assertEqual((destination / "SKILL.md").read_text(), "new")
            rollback(destination, result["previous_version"])
            self.assertEqual((destination / "SKILL.md").read_text(), "old")

    def test_generated_client_configuration_keeps_credentials_local(self):
        from zhibi.network_setup import deliver
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve(); source = base / "config.json"
            source.write_text(json.dumps({"type": "socks5", "server": "proxy.example.org", "port": 1080, "username": "user", "password": "secret-sentinel"})); source.chmod(0o600)
            result = deliver(source, base / "delivery")
            self.assertNotIn("secret-sentinel", json.dumps(result))
            data = json.loads((base / "delivery/mihomo.private.json").read_text())
            self.assertFalse(data["tun"]["enable"])
            self.assertFalse(data["allow-lan"])
            self.assertEqual(data["proxies"][0]["password"], "secret-sentinel")

    def test_adspower_refuses_active_profile_and_missing_rollback_values(self):
        from zhibi.adspower import run
        class Fake:
            active = True
            fingerprint = {"webrtc": "disabled"}
            def inspect(self):
                return {"active": self.active, "configuration_readable": True, "fingerprint": self.fingerprint.copy()}
            def request(self, action, patch):
                self.fingerprint.update(patch)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve(); config = base / "config.json"
            config.write_text(json.dumps({"profile_id": "fixture", "patch": {"webrtc": "proxy"}})); config.chmod(0o600)
            fake = Fake()
            with self.assertRaises(InputError): run("update", config, True, base / "active", client=fake)
            self.assertEqual(fake.fingerprint["webrtc"], "disabled")
            fake.active = False
            result = run("update", config, True, base / "change", client=fake)
            self.assertTrue(result["configuration_verified"])
            result = run("restore", config, True, base / "restore", base / "change/receipt.private.json", client=fake)
            self.assertTrue(result["configuration_verified"])
            self.assertEqual(fake.fingerprint["webrtc"], "disabled")

    def test_custom_suite_does_not_silently_select_providers(self):
        self.assertEqual(suite.selected_providers("custom"), [])
        self.assertEqual(suite.selected_providers("custom", ["dbip"]), ["dbip"])
        self.assertEqual(suite.plan("custom", ["smtp"], True)["ip_scan"]["providers"], [])


if __name__ == "__main__":
    unittest.main()

class FinalCoverageTests(unittest.TestCase):
    def test_public_feeds_local_membership_and_untrusted_input(self):
        from zhibi import feeds
        raw = b'# generated\n8.8.8.8 3\n1.1.1.1 1\n'
        value = feeds.parse('ipsum', raw, '8.8.8.8')
        self.assertTrue(value['listed'])
        self.assertFalse(value['queried_ip_transmitted'])
        self.assertEqual(value['matches'][0]['overlapping_feed_count'], 3)
        self.assertFalse(feeds.parse('ipsum', raw, '9.9.9.9')['listed'])
        drop = b'{"cidr":"8.8.8.0/24"}\n{"timestamp":12345}\n'
        self.assertTrue(feeds.parse('spamhaus-drop', drop, '8.8.8.8')['listed'])
        with self.assertRaises(ValueError): feeds.parse('ipsum', b'8.8.8.8 unknown', '8.8.8.8')

    def test_client_model_distinct_weights_and_unobserved_inputs(self):
        from zhibi.checkcc_model import client_signals
        env = {'timezone':'Asia/Harbin', 'languages':['zh-CN'], 'locale':'zh-CN', 'userAgent':'huawei windows'}
        value = client_signals(env, None)
        by_id = {v['feature']:v for v in value['contributions']}
        self.assertEqual(by_id['timezone']['contribution'], 26)
        self.assertEqual(by_id['domesticDevice']['contribution'], 4)
        self.assertIsNone(by_id['chineseFonts']['contribution'])
        self.assertIsNone(by_id['timezoneOffset']['contribution'])
        self.assertFalse(value['complete'])
        self.assertFalse(value['platform_rule'])

    def test_nonzero_new_score_not_called_clean_or_missing(self):
        from zhibi.assessment import assess_scan
        from zhibi.scan_demo import run_demo
        from zhibi.scan import interpret
        with tempfile.TemporaryDirectory() as tmp:
            run = run_demo('conflicting-sources', Path(tmp) / 'run')
            report = json.loads((Path(run['directory']) / 'report.json').read_text())
        record = query(Client(True, opener=Opener({'ip':'8.8.8.8', 'country_code':'US', 'fraud_score':50})), 'ip2location', '8.8.8.8', 'agent-ipv4')
        report['intelligence'] = [record]
        report['findings'] = interpret([record])
        report['paths'] = []
        decision = assess_scan(report)
        self.assertFalse(any('没有 IP 信誉评分' in gap for gap in decision['tool_gaps']))
        self.assertIn('50 / 99', decision['reputation_readings'][0]['value'])
        self.assertEqual(next(c for c in decision['overview']['checks'] if c['label']=='IP 信誉')['state'], 'attention')

class SessionFallbackTests(unittest.TestCase):
    def test_basic_session_selects_only_baseline_network_and_hides_catalog(self):
        from zhibi.session import probe_page
        page = probe_page("basic", True)
        self.assertIn('for(const id of ["ipv4", "ipv6"])', page)
        self.assertIn('id="network-options"><summary>', page)
        self.assertNotIn('id="local-options" open', page)
        offline = probe_page("basic", False)
        self.assertIn('for(const id of [])', offline)

    def test_only_current_download_is_imported_and_partial_file_is_ignored(self):
        from zhibi.session import file_received, probe_page
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); run=root/'run'; run.mkdir()
            download=root/'zhibi-session-selected.json'
            (root/'zhibi-browser.json').write_text(json.dumps(bundle4()))
            self.assertFalse(file_received(run, download))
            download.write_text('{')
            self.assertFalse(file_received(run, download))
            download.write_text(json.dumps(bundle4()))
            self.assertTrue(file_received(run, download))
            self.assertTrue((run/'browser.private.json').is_file())
        page=probe_page('all', True, 'zhibi-session-test.json')
        self.assertIn('a.download="zhibi-session-test.json"', page)
        self.assertNotIn('默认不联网。只记录本页浏览器背景和能力。', page)

    def test_receiver_rejects_wrong_host_and_never_serves_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            state={}; server=HTTPServer(('127.0.0.1',0), handler(Path(tmp), 'token', state))
            thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
            base='http://127.0.0.1:'+str(server.server_port)
            try:
                for path,headers in (('/token',{'Host':'evil.example'}),('/report.html',{}),('/browser.private.json',{})):
                    with self.assertRaises(urllib.error.HTTPError):
                        urllib.request.urlopen(urllib.request.Request(base+path,headers=headers))
                self.assertFalse(state.get('received'))
            finally: server.shutdown();server.server_close();thread.join()
