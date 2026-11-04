import copy
import io
import json
import os
import socket
import ssl
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from zhibi.checks import collect
from zhibi.cli import main
from zhibi.demo import fixture
from zhibi.engine import bundle, evaluate
from zhibi.guidance import preparation, triage
from zhibi.history import timeline
from zhibi.models import InputError, IPV6_ENDPOINT, PUBLIC_ENDPOINT, observation, timestamp, validate_observations
from zhibi.research import render_learning_html, run_lab, theory, validate_knowledge
from zhibi.transport import NetworkError, Transport


class ResearchTests(unittest.TestCase):
    def test_graph_closure_and_provenance(self):
        counts = validate_knowledge()
        self.assertGreaterEqual(counts["claims"], counts["rules"])
        data = theory()
        nodes = {n["id"] for n in data["nodes"]}
        self.assertEqual(len(nodes), len(data["nodes"]))
        for edge in data["edges"]:
            self.assertIn(edge["from"], nodes)
            self.assertIn(edge["to"], nodes)
        self.assertEqual(data["status"], "research_framework")

    def test_unreviewed_claim_cannot_authorize_conclusion(self):
        data = fixture("intentional-routing")
        for field, value in (("status", "proposed"), ("status", "contradicted"), ("status", "retired"),
                             ("scope_kind", "cross_platform_analogy")):
            claims = bundle("claims")
            next(c for c in claims if c["id"] == "route-not-ban")[field] = value
            report = evaluate(data["observations"], data["profile"], at=timestamp(data["evaluated_at"]), claims=claims)
            self.assertEqual(next(f for f in report["findings"] if f["id"] == "network.route")["assessment"], "unknown")

    def test_missing_claim_fails_closed(self):
        with self.assertRaises(InputError):
            evaluate([], claims=[])
        claims = bundle("claims")
        claims[0]["sources"] = ["unknown-source"]
        with self.assertRaises(InputError):
            validate_knowledge(claims=claims)

    def test_claim_evidence_is_checked_even_if_not_listed_by_rule(self):
        data = fixture("intentional-routing")
        claims, sources = bundle("claims"), bundle("sources")
        next(c for c in claims if c["id"] == "route-not-ban")["sources"].append("distillation-feb")
        next(s for s in sources if s["id"] == "distillation-feb")["checked_at"] = "2025-01-01T00:00:00Z"
        report = evaluate(data["observations"], data["profile"], at=timestamp(data["evaluated_at"]),
                          claims=claims, sources=sources)
        finding = next(f for f in report["findings"] if f["id"] == "network.route")
        self.assertEqual(finding["assessment"], "unknown")
        self.assertIn("distillation-feb", finding["evidence_refs"])

    def test_web_and_api_errors_keep_product_scope(self):
        self.assertEqual(triage("http_403", "api")["category"], "permissions")
        self.assertEqual(triage("http_403", "web")["category"], "access_needs_confirmation")
        self.assertEqual(triage("http_429")["category"], "capacity_or_quota")
        self.assertEqual(triage("account_suspended")["category"], "reported_account_restriction")
        with self.assertRaises(InputError) as err:
            triage("SECRET_TOKEN")
        self.assertNotIn("SECRET_TOKEN", str(err.exception))

    def test_guide_is_incomplete_until_user_confirms(self):
        web, code = preparation(), preparation({"product": "code"})
        self.assertEqual(web["completion"], "not_recorded")
        self.assertNotIn("client-install", {s["id"] for s in web["steps"]})
        self.assertIn("client-install", {s["id"] for s in code["steps"]})

    def test_labs_preserve_environment_and_failure_meaning(self):
        before = dict(os.environ)
        with patch("urllib.request.OpenerDirector.open") as http:
            repair = run_lab("repair")
            routing = run_lab("routing")
            failure = run_lab("failure")
            http.assert_not_called()
        self.assertEqual(dict(os.environ), before)
        def status(run, key):
            return next(f["assessment"] for f in run["summary"]["findings"] if f["rule_id"] == key)
        self.assertEqual([status(r, "host.proxy") for r in repair["runs"]], ["needs_confirmation", "verified"])
        self.assertEqual([status(r, "network.route") for r in routing["runs"]], ["needs_confirmation", "verified"])
        self.assertEqual(failure["runs"][0]["summary"]["coverage"], "unavailable")
        self.assertEqual(repair["system_changes"], 0)

    def test_learning_page_has_no_active_remote_resources(self):
        html = render_learning_html()
        self.assertEqual(html.count('class="chapter"'), 6)
        self.assertIn("default-src 'none'", html)
        self.assertNotIn("<script", html)
        self.assertNotIn('<link', html)

    def test_cli_learning_and_guidance_outputs(self):
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(io.StringIO()):
            for command, suffix in ((["learn", "--format", "html"], ".html"),
                                    (["theory", "--format", "json"], ".json"),
                                    (["triage", "--signal", "http_403"], ".json"),
                                    (["guide"], ".md"), (["lab", "repair"], ".json")):
                target = Path(tmp) / (command[0] + suffix)
                self.assertEqual(main(command + ["--out", str(target)]), 0)
                self.assertGreater(target.stat().st_size, 100)

    def test_cli_remains_utf8_under_ascii_pipe_default(self):
        env = {**os.environ, "PYTHONIOENCODING": "ascii"}
        completed = subprocess.run([sys.executable, "-c",
                                   "from zhibi.cli import main; raise SystemExit(main(['guide']))"],
                                  env=env, capture_output=True)
        self.assertEqual(completed.returncode, 0)
        self.assertIn("知彼", completed.stdout.decode("utf-8"))


