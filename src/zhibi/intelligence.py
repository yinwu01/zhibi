"""Opt-in IP intelligence. Provider semantics stay separate; no aggregate risk score."""
from __future__ import annotations

import getpass
import ipaddress
import json
import math
import os
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
import warnings
from datetime import datetime, timezone
from pathlib import Path

from .models import InputError, exact, now, read_json, timestamp
from .transport import NoRedirect

PROVIDERS = {
    "ipwhois": {"name": "IPWhois", "host": "ipwho.is", "key": None,
        "docs": "https://ipwhois.io/documentation", "purpose": "network_identity",
        "key_required": False, "upstream_sources": [], "profile": {}},
    "ipapi": {"name": "ipapi.is", "host": "api.ipapi.is", "key": "ZHIBI_IPAPI_KEY",
        "docs": "https://ipapi.is/developers.html", "purpose": "proxy_and_network_intelligence",
        "key_required": False, "upstream_sources": [], "profile": {"all_companies": False}},
    "ipqs": {"name": "IPQualityScore", "host": "www.ipqualityscore.com", "key": "ZHIBI_IPQS_KEY",
        "docs": "https://www.ipqualityscore.com/documentation/proxy-detection-api/response-parameters",
        "purpose": "ip_fraud_intelligence", "key_required": True, "upstream_sources": [],
        "profile": {"strictness": 0, "allow_public_access_points": True}},
    "abuseipdb": {"name": "AbuseIPDB", "host": "api.abuseipdb.com", "key": "ZHIBI_ABUSEIPDB_KEY",
        "docs": "https://docs.abuseipdb.com/#check-endpoint", "purpose": "abuse_reports",
        "key_required": True, "upstream_sources": ["ipinfo:geolocation"],
        "profile": {"maxAgeInDays": 30, "verbose": False}},
    "proxycheck": {"name": "ProxyCheck", "host": "proxycheck.io", "key": None,
        "docs": "https://proxycheck.io/api/", "purpose": "proxy_risk_and_attack_history",
        "key_required": False, "upstream_sources": [], "profile": {"ver": "24-June-2026", "tag": 0}},
    "ipquery": {"name": "IPQuery", "host": "api.ipquery.io", "key": None,
        "docs": "https://ipquery.io/", "purpose": "proxy_and_risk_intelligence",
        "key_required": False, "upstream_sources": [], "profile": {}},
    "stopforumspam": {"name": "StopForumSpam", "host": "api.stopforumspam.org", "key": None,
        "docs": "https://www.stopforumspam.com/usage", "purpose": "forum_spam_reports",
        "key_required": False, "upstream_sources": [], "profile": {"json": True}},
}
from .extra_intelligence import SPECS as EXTRA_PROVIDERS
PROVIDERS.update(EXTRA_PROVIDERS)

# This preset works without accounts. Keyed services remain an explicit addition.
FREE_REPUTATION = ("ipwhois", "proxycheck", "ipquery", "stopforumspam")
KEY_SIGNUP = {
    "ipqs": "https://www.ipqualityscore.com/create-account",
    "abuseipdb": "https://www.abuseipdb.com/register?plan=free",
    "ipapi": "https://ipapi.is/app/signup",
}
OPTIONAL_CAPABILITIES = {
    "ipqs": "IPQS 欺诈分、代理标签与近期滥用标记",
    "abuseipdb": "最近 30 天举报数、独立举报者数与最近举报时间",
    "ipapi": "额外的代理标签、公司与 ASN 网段滥用比例",
}
FLAG_FIELDS = ("vpn", "proxy", "tor", "hosting", "mobile", "recent_abuse", "active_vpn", "active_tor")
STATES = {"ok", "partial", "missing_key", "quota_exceeded", "auth_error", "timeout", "error",
          "invalid_response", "skipped", "blocked_dependency"}
MAX_RESPONSE = 128 * 1024


def public_ip(value):
    try:
        address = ipaddress.ip_address(value)
    except (ValueError, TypeError):
        raise InputError("需要有效的公网 IP 地址。") from None
    if not address.is_global or address.is_multicast:
        raise InputError("情报查询仅接受公网单播 IP，不接受内网、文档或保留地址。")
    return str(address)


