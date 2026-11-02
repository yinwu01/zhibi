"""Synthetic, offline provider scenarios for documentation and Skill rehearsal."""
from copy import deepcopy

from .intelligence import QueryFailure
from .models import now, observation

RESPONSES = {
    "ipwhois": {"success": True, "ip": "8.8.8.8", "country_code": "US", "connection": {"asn": 64500, "org": "Synthetic Network A"}},
    "ipapi": {"ip": "8.8.8.8", "asn": {"asn": 64501, "org": "Synthetic Network B", "type": "hosting", "abuser_score": "0.0200 (Low)"},
              "company": {"name": "Synthetic Company", "abuser_score": "0.0100 (Low)"}, "location": {"country_code": "US"},
              "is_vpn": True, "is_proxy": False, "is_tor": False, "is_datacenter": True, "is_mobile": False, "is_abuser": False},
    "ipqs": {"success": True, "country_code": "US", "ASN": 64500, "organization": "Synthetic Network A", "connection_type": "Corporate",
             "fraud_score": 78, "proxy": False, "vpn": False, "tor": False, "recent_abuse": False, "mobile": False},
    "abuseipdb": {"data": {"ipAddress": "8.8.8.8", "countryCode": "US", "isp": "Synthetic Network A", "usageType": "Organization",
                           "abuseConfidenceScore": 0, "totalReports": 0, "numDistinctUsers": 0, "lastReportedAt": None, "isTor": False}},
}


class DemoTransport:
    enabled, metadata, ipv6, connectivity = True, False, False, False
    def __init__(self):
        self.flows = []
    def get(self, service, ip=None):
        if service != "ipify":
            raise AssertionError("Unexpected demo service")
        return {"ip": "8.8.8.8"}


class DemoClient:
    def __init__(self, scenario="conflicting-sources"):
        self.scenario, self.flows = scenario, []
    def fetch(self, provider, address, key=None):
        if self.scenario == "provider-outage":
            raise QueryFailure("quota_exceeded" if provider == "ipqs" else "timeout")
        if self.scenario == "missing-coverage" and provider == "ipapi":
            return {"ip": address, "asn": "AS64500 Synthetic Network", "company": "Synthetic Network", "docs": "https://ipapi.is/free-tier.html"}
        return deepcopy(RESPONSES[provider])


def run_demo(scenario, out=None):
    from .scan import run_scan
    from .demo import fixture
    def synthetic_collect(transport, browser):
        items = fixture("intentional-routing")["observations"]
        at = now()
        for item in items:
            item["at"] = at
            if item["check_id"] == "network.egress":
                item["facts"]["ip"] = "8.8.8.8"
        items += [observation("network.ipv6", "skipped", at=at),
                  observation("network.connectivity", "skipped", at=at)]
        return items
    return run_scan(network=True, providers=list(RESPONSES), out=out,
                    transport=DemoTransport(), client=DemoClient(scenario), keys={}, sample=True,
                    collector=synthetic_collect)