class ExtendedNetworkTests(unittest.TestCase):
    def test_ipv6_response_validates_family_and_optin(self):
        for address, state in (("2606:4700:4700::1111", "ok"), ("8.8.8.8", "error"), ("::1", "error")):
            transport = Transport(True, ipv6=True)
            with patch.object(transport, "get", return_value={"ip": address}):
                item = next(o for o in collect(transport) if o["check_id"] == "network.ipv6")
            self.assertEqual(item["status"], state)
        with patch("urllib.request.OpenerDirector.open") as call:
            with self.assertRaises(NetworkError):
                Transport(True).get("ipify6")
            call.assert_not_called()

    def test_inconsistent_diagnostics_rejected(self):
        for state, outcome, code in (("ok", "dns_error", None), ("error", "http_response", None),
                                     ("timeout", "dns_error", None), ("error", "timeout", None)):
            with self.assertRaises(InputError):
                validate_observations([observation("network.connectivity", state,
                                      {"endpoint": PUBLIC_ENDPOINT, "outcome": outcome, "http_status": code})])


class TimelineTests(unittest.TestCase):
    def snapshots(self):
        left, right = fixture("proxy-conflict"), fixture("proxy-corrected")
        right["evaluated_at"] = "2026-10-18T08:10:00+00:00"
        return [left, right]

    def test_comparison_requires_user_context_and_contains_no_raw_facts(self):
        samples = self.snapshots()
        self.assertEqual(timeline(samples)["comparisons"][0]["changes"], [])
        graph = timeline(samples, same_context=True)
        self.assertEqual(graph["comparisons"][0]["changes"],
                         [{"check_id": "host.proxy", "change": "observed_values_changed"}])
        serialized = json.dumps(graph)
        for sample in samples:
            for item in sample["observations"]:
                if "ip" in item["facts"]:
                    self.assertNotIn(item["facts"]["ip"], serialized)
        ids = {n["id"] for n in graph["nodes"]}
        self.assertTrue(all(e["from"] in ids and e["to"] in ids for e in graph["edges"]))

    def test_changed_intake_prevents_comparison(self):
        samples = self.snapshots()
        samples[1]["profile"]["route_intent"] = "different"
        self.assertEqual(timeline(samples, True)["comparisons"][0]["comparability"], "not_established")

    def test_same_time_and_mixed_sample_inputs_rejected(self):
        with self.assertRaises(InputError):
            timeline([fixture(), fixture()])
        samples = self.snapshots()
        samples[1] = {"profile": samples[1]["profile"], "observations": samples[1]["observations"],
                      "generated_at": samples[1]["evaluated_at"]}
        with self.assertRaises(InputError):
            timeline(samples)


if __name__ == "__main__":
    unittest.main()