def config_path():
    return Path.home() / ".zhibi" / "providers.json"


def load_keys(path=None, include_environment=True):
    """Read only our explicitly defined key store, never account or browser files."""
    path = Path(path) if path else config_path()
    keys = {}
    if path.is_symlink():
        raise InputError("情报密钥文件不能是符号链接。")
    if path.exists():
        if os.name == "posix" and path.stat().st_mode & 0o077:
            raise InputError("情报密钥文件权限过宽；请在本地将其设为 600。")
        data = read_json(path)
        if not isinstance(data, dict) or set(data) - set(PROVIDERS):
            raise InputError("情报密钥文件格式无效。")
        keys.update(data)
    for name, spec in PROVIDERS.items():
        if include_environment and spec["key"] and os.environ.get(spec["key"]):
            keys[name] = os.environ[spec["key"]]
    if any(not PROVIDERS[name]["key"] or not isinstance(key, str) or not 1 <= len(key) <= 512
           or not key.isascii() or any(c.isspace() or ord(c) < 33 or ord(c) > 126 for c in key)
           for name, key in keys.items()):
        raise InputError("情报密钥格式无效；值不会写入日志。")
    return keys


def configure(name, skip_empty=False):
    if name not in PROVIDERS or not PROVIDERS[name]["key"]:
        raise InputError("该来源不需要配置密钥。")
    target = config_path()
    if target.parent.is_symlink() or target.is_symlink():
        raise InputError("密钥目录不能是符号链接。")
    current = load_keys(target, include_environment=False)
    try:
        with warnings.catch_warnings():
            # Never let getpass fall back to echoed input in a captured tool session.
            warnings.simplefilter("error", getpass.GetPassWarning)
            field = "username:api-key" if name.startswith("scamalytics") else "API Key"
            key = getpass.getpass("在自己的终端粘贴 " + field + "（隐藏输入，不要发到聊天）：").strip()
    except (getpass.GetPassWarning, EOFError):
        raise InputError("无法隐藏输入；请在自己的交互式终端运行 configure，未保存密钥。") from None
    if not key and skip_empty:
        return {"provider": name, "configured": False, "skipped": True}
    if not key or not key.isascii() or len(key) > 512 or any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise InputError("密钥为空或格式无效；未保存。")
    if name.startswith("scamalytics"):
        username, separator, secret = key.partition(":")
        if not separator or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", username) or not secret:
            raise InputError("Scamalytics 需要 username:api-key 格式，并选择账户对应的 EU/US 节点；未保存。")
    current[name] = key
    target.parent.mkdir(mode=0o700, exist_ok=True)
    from .storage import write
    import secrets
    temporary = target.parent / (".providers-" + secrets.token_hex(8))
    try:
        write(temporary, current)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {"provider": name, "configured": True, "stored_locally": True}


def configure_all():
    """Prompt only for missing keys; never print, transmit or overwrite existing keys."""
    results = []
    keys = load_keys()
    print("依次配置三家免费账户的 Key。回车可跳过；已配置的来源会保留。此步骤不联网验证。")
    for name, url in KEY_SIGNUP.items():
        print("\n" + PROVIDERS[name]["name"] + " · 注册：" + url)
        if keys.get(name):
            print("已配置，保留现有 Key。")
            results.append({"provider": name, "configured": True, "unchanged": True})
        else:
            result = configure(name, skip_empty=True)
            print("已保存到本机。" if result["configured"] else "已跳过，尚未配置。")
            results.append(result)
    return {"providers": results, "network_validation": False}


def catalog(keys=None):
    keys = {} if keys is None else keys
    notes = {
        "proxycheck": "免 Key 100 次/日；代理标签、风险分和可用活动记录。免费 Key 可升至 1000 次/日；本适配器只用免 Key 接口。",
        "ipquery": "免 Key 公共接口；代理标签和原始风险分，受限流约束。",
        "stopforumspam": "免 Key 只读查询；论坛垃圾信息库命中和频次，不代表全网滥用历史。",
        "ipapi": "免 Key 30 次/日仅精简归属；免费 Key 1000 次/日含标签和网段滥用比例。",
        "ipqs": "需自己的 Key；免费账户每月 1000 credits，高级字段依套餐。",
        "abuseipdb": "需自己的 Key；免费个人方案每日 1000 次 Check/Report。",
    }
    from .extra_intelligence import NOTES
    notes.update(NOTES)
    return [{"id": name, **{k: v for k, v in spec.items() if k != "key"},
             "key_environment_variable": spec["key"], "configured": bool(keys.get(name)),
             "coverage_note": notes.get(name, "公开归属查询；受服务限额和使用条件约束。")}
            for name, spec in PROVIDERS.items()]


