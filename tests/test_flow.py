"""The delivery folder and the user-facing wording are the product surface. Test both."""
import json
import tempfile
import unittest
from pathlib import Path

from zhibi import flow, remote, score as s

FACTS = {"os": "Ubuntu 24.04", "tz": "Europe/Berlin", "lc_all": "en_US.UTF-8", "ntp": "yes",
         "systemd": "yes", "nameservers": "10.0.0.1 ", "egress_ip": "203.0.113.9",
         "egress_org": "Example Telecom Broadband", "nproc": "2", "mem_mb": "2048"}


def build_report():
    result = s.score(egress=flow._egress(FACTS), facts=FACTS, expect_tz="Europe/Berlin",
                     expect_locale="en_US.UTF-8", dns=flow._dns(FACTS),
                     service={"active": True, "enabled": True})
    return {"host": "203.0.113.9", "at": "2026-11-05T00:00:00Z", "facts": FACTS,
            "score": result, "remote": {"checks": []}, "headline": flow._headline({"score": result})}


class HeadlineTests(unittest.TestCase):
    def test_headline_is_three_plain_sentences(self):
        lines = flow._headline(build_report())
        self.assertEqual(len(lines), 3)
        self.assertIn("总体判断", lines[0])

    def test_headline_never_leaks_internal_ids(self):
        report = build_report()
        text = " ".join(flow._headline(report))
        for identifier in ("reputation", "not_measured", "consistency", "leakage"):
            self.assertNotIn(identifier, text)

    def test_headline_names_missing_items_in_chinese(self):
        text = " ".join(flow._headline(build_report()))
        self.assertIn("信誉读数", text)
        self.assertIn("不算通过", text)

    def test_insufficient_evidence_refuses_a_verdict(self):
        result = s.score()
        lines = flow._headline({"score": result})
        self.assertIn("先不下结论", lines[0])


class DeliverTests(unittest.TestCase):
    def test_folder_contains_everything_the_user_keeps(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "out"
            flow.deliver_files(folder, build_report(), unit="svc",
                               timezone="Europe/Berlin", locale="en_US.UTF-8")
            names = sorted(p.name for p in folder.iterdir())
            self.assertEqual(names, sorted(["先读我.md", "报告.html", "verification.json",
                                            "remote.md", "browser.md", "reproduce.sh",
                                            "rollback.sh"]))

    def test_scripts_are_executable_and_reference_the_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "out"
            flow.deliver_files(folder, build_report(), unit="svc",
                               timezone="Europe/Berlin", locale="en_US.UTF-8")
            reproduce = (folder / "reproduce.sh").read_text()
            self.assertIn("zhibi check --host 203.0.113.9", reproduce)
            rollback = (folder / "rollback.sh").read_text()
            self.assertIn("systemctl disable --now svc", rollback)

    def test_readme_states_the_stop_command_and_no_guarantee(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "out"
            flow.deliver_files(folder, build_report(), unit="svc",
                               timezone="Europe/Berlin", locale="en_US.UTF-8")
            text = (folder / "先读我.md").read_text()
            self.assertIn("systemctl stop svc", text)
            self.assertNotIn("不会被限制", text)

    def test_html_is_self_contained(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "out"
            flow.deliver_files(folder, build_report(), unit="svc",
                               timezone="Europe/Berlin", locale="en_US.UTF-8")
            html = (folder / "报告.html").read_text()
            self.assertNotIn("http://", html)
            self.assertNotIn("https://", html)
            self.assertIn("环境准备记录", html)

    def test_existing_folder_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "out"
            flow.deliver_files(folder, build_report(), unit="svc",
                               timezone="Europe/Berlin", locale="en_US.UTF-8")
            with self.assertRaises(FileExistsError):
                flow.deliver_files(folder, build_report(), unit="svc",
                                   timezone="Europe/Berlin", locale="en_US.UTF-8")


class RemoteContractTests(unittest.TestCase):
    def test_facts_parse_and_findings_flag_public_dns(self):
        text = "tz=UTC\nntp=no\nnameservers=8.8.8.8 \nlocales=3\nsystemd=yes\n"
        facts = remote.parse_facts(text)
        keys = {item["key"]: item["state"] for item in remote.findings(facts)}
        self.assertEqual(keys["remote.dns"], "fail")
        self.assertEqual(keys["remote.clock"], "changed_unverified")

    def test_wrap_rejects_newline_injection(self):
        with self.assertRaises(Exception):
            remote.unit("svc", "ok\nExecStart=/bin/sh")

    def test_wrap_unit_uses_the_users_command_verbatim(self):
        body = remote.unit("svc", "/usr/bin/env codex --profile work")
        self.assertIn("ExecStart=/usr/bin/env codex --profile work", body)
        self.assertIn("Restart=always", body)

    def test_verify_marks_missing_service_as_unmeasured(self):
        result = remote.verify(FACTS, "Europe/Berlin", "en_US.UTF-8")
        unit = [c for c in result["checks"] if c["key"] == "unit"][0]
        self.assertEqual(unit["state"], "not_measured")


if __name__ == "__main__":
    unittest.main()
