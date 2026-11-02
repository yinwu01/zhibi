import copy
import json
import tempfile
import unittest
from pathlib import Path

from zhibi.assessment import assess_scan
from zhibi.scan import interpret, interpret_paths, evidence_graph, validate_scan, scan_summary, render_scan
from zhibi.scan_demo import run_demo
from zhibi.models import ENDPOINT, IPV6_ENDPOINT


class AssessmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        result = run_demo("conflicting-sources", str(Path(self.temp.name) / "run"))
        self.report = json.loads((Path(result["directory"]) / "report.json").read_text())
        self.addCleanup(self.temp.cleanup)

    def decision(self, report):
        report["findings"] = interpret_paths(report["paths"]) + interpret(report["intelligence"])
        report["graph"] = evidence_graph(report["intelligence"], report["findings"], report["paths"])
        validate_scan(report)
        return assess_scan(report)

    def paths(self, intent="unknown", rtc="timeout"):
        at = self.report["generated_at"]
        return [
            {"id": "path:browser-ipv4", "status": "ok", "at": at, "endpoint": ENDPOINT,
             "automated": False, "matches_agent": False, "route_intent": intent},
            {"id": "path:browser-ipv6", "status": "error", "at": at, "endpoint": IPV6_ENDPOINT,
             "automated": False, "matches_agent": None, "route_intent": intent},
            {"id": "path:webrtc", "status": rtc, "at": at, "endpoint": "stun:stun.l.google.com:19302",
             "automated": False, "candidate_count": 0 if rtc == "timeout" else 1,
             "types": [] if rtc == "timeout" else ["srflx"], "complete": rtc == "ok",
             "https_relation": "unknown" if rtc == "timeout" else "different"}]

    def test_identity_only_and_route_difference_do_not_become_user_faults(self):
        report = self.report
        report["intelligence"] = report["intelligence"][:1]
        report["paths"] = self.paths()
        decision = self.decision(report)
        self.assertEqual(decision["status"], "incomplete")
        self.assertIn("IP 信誉检测未完成", decision["headline"])
        self.assertEqual(decision["user_actions"], [])
        self.assertFalse(any(r["kind"] == "review" for r in decision["conclusions"]))
        self.assertTrue(any("WebRTC" in g for g in decision["tool_gaps"]))
        self.assertTrue(any("IP 信誉" in g for g in decision["tool_gaps"]))
        self.assertIn("不要求更换 IP", decision["recommendation"])
        table = {r["label"]: r for r in decision["overview"]["table_rows"]}
        for label in ("IP 信誉", "历史记录", "浏览器直连检查"):
            self.assertEqual(table[label]["result"], "未完成")
        self.assertEqual(table["IPv6 出站策略"]["result"], "待确认")
        self.assertIn("禁用 IPv6 出站", table["IPv6 出站策略"]["advice"])

    def test_declared_same_route_changes_the_action_but_not_missing_coverage(self):
        self.report["intelligence"] = self.report["intelligence"][:1]
        self.report["paths"] = self.paths("same")
        decision = self.decision(self.report)
        self.assertEqual(decision["status"], "attention")
        self.assertTrue(any("共用出口预期" in a for a in decision["user_actions"]))
        self.assertTrue(any("IP 信誉" in g for g in decision["tool_gaps"]))

    def test_actual_webrtc_mismatch_is_actionable_but_timeout_is_not(self):
        self.report["intelligence"] = self.report["intelligence"][:1]
        self.report["paths"] = self.paths(rtc="ok")
        decision = self.decision(self.report)
        self.assertEqual(decision["status"], "attention")
        self.assertTrue(any("WebRTC" in a for a in decision["user_actions"]))
        direct = next(r for r in decision["overview"]["table_rows"] if r["label"] == "浏览器直连检查")
        self.assertEqual(direct["result"], "需注意")

    def test_conflicting_vpn_labels_are_not_resolved_by_majority(self):
        decision = self.decision(self.report)
        vpn = next(r for r in decision["conclusions"] if r["id"] == "agent-ipv4:vpn")
        self.assertEqual(vpn["kind"], "review")
        self.assertIn("来源结论冲突", vpn["verdict"])
        self.assertIn("来源冲突", decision["headline"])
        self.assertIn("VPN", decision["overview"]["checks"][1]["detail"])
        self.assertIn("IPQS", decision["overview"]["checks"][1]["detail"])

    def test_ipqs_documented_boundaries_do_not_become_ban_odds(self):
        original = copy.deepcopy(self.report["intelligence"][2])
        for value, kind, expected in ((0, "result", "低于"), (74, "result", "低于"),
                                      (75, "review", "可疑阈值"), (89, "review", "可疑阈值"),
                                      (90, "review", "高风险阈值"), (100, "review", "高风险阈值")):
            with self.subTest(value=value):
                report = copy.deepcopy(self.report)
                record = copy.deepcopy(original)
                record["facts"]["scores"][0]["value"] = value
                report["intelligence"] = [record]
                decision = self.decision(report)
                score = next(r for r in decision["conclusions"] if r["id"].endswith(":fraud_score"))
                self.assertEqual(score["kind"], kind)
                self.assertIn(expected, score["verdict"])
                self.assertNotIn("封号概率", score["verdict"])
                if value >= 75:
                    self.assertEqual(decision["status"], "attention")
                    self.assertEqual(decision["overview"]["status"], "attention")
                    self.assertEqual(decision["overview"]["checks"][1]["state"], "attention")
                    self.assertNotIn("不要求更换", decision["recommendation"])

    def test_zero_reports_stays_zero_and_no_measurement_never_passes(self):
        self.report["intelligence"] = [self.report["intelligence"][3]]
        decision = self.decision(self.report)
        reports = next(r for r in decision["conclusions"] if r["id"].endswith(":reports"))
        self.assertIn("0 条举报", reports["verdict"])
        self.assertEqual(reports["kind"], "result")
        self.report["subjects"] = []
        self.report["intelligence"] = []
        decision = self.decision(self.report)
        self.assertEqual(decision["status"], "incomplete")
        self.assertIn("没有取得有效出口", decision["headline"])

    def test_html_and_agent_lead_with_same_decision_without_private_data(self):
        self.report["intelligence"] = self.report["intelligence"][:1]
        decision = self.decision(self.report)
        summary = scan_summary(self.report)
        page = render_scan(self.report)
        self.assertEqual(summary["assessment"], decision)
        self.assertEqual(summary["format"], "zhibi-scan-summary-2")
        self.assertNotIn("baseline", summary)
        self.assertNotIn("findings", summary)
        self.assertLess(page.index(decision["overview"]["headline"]), page.index('id="evidence"'))
        self.assertLess(page.index(decision["overview"]["next_step"]), page.index('id="evidence"'))
        self.assertEqual(decision["overview"]["pending_count"], len(decision["tool_gaps"]))
        front = page.split('<details id="evidence">')[0].split('<body>')[1]
        for technical in ("ASN", "国家代码", "诊断端点", "AS64500", "Synthetic Network", "0 / 100"):
            self.assertNotIn(technical, front)
        self.assertNotIn('<details id="evidence" open', page)
        self.assertEqual(front.count('<table '), 1)
        self.assertIn('<th scope="col">检查项</th><th scope="col">结果</th><th scope="col">建议</th>', front)
        self.assertEqual(sum(decision["overview"]["counts"].values()), len(decision["overview"]["table_rows"]))
        for private in ("8.8.8.8", "Synthetic Network", "userAgent"):
            self.assertNotIn(private, json.dumps(summary))

    def test_unselected_webrtc_is_not_a_user_task_or_a_measurement_gap(self):
        self.report["paths"] = self.paths(rtc="timeout")
        self.report["paths"][-1]["status"] = "skipped"
        decision = self.decision(self.report)
        self.assertFalse(any("WebRTC" in g for g in decision["tool_gaps"]))
        self.assertFalse(any(r["label"] == "浏览器直连检查" for r in decision["overview"]["table_rows"]))

    def test_next_operation_does_not_turn_missing_measurements_into_configuration(self):
        self.report["subjects"] = []
        self.report["intelligence"] = []
        decision = self.decision(self.report)
        self.assertEqual(decision["overview"]["next_action"]["id"], "collect_exit")
        self.report["subjects"] = [{"id": "agent-ipv4", "family": 4,
                                    "measured_at": self.report["generated_at"], "endpoint": ENDPOINT}]
        decision = self.decision(self.report)
        self.assertEqual(decision["overview"]["next_action"]["id"], "retry_intelligence")


if __name__ == "__main__":
    unittest.main()