class QueryFailure(Exception):
    def __init__(self, state):
        self.state = state
        super().__init__(state)


class Client:
    """Fixed hosts, one request per provider/subject, no redirects, logs or retries."""
    def __init__(self, enabled=False, timeout=8, opener=None):
        self.enabled, self.timeout = enabled, timeout
        self.opener = opener or urllib.request.build_opener(NoRedirect())
        self.attempted, self.flows = set(), []

    def fetch(self, provider, address, key=None):
        if not self.enabled or provider not in PROVIDERS:
            raise QueryFailure("skipped")
        address = public_ip(address)
        identity = (provider, address)
        if identity in self.attempted or len(self.attempted) >= 2 * len(PROVIDERS):
            raise QueryFailure("quota_exceeded")
        spec = PROVIDERS[provider]
        if spec["key_required"] and not key:
            raise QueryFailure("missing_key")
        headers = {"User-Agent": "Zhibi/0.2", "Accept": "application/json"}
        body = None
        if provider in EXTRA_PROVIDERS:
            from .extra_intelligence import request
            url, body = request(provider, address, key, headers)
        elif provider == "ipwhois":
            url = "https://ipwho.is/" + urllib.parse.quote(address, safe="")
        elif provider == "proxycheck":
            url = "https://proxycheck.io/v3/" + urllib.parse.quote(address, safe="") + "?" + urllib.parse.urlencode(spec["profile"])
        elif provider == "ipquery":
            url = "https://api.ipquery.io/" + urllib.parse.quote(address, safe="")
        elif provider == "stopforumspam":
            url = "https://api.stopforumspam.org/api?" + urllib.parse.urlencode({"ip": address, "json": ""})
        elif provider == "ipapi":
            url = "https://api.ipapi.is/"
            data = {"q": address}
            if key:
                data["key"] = key
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
        elif provider == "ipqs":
            url = "https://www.ipqualityscore.com/api/json/ip/"
            headers.update({"Content-Type": "application/json", "ipqs-key": key})
            body = json.dumps({"ip": address, **spec["profile"]}).encode()
        elif provider == "abuseipdb":
            url = "https://api.abuseipdb.com/api/v2/check?" + urllib.parse.urlencode(
                {"ipAddress": address, "maxAgeInDays": spec["profile"]["maxAgeInDays"]})
            headers["Key"] = key
        else:
            raise QueryFailure("skipped")
        self.attempted.add(identity)
        self.flows.append({"provider": provider, "recipient": spec["host"], "sent": True,
                           "fields": ["request_source_ip", "queried_ip", "query_profile"] + (["provider_api_key"] if key else [])})
        try:
            request = urllib.request.Request(url, data=body, headers=headers)
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read(MAX_RESPONSE + 1)
            if len(raw) > MAX_RESPONSE:
                raise QueryFailure("invalid_response")
            def unique(pairs):
                result = {}
                for k, v in pairs:
                    if k in result:
                        raise ValueError()
                    result[k] = v
                return result
            result = json.loads(raw, object_pairs_hook=unique,
                                parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if not isinstance(result, dict):
                raise QueryFailure("invalid_response")
            return result
        except urllib.error.HTTPError as exc:
            state = "quota_exceeded" if exc.code in (402, 429) else "auth_error" if exc.code in (401, 403) else "error"
            if exc.fp is not None:
                exc.close()
            raise QueryFailure(state) from None
        except (TimeoutError, socket.timeout):
            raise QueryFailure("timeout") from None
        except urllib.error.URLError as exc:
            raise QueryFailure("timeout" if isinstance(exc.reason, (TimeoutError, socket.timeout)) else "error") from None
        except (OSError, ValueError, UnicodeError, RecursionError):
            raise QueryFailure("invalid_response") from None


def number(value, maximum=4294967295, integer=False):
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= maximum or (integer and type(value) is not int):
        raise QueryFailure("invalid_response")
    return value


def text(value):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 300 or any(ord(c) < 32 for c in value):
        raise QueryFailure("invalid_response")
    return value


def country(value):
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch("[A-Za-z]{2}", value):
        raise QueryFailure("invalid_response")
    return value.upper()


def flag(value):
    if value is not None and type(value) is not bool:
        raise QueryFailure("invalid_response")
    return value


def mapping(value):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise QueryFailure("invalid_response")
    return value


def as_number(value):
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"AS\d+", value):
        raise QueryFailure("invalid_response")
    return number(int(value[2:]), integer=True)


