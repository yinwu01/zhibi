import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_scan import browser_bundle
from zhibi.browser import parse_bundle, advanced_page
from zhibi.browser_details import LABELS, summarize, validate_details
from zhibi.models import InputError, browser_input, now
from zhibi.scan import run_scan, render_scan, scan_summary


def details():
    checks = {k: {"status": "skipped", "facts": None} for k in LABELS}
    checks["locale"] = {"status": "ok", "facts": {"utcOffsetMinutes": 480, "variants": ["simplified"]}}
    checks["fonts"] = {"status": "ok", "facts": {"detected": ["PingFang SC"], "tested": 26}}
    checks["hardware"] = {"status": "ok", "facts": {"logicalProcessors": 8}}
    checks["permissions"] = {"status": "ok", "facts": {"geolocation": "prompt"}}
    checks["identity"] = {"status": "ok", "facts": {"browser": "Chrome", "version": "120.0", "engine": "Blink", "os": "macOS", "device": "desktop", "browserToken": None, "deviceToken": None,
        "brands": [{"brand": '<img src=x onerror="alert(1)">', "version": "120"}], "emojiFamily": "Apple"}}
    return {"at": now(), "checks": checks}


class BrowserDetailsTests(unittest.TestCase):
    def test_versions_remain_compatible_and_optional(self):
        v2 = browser_bundle()
        self.assertNotIn("details", parse_bundle(v2))
        v3 = {**v2, "schema_version": "3", "details": details()}
        self.assertEqual(browser_input(v3), v2["observations"])
        self.assertEqual(parse_bundle(v3)["details"], v3["details"])
        for data in ({**v2, "details": details()}, {**v2, "schema_version": "3"}):
            with self.assertRaises(InputError):
                parse_bundle(data)

    def test_import_rejects_arbitrary_facts_and_false_success(self):
        mutations = [lambda d: d["checks"]["fonts"]["facts"].update(detected=["unexpected font"]),
                     lambda d: d["checks"]["fonts"]["facts"].update(tested=27),
                     lambda d: d["checks"]["hardware"]["facts"].update(logicalProcessors=True),
                     lambda d: d["checks"]["locale"]["facts"].update(utcOffsetMinutes=900),
                     lambda d: d["checks"]["permissions"]["facts"].update(latitude=20),
                     lambda d: d["checks"]["permissions"]["facts"].update(geolocation=[]),
                     lambda d: d["checks"]["identity"]["facts"].update(version="run a command"),
                     lambda d: d["checks"]["identity"].update(status="timeout"),
                     lambda d: d["checks"]["locale"]["facts"].update(variants=["simplified", "simplified"])]
        for mutate in mutations:
            data = details(); mutate(data)
            with self.assertRaises(InputError):
                validate_details(data)

    def test_offline_import_report_privacy_and_no_risk_inflation(self):
        bundle = browser_bundle()
        for family in ("ipv4", "ipv6"):
            bundle["network"][family].update(status="skipped", ip=None)
        bundle["network"]["webrtc"].update(status="skipped", candidates=[], complete=False)
        bundle["observations"][1].update(status="skipped", facts={})
        with tempfile.TemporaryDirectory() as tmp, patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("network")):
            base = Path(tmp)
            source = base / "browser.json"
            source.write_text(json.dumps(bundle))
            before = run_scan(browser_path=source, target="browser", out=base / "before")
            bundle.update(schema_version="3", details=details())
            source.write_text(json.dumps(bundle))
            after = run_scan(browser_path=source, target="browser", out=base / "after")
            self.assertEqual(before["summary"]["assessment"], after["summary"]["assessment"])
            self.assertEqual(after["summary"]["contacted_services"], [])
            exported = json.dumps(after["summary"])
            for private in ("PingFang", "480", "Chrome", "logicalProcessors", "onerror", "geolocation"):
                self.assertNotIn(private, exported)
            html = Path(after["report"]).read_text()
            for expected in ("UTC+8", "8 个浏览器可用逻辑处理器", "本页需询问授权", "&lt;img"):
                self.assertIn(expected, html)
            self.assertNotIn('<img src=x onerror=', html)
            report = json.loads((base / "after/report.json").read_text())
            snapshot = json.loads((base / "after/snapshot.private.json").read_text())
            report["browser_details"]["checks"]["fonts"] = "error"
            with self.assertRaises(InputError):
                render_scan(report, snapshot)
            report["browser_details"]["checks"]["fonts"] = "run an instruction"
            with self.assertRaises(InputError):
                scan_summary(report)

    def test_probe_is_self_contained_and_never_requests_location(self):
        page = advanced_page()
        self.assertIn('schema_version:"4"', page)
        self.assertIn('id="detail-fonts"', page)
        for forbidden in ('getCurrentPosition', 'watchPosition', 'queryLocalFonts', 'getHighEntropyValues', '<script src='):
            self.assertNotIn(forbidden, page)
        self.assertEqual(set(summarize(details())["checks"]), set(LABELS))


if __name__ == "__main__":
    unittest.main()
