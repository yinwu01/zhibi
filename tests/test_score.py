"""Scoring must stay honest: unmeasured is never a pass, and one dimension cannot fake another."""
import unittest

from zhibi import score as s


GOOD_FACTS = {"tz": "Europe/Berlin", "lc_all": "en_US.UTF-8", "ntp": "yes", "systemd": "yes"}
BAD_FACTS = {"tz": "UTC", "lc_all": "C", "ntp": "no", "systemd": "yes"}


class EgressTests(unittest.TestCase):
    def test_datacenter_org_is_background(self):
        dim = s.egress_dimension({"org": "AS14061 DigitalOcean, LLC"})
        self.assertTrue(dim["reasons"])
        self.assertEqual(dim["state"], "not_measured")
        self.assertEqual(s.looks_datacenter("AS14061 DigitalOcean, LLC"), True)

    def test_residential_org_is_not_flagged(self):
        self.assertFalse(s.looks_datacenter("China Telecom Broadband"))
        self.assertEqual(s.egress_dimension({"org": "China Telecom Broadband"})["state"], "not_measured")

    def test_unknown_org_is_not_measured_not_pass(self):
        dim = s.egress_dimension({})
        self.assertEqual(dim["state"], "not_measured")
        self.assertEqual(dim["score"], 0)


class DimensionTests(unittest.TestCase):
    def test_consistency_full_match(self):
        dim = s.consistency_dimension(GOOD_FACTS, "Europe/Berlin", "en_US.UTF-8")
        self.assertEqual(dim["state"], "ok")

    def test_consistency_mismatch_fails(self):
        dim = s.consistency_dimension(BAD_FACTS, "Europe/Berlin", "en_US.UTF-8")
        self.assertEqual(dim["state"], "fail")
        self.assertTrue(dim["fix"])

    def test_dns_leak_alone_lowers_leakage(self):
        dim = s.leakage_dimension({"nameservers": ["8.8.8.8"], "public": {"8.8.8.8"}})
        self.assertEqual(dim["state"], "not_measured")
        self.assertLess(dim["score"], 80)

    def test_webrtc_leak_is_worst_case(self):
        dim = s.leakage_dimension({"nameservers": ["10.0.0.1"], "public": set()},
                                  {"leak": True})
        self.assertEqual(dim["state"], "fail")

    def test_no_leak_measurement_is_unmeasured(self):
        dim = s.leakage_dimension()
        self.assertEqual(dim["state"], "not_measured")

    def test_reputation_optional_stays_unmeasured(self):
        self.assertEqual(s.reputation_dimension({})["state"], "not_measured")
        self.assertEqual(s.reputation_dimension({"score": 92})["state"], "ok")

    def test_unknown_provider_never_becomes_residential(self):
        dim = s.egress_dimension({"org": "Unrecognized Organization"})
        self.assertEqual(dim["state"], "not_measured")
        self.assertIn("未知类型", dim["reasons"][0])

    def test_systemd_available_is_not_running_service(self):
        self.assertEqual(s.stability_dimension(facts={"systemd": "yes"})["state"], "not_measured")

    def test_missing_values_are_not_mismatches(self):
        self.assertEqual(s.consistency_dimension({}, "Europe/Berlin", "en_US.UTF-8")["state"], "not_measured")

    def test_stability_requires_service_evidence(self):
        self.assertEqual(s.stability_dimension()["state"], "not_measured")
        dim = s.stability_dimension({"active": False, "enabled": False}, {"systemd": "yes"})
        self.assertEqual(dim["state"], "fail")


class AggregateTests(unittest.TestCase):
    def test_clean_profile_scores_low(self):
        result = s.score(egress={"org": "China Telecom"}, facts=GOOD_FACTS,
                         expect_tz="Europe/Berlin", expect_locale="en_US.UTF-8",
                         dns={"nameservers": ["10.0.0.1"], "public": set()},
                         webrtc={"leak": False}, reputation={"score": 90},
                         service={"active": True, "enabled": True})
        self.assertEqual(result["level"], "low")
        self.assertGreaterEqual(result["score"], 80)
        self.assertEqual(result["high_risk"], [])

    def test_dirty_profile_is_high_risk_with_reasons(self):
        result = s.score(egress={"org": "DigitalOcean"}, facts=BAD_FACTS,
                         expect_tz="Europe/Berlin", expect_locale="en_US.UTF-8",
                         dns={"nameservers": ["8.8.8.8"], "public": {"8.8.8.8"}},
                         webrtc={"leak": True}, service={"active": False, "enabled": False})
        self.assertEqual(result["level"], "high")
        ids = {item["id"] for item in result["high_risk"]}
        self.assertTrue({"consistency", "leakage"} <= ids)

    def test_missing_evidence_never_becomes_low(self):
        result = s.score()
        self.assertEqual(result["level"], "insufficient")
        self.assertEqual(result["score"], 0)
        self.assertEqual(len(result["unmeasured"]), 5)

    def test_coverage_reflects_measured_weight(self):
        result = s.score(facts=GOOD_FACTS, expect_tz="Europe/Berlin")
        self.assertEqual(result["coverage"], 25)
        self.assertIn("not_measured", {d["state"] for d in result["dimensions"]})

    def test_score_always_carries_its_limits(self):
        result = s.score(facts=GOOD_FACTS)
        self.assertIn("不代表任何服务端的判断", result["notice"])


if __name__ == "__main__":
    unittest.main()