def provider_time(value):
    if value is None:
        return None
    if type(value) is int:
        return datetime.fromtimestamp(number(value), timezone.utc).isoformat()
    return timestamp(value).isoformat()


def activity_fields(data):
    """Null attack history is unavailable, not an invented zero count."""
    detection = mapping(data.get("detections"))
    history = data.get("attack_history")
    if history is not None:
        if not isinstance(history, dict) or len(history) > 64:
            raise QueryFailure("invalid_response")
        for name, count in history.items():
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", name) or count is None:
                raise QueryFailure("invalid_response")
            number(count, integer=True)
    return {"attack_counts": history,
            "detection_confidence": number(detection.get("confidence"), 100),
            "first_seen": provider_time(detection.get("first_seen")),
            "last_seen": provider_time(detection.get("last_seen")),
            "times_seen": number(detection.get("times_seen"), integer=True)}


def spam_fields(data):
    appears, count, last = data.get("appears"), data.get("frequency"), data.get("lastseen")
    if type(appears) is not int or appears not in (0, 1) or count is None:
        raise QueryFailure("invalid_response")
    number(count, integer=True)
    if bool(appears) != (count > 0):
        raise QueryFailure("invalid_response")
    if last is not None:
        # SFS supplies a wall-clock string, without an offset. Do not invent UTC.
        if not isinstance(last, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", last):
            raise QueryFailure("invalid_response")
        datetime.strptime(last, "%Y-%m-%d %H:%M:%S")
    return {"listed": bool(appears), "frequency": count, "last_seen": last}


def parse(provider, data, address):
    """Explicit allowlist: upstream free text, IDs, coordinates and contacts are dropped."""
    facts = {"country_code": None, "asn": None, "organization": None, "network_type": None,
             "flags": {key: None for key in FLAG_FIELDS}, "scores": [], "total_reports": None,
             "distinct_reporters": None, "last_reported_at": None}
    if provider in EXTRA_PROVIDERS:
        from .extra_intelligence import parse as parse_extra
        return parse_extra(provider, data, address, facts)
    if provider in ("ipwhois", "ipapi"):
        if data.get("success") is False or data.get("error"):
            code = data.get("error_code", "")
            raise QueryFailure("quota_exceeded" if code in ("ERR_QUOTA_EXCEEDED", "ERR_FREE_TIER_EXHAUSTED")
                               else "auth_error" if isinstance(code, str) and code.startswith("ERR_FORBIDDEN") else "error")
        if public_ip(data.get("ip")) != address:
            raise QueryFailure("invalid_response")
    if provider == "proxycheck":
        if data.get("status") not in ("ok", "warning"):
            raise QueryFailure("auth_error" if data.get("status") == "denied" else "error")
        if data.get("version") != PROVIDERS[provider]["profile"]["ver"] or address not in data:
            raise QueryFailure("invalid_response")
        data = mapping(data[address])
        network, location, detection = (mapping(data.get(k)) for k in ("network", "location", "detections"))
        facts.update(country_code=country(location.get("country_code")), asn=as_number(network.get("asn")),
                     organization=text(network.get("organisation")), network_type=text(network.get("type")),
                     activity=activity_fields(data))
        for key in ("vpn", "proxy", "tor", "hosting"):
            facts["flags"][key] = flag(detection.get(key))
        score = number(detection.get("risk"), 100)
        if score is not None:
            facts["scores"].append({"name": "proxycheck_risk", "value": score, "scale": 100, "scope": "ip_query"})
        tier = "public_reputation"
    elif provider == "ipquery":
        if public_ip(data.get("ip")) != address:
            raise QueryFailure("invalid_response")
        network, location, risk = (mapping(data.get(k)) for k in ("isp", "location", "risk"))
        facts.update(country_code=country(location.get("country_code")), asn=as_number(network.get("asn")),
                     organization=text(network.get("org")))
        for target, source in {"vpn": "is_vpn", "proxy": "is_proxy", "tor": "is_tor",
                               "hosting": "is_datacenter", "mobile": "is_mobile"}.items():
            facts["flags"][target] = flag(risk.get(source))
        score = number(risk.get("risk_score"), 100, integer=True)
        if score is not None:
            facts["scores"].append({"name": "ipquery_risk", "value": score, "scale": 100, "scope": "ip_query"})
        tier = "public_reputation"
    elif provider == "stopforumspam":
        if type(data.get("success")) is not int or data["success"] != 1:
            raise QueryFailure("error")
        data = mapping(data.get("ip"))
        if public_ip(data.get("value")) != address:
            raise QueryFailure("invalid_response")
        facts.update(country_code=country(data.get("country")), asn=number(data.get("asn"), integer=True),
                     spam=spam_fields(data))
        tier = "public_spam_lookup"
    elif provider == "ipwhois":
        if data.get("success") is not True:
            raise QueryFailure("invalid_response")
        connection = mapping(data.get("connection"))
        facts.update(country_code=country(data.get("country_code")), asn=number(connection.get("asn"), integer=True),
                     organization=text(connection.get("org")))
        tier = "public_identity"
    elif provider == "ipapi":
        # Anonymous responses changed in October 2026. Never treat omitted flags as false.
        if isinstance(data.get("asn"), str) or isinstance(data.get("company"), str) or "docs" in data:
            asn = data.get("asn")
            match = re.match(r"^AS(\d+)(?:\s|$)", asn) if isinstance(asn, str) else None
            facts.update(asn=number(int(match[1]), integer=True) if match else None,
                         organization=text(data.get("company")))
            tier = "anonymous_identity_only"
        else:
            network, company, location = (mapping(data.get(key)) for key in ("asn", "company", "location"))
            facts.update(asn=number(network.get("asn"), integer=True), country_code=country(location.get("country_code")),
                         organization=text(network.get("org") or company.get("name")), network_type=text(network.get("type")))
            for target, source in {"vpn": "is_vpn", "proxy": "is_proxy", "tor": "is_tor", "hosting": "is_datacenter",
                                   "mobile": "is_mobile", "recent_abuse": "is_abuser"}.items():
                facts["flags"][target] = flag(data.get(source))
            # abuser_score describes an entire company/ASN network, not this IP's fraud probability.
            for label, obj in (("company_abuse_ratio", company), ("asn_abuse_ratio", network)):
                score = obj.get("abuser_score")
                if score is not None:
                    match = re.fullmatch(r"(0(?:\.\d+)?|1(?:\.0+)?) \([A-Za-z ]+\)", str(score))
                    if not match:
                        raise QueryFailure("invalid_response")
                    facts["scores"].append({"name": label, "value": float(match[1]), "scale": 1, "scope": "network"})
            tier = "authenticated_response"
    elif provider == "ipqs":
        if data.get("success") is not True:
            raise QueryFailure("error")
        facts.update(country_code=country(data.get("country_code")), asn=number(data.get("ASN"), integer=True),
                     organization=text(data.get("organization")), network_type=text(data.get("connection_type")))
        for key in FLAG_FIELDS:
            if key != "hosting":
                facts["flags"][key] = flag(data.get(key))
        score = number(data.get("fraud_score"), 100)
        if score is not None:
            facts["scores"].append({"name": "fraud_score", "value": score, "scale": 100, "scope": "ip_query"})
        tier = "authenticated_response"
    elif provider == "abuseipdb":
        data = mapping(data.get("data"))
        if public_ip(data.get("ipAddress")) != address:
            raise QueryFailure("invalid_response")
        facts.update(country_code=country(data.get("countryCode")), organization=text(data.get("isp")),
                     network_type=text(data.get("usageType")), total_reports=number(data.get("totalReports"), integer=True),
                     distinct_reporters=number(data.get("numDistinctUsers"), integer=True))
        facts["flags"]["tor"] = flag(data.get("isTor"))
        if data.get("lastReportedAt") is not None:
            facts["last_reported_at"] = timestamp(data["lastReportedAt"]).isoformat()
        score = number(data.get("abuseConfidenceScore"), 100)
        if score is not None:
            facts["scores"].append({"name": "abuse_confidence", "value": score, "scale": 100, "scope": "reported_abuse"})
        tier = "authenticated_response"
    else:
        raise QueryFailure("invalid_response")
    return facts, tier


def missing_fields(provider, facts):
    if provider in EXTRA_PROVIDERS:
        required = ["country_code"] if provider in ("dbip", "ip2location", "ipinfo", "ipregistry") else []
        missing = [k for k in required if facts[k] is None]
        if provider.startswith("scamalytics") and not facts["scores"]:
            missing.append("score")
        return missing
    required = [] if provider == "stopforumspam" else ["country_code", "asn"] if provider in ("ipwhois", "ipapi", "proxycheck", "ipquery") else ["country_code"]
    missing = [k for k in required if facts[k] is None]
    if provider in ("ipapi", "ipqs"):
        missing += ["flags." + k for k in ("vpn", "proxy", "tor", "recent_abuse") if facts["flags"][k] is None]
    if provider in ("proxycheck", "ipquery"):
        missing += ["flags." + k for k in ("vpn", "proxy", "tor", "hosting") if facts["flags"][k] is None]
    if provider in ("ipqs", "abuseipdb", "proxycheck", "ipquery") and not facts["scores"]:
        missing.append("score")
    if provider == "abuseipdb":
        missing += [k for k in ("total_reports", "distinct_reporters") if facts[k] is None]
    return missing


def validate_records(records):
    if not isinstance(records, list) or len(records) > 2 * len(PROVIDERS):
        raise InputError("情报记录数量无效。")
    seen = set()
    required = {"provider", "subject", "status", "queried_at", "source_updated_at", "observation_window_days",
                "product_tier", "query_profile", "source", "upstream_sources", "facts", "missing_fields"}
    try:
        for r in records:
            exact(r, required, required)
            if r["provider"] not in PROVIDERS or r["subject"] not in {"agent-ipv4", "agent-ipv6", "browser-ipv4", "browser-ipv6", "agent-unmeasured", "browser-unmeasured"} or r["status"] not in STATES:
                raise InputError("情报来源、对象或状态无效。")
            identity = (r["provider"], r["subject"])
            if identity in seen:
                raise InputError("情报记录重复。")
            seen.add(identity)
            spec = PROVIDERS[r["provider"]]
            if r["query_profile"] != spec["profile"] or r["source"] != spec["docs"] or r["upstream_sources"] != spec["upstream_sources"]:
                raise InputError("情报来源与查询配置不匹配。")
            timestamp(r["queried_at"])
            if r["source_updated_at"] is not None:
                timestamp(r["source_updated_at"])
            if r["observation_window_days"] != (30 if r["provider"] == "abuseipdb" and r["status"] != "blocked_dependency" else None):
                raise InputError("情报时间窗口无效。")
            if r["status"] not in ("ok", "partial"):
                if r["facts"] is not None or r["missing_fields"] != [] or r["product_tier"] != "unknown":
                    raise InputError("失败情报不能含成功事实。")
                continue
            tiers = {"ipwhois": {"public_identity"}, "ipapi": {"anonymous_identity_only", "authenticated_response"},
                     "ipqs": {"authenticated_response"}, "abuseipdb": {"authenticated_response"},
                     "proxycheck": {"public_reputation"}, "ipquery": {"public_reputation"},
                     "stopforumspam": {"public_spam_lookup"}}
            tiers.update({key: {"official_api"} for key in EXTRA_PROVIDERS})
            if r["product_tier"] not in tiers[r["provider"]]:
                raise InputError("情报响应覆盖类型无效。")
            facts = r["facts"]
            fields = {"country_code", "asn", "organization", "network_type", "flags", "scores", "total_reports", "distinct_reporters", "last_reported_at"}
            if r["provider"] == "proxycheck":
                fields.add("activity")
                a = facts.get("activity")
                exact(a, {"attack_counts", "detection_confidence", "first_seen", "last_seen", "times_seen"},
                      {"attack_counts", "detection_confidence", "first_seen", "last_seen", "times_seen"})
                activity_fields({"attack_history": a["attack_counts"], "detections": {
                    "confidence": a["detection_confidence"], "first_seen": a["first_seen"],
                    "last_seen": a["last_seen"], "times_seen": a["times_seen"]}})
            elif r["provider"] == "stopforumspam":
                fields.add("spam")
                s = facts.get("spam")
                exact(s, {"listed", "frequency", "last_seen"}, {"listed", "frequency", "last_seen"})
                if type(s["listed"]) is not bool:
                    raise InputError("垃圾信息记录状态无效。")
                spam_fields({"appears": int(s["listed"]), "frequency": s["frequency"], "lastseen": s["last_seen"]})
            exact(facts, fields, fields)
            country(facts["country_code"])
            for k in ("asn", "total_reports", "distinct_reporters"):
                number(facts[k], integer=True)
            for k in ("organization", "network_type"):
                text(facts[k])
            if facts["last_reported_at"] is not None:
                timestamp(facts["last_reported_at"])
            exact(facts["flags"], FLAG_FIELDS, FLAG_FIELDS)
            for value in facts["flags"].values():
                flag(value)
            if not isinstance(facts["scores"], list) or len(facts["scores"]) > 2:
                raise InputError("情报评分列表无效。")
            allowed = {"ipwhois": {}, "ipapi": {"company_abuse_ratio": (1, "network"), "asn_abuse_ratio": (1, "network")},
                       "ipqs": {"fraud_score": (100, "ip_query")}, "abuseipdb": {"abuse_confidence": (100, "reported_abuse")},
                       "proxycheck": {"proxycheck_risk": (100, "ip_query")},
                       "ipquery": {"ipquery_risk": (100, "ip_query")}, "stopforumspam": {}}
            from .extra_intelligence import SCORES
            allowed.update(SCORES)
            allowed = allowed[r["provider"]]
            names = set()
            for score in facts["scores"]:
                exact(score, {"name", "value", "scale", "scope"}, {"name", "value", "scale", "scope"})
                if score["name"] not in allowed or score["name"] in names or (score["scale"], score["scope"]) != allowed[score["name"]] or type(score["scale"]) is not int:
                    raise InputError("情报评分语义无效。")
                names.add(score["name"])
                if score["value"] is None:
                    raise InputError("评分缺失不能被当作数值。")
                number(score["value"], score["scale"])
            missing = missing_fields(r["provider"], facts)
            if r["missing_fields"] != missing or r["status"] != ("partial" if missing else "ok"):
                raise InputError("情报覆盖状态不一致。")
    except (QueryFailure, TypeError, ValueError, KeyError) as exc:
        if isinstance(exc, InputError):
            raise
        raise InputError("情报记录格式无效。") from None
    return records


def query(client, provider, address, subject, key=None):
    spec = PROVIDERS[provider]
    result = {"provider": provider, "subject": subject, "status": "skipped", "queried_at": now(),
              "source_updated_at": None, "observation_window_days": 30 if provider == "abuseipdb" else None,
              "product_tier": "unknown", "query_profile": spec["profile"], "source": spec["docs"],
              "upstream_sources": spec["upstream_sources"], "facts": None, "missing_fields": []}
    try:
        payload = client.fetch(provider, address, key)
        facts, tier = parse(provider, payload, address)
        if provider == "proxycheck":
            result["source_updated_at"] = provider_time(payload[address].get("last_updated"))
        missing = missing_fields(provider, facts)
        result.update(facts=facts, product_tier=tier, missing_fields=missing, status="partial" if missing else "ok")
    except QueryFailure as exc:
        result["status"] = exc.state
    except (InputError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        result["status"] = "invalid_response"
    return result
