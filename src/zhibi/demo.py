"""Reproducible synthetic fixtures; never describes a real user's account."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from .models import ENDPOINT, observation

SCENARIOS = ("route-mismatch", "intentional-routing", "measurement-failure", "stale-policy",
             "proxy-conflict", "proxy-corrected")


def fixture(scenario="route-mismatch"):
    at = datetime(2026, 10, 18, 8, 0, tzinfo=timezone.utc)
    when = at.isoformat()
    items = [
        observation("host.runtime", "ok", {"python_supported": True, "os_family": "Darwin"}, when),
        observation("host.proxy", "ok", {"configured": True, "authenticated": False,
                    "unsupported_scheme": False, "conflicting": False}, when),
        observation("host.dns", "ok", {"nameserver_count": 1}, when),
        observation("client.installed", "ok", {"present": False}, when),
        observation("browser.context", "ok", {"timezone": "Asia/Taipei", "language": "zh-CN",
                    "cookies_enabled": True, "storage_available": True, "automated": False}, when),
        observation("browser.egress", "ok", {"ip": "198.51.100.20", "family": 4, "endpoint": ENDPOINT}, when),
        observation("network.egress", "ok", {"ip": "203.0.113.10", "family": 4, "endpoint": ENDPOINT}, when),
        observation("network.metadata", "skipped", at=when),
    ]
    context = {"product": "web", "country_code": None, "route_intent": "unknown", "stage": "registration"}
    if scenario == "intentional-routing":
        context["route_intent"] = "different"
    elif scenario == "measurement-failure":
        items = [observation(i["check_id"], "timeout", at=when) for i in items]
    elif scenario == "stale-policy":
        at += timedelta(days=100)
    elif scenario in ("proxy-conflict", "proxy-corrected"):
        from .checks import proxy_check
        synthetic_env = {"https_proxy": "http://127.0.0.1:8080", "HTTPS_PROXY": "http://127.0.0.1:9090"}
        if scenario == "proxy-corrected":
            synthetic_env["HTTPS_PROXY"] = synthetic_env["https_proxy"]
        items[1] = proxy_check(synthetic_env)
        items[1]["at"] = when
    elif scenario != "route-mismatch":
        raise ValueError("未知示例场景。")
    return {"schema_version": "1", "sample": True, "profile": context,
            "observations": deepcopy(items), "evaluated_at": at.isoformat()}
