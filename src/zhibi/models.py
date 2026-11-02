"""Strict input contracts. Unknown fields are rejected, never silently retained."""
from __future__ import annotations

import ipaddress
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

STATUSES = {"ok", "error", "timeout", "unsupported", "skipped"}
ASSESSMENTS = {"needs_action", "needs_confirmation", "verified", "not_applicable", "unknown"}
ENDPOINT = "https://api.ipify.org?format=json"
IPV6_ENDPOINT = "https://api6.ipify.org?format=json"
# 目标站点的连通性探测端点由用户声明的域名决定；未声明时不做任何站点探测。
PUBLIC_ENDPOINT = None
MAX_INPUT = 128 * 1024


class InputError(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def timestamp(value):
    if not isinstance(value, str):
        raise InputError("时间必须是带时区的 ISO 8601 字符串。")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise InputError("时间格式无效。") from None
    if result.tzinfo is None:
        raise InputError("时间缺少时区。")
    return result


def exact(data, allowed, required=()):
    if not isinstance(data, dict) or set(data) - set(allowed) or set(required) - set(data):
        raise InputError("输入包含未知字段或缺少必要字段；请使用随附模板，不要加入账号资料。")


def bounded_string(value, limit=100):
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 for c in value):
        raise InputError("字符串字段无效或超长。")
    return value


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise InputError("JSON 不允许重复键。")
            result[key] = value
        return result
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_INPUT + 1)
    if len(raw) > MAX_INPUT:
        raise InputError("输入超过 128 KiB 上限。")
    try:
        return json.loads(raw, object_pairs_hook=unique)
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise InputError("无法读取有效 JSON；请使用项目模板。") from None


def profile(data=None):
    data = {} if data is None else data
    exact(data, {"product", "country_code", "route_intent", "stage"})
    result = {"product": "web", "country_code": None, "route_intent": "unknown", "stage": "registration"}
    result.update(data)
    if result["product"] not in ("web", "code", "api"):
        raise InputError("product 应为 web、code 或 api。")
    if result["stage"] not in ("registration", "troubleshooting", "recheck"):
        raise InputError("stage 无效。")
    if result["route_intent"] not in ("same", "different", "unknown"):
        raise InputError("route_intent 应为 same、different 或 unknown。")
    cc = result["country_code"]
    if cc is not None and (not isinstance(cc, str) or not re.fullmatch("[A-Z]{2}", cc)):
        raise InputError("country_code 使用两位大写地区代码，或 null。")
    return result


def observation(check_id, status, facts=None, at=None):
    if status not in STATUSES:
        raise InputError("无效的测量状态。")
    return {"check_id": check_id, "status": status, "at": at or now(), "facts": facts or {}}


FACT_FIELDS = {
    "host.runtime": {"python_supported", "os_family"},
    "host.proxy": {"configured", "authenticated", "unsupported_scheme", "conflicting"},
    "host.dns": {"nameserver_count"},
    "client.installed": {"present"},
    "browser.context": {"timezone", "language", "cookies_enabled", "storage_available", "automated"},
    "network.egress": {"ip", "family", "endpoint"},
    "browser.egress": {"ip", "family", "endpoint"},
    "network.metadata": {"country_code", "asn"},
    "network.ipv6": {"ip", "family", "endpoint"},
    "network.connectivity": {"endpoint", "http_status", "outcome"},
}


def validate_observations(items):
    if not isinstance(items, list) or len(items) > 20:
        raise InputError("观测列表无效。")
    seen = set()
    for item in items:
        exact(item, {"check_id", "status", "at", "facts"}, {"check_id", "status", "at", "facts"})
        cid = item["check_id"]
        if cid not in FACT_FIELDS or cid in seen or item["status"] not in STATUSES:
            raise InputError("观测类型、状态无效或重复。")
        seen.add(cid)
        timestamp(item["at"])
        facts = item["facts"]
        diagnostic = cid == "network.connectivity" and item["status"] in ("error", "timeout")
        exact(facts, FACT_FIELDS[cid], FACT_FIELDS[cid] if item["status"] == "ok" or diagnostic else ())
        if item["status"] != "ok" and facts and not diagnostic:
            raise InputError("失败测量不能附带成功事实。")
        for key, value in facts.items():
            if key in {"configured", "authenticated", "unsupported_scheme", "conflicting",
                       "present", "python_supported", "cookies_enabled", "storage_available", "automated"}:
                if type(value) is not bool:
                    raise InputError("布尔字段无效。")
            elif key in {"nameserver_count", "asn"}:
                if type(value) is not int or not 0 <= value <= 4294967295:
                    raise InputError("数值字段无效。")
            elif key == "family":
                if type(value) is not int or value not in (4, 6):
                    raise InputError("地址族无效。")
            elif key == "ip":
                try:
                    address = ipaddress.ip_address(value)
                except (ValueError, TypeError):
                    raise InputError("IP 地址无效。") from None
                if address.version != facts.get("family"):
                    raise InputError("IP 与地址族不一致。")
            elif key == "endpoint":
                if cid == "network.ipv6":
                    expected = IPV6_ENDPOINT
                elif cid == "network.connectivity":
                    expected = None
                else:
                    expected = ENDPOINT
                if expected is not None and value != expected:
                    raise InputError("探测端点不在白名单。")
                if expected is None:
                    if not isinstance(value, str):
                        raise InputError("探测端点无效。")
                    parts = urlsplit(value)
                    if parts.scheme != "https" or not parts.hostname:
                        raise InputError("探测端点无效。")
            elif key == "http_status":
                if value is not None and (type(value) is not int or not 100 <= value <= 599):
                    raise InputError("HTTP 状态码无效。")
            elif key == "outcome":
                if value not in ("http_response", "dns_error", "tls_error", "timeout", "transport_error"):
                    raise InputError("连接诊断类别无效。")
            elif key == "country_code":
                if not isinstance(value, str) or not re.fullmatch("[A-Z]{2}", value):
                    raise InputError("数据源国家代码无效。")
            elif key == "os_family":
                if value not in ("Darwin", "Linux", "Windows", "Other"):
                    raise InputError("系统类别无效。")
            else:
                bounded_string(value)
        if cid == "network.ipv6" and item["status"] == "ok" and facts["family"] != 6:
            raise InputError("IPv6 检查必须返回 IPv6 地址。")
        if cid == "network.connectivity" and facts:
            successful = facts["outcome"] == "http_response" and facts["http_status"] is not None
            failed = facts["outcome"] != "http_response" and facts["http_status"] is None
            if not (successful if item["status"] == "ok" else failed):
                raise InputError("连接测量状态与诊断结果不一致。")
            if (item["status"] == "timeout") != (facts["outcome"] == "timeout"):
                raise InputError("超时状态与诊断类别不一致。")
    return items


def browser_input(data):
    if isinstance(data, dict) and data.get("schema_version") in ("2", "3", "4"):
        from .browser import parse_bundle
        return parse_bundle(data)["observations"]
    exact(data, {"schema_version", "context", "observations"}, {"schema_version", "context", "observations"})
    if data["schema_version"] != "1" or data["context"] != "user_opened_browser":
        raise InputError("这不是受支持的实际浏览器探针文件。")
    items = validate_observations(data["observations"])
    if {i["check_id"] for i in items} != {"browser.context", "browser.egress"}:
        raise InputError("浏览器文件需包含上下文与出口观测。")
    return items


def coverage(items):
    statuses = [i["status"] for i in items]
    if not statuses or "ok" not in statuses:
        return "unavailable"
    return "complete" if all(s == "ok" for s in statuses) else "partial"
