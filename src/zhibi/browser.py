"""Strict browser bundle import and self-contained advanced probe generation."""
import ipaddress
from importlib.resources import files

from .models import ENDPOINT, IPV6_ENDPOINT, InputError, bounded_string, exact, timestamp

STUN = "stun:stun.l.google.com:19302"
NETWORK_STATES = {"ok", "error", "timeout", "skipped", "invalid_response", "quota_exceeded"}


def parse_bundle(data):
    from .models import browser_input
    if isinstance(data, dict) and data.get("schema_version") == "1":
        return {"observations": browser_input(data), "network": None, "environment": None}
    fields = {"schema_version", "context", "observations", "network", "environment"}
    advanced = isinstance(data, dict) and data.get("schema_version") in ("3", "4")
    if advanced:
        fields.add("details")
    if isinstance(data, dict) and data.get("schema_version") == "4":
        fields.add("extras")
    exact(data, fields, fields)
    if data["schema_version"] not in ("2", "3", "4") or data["context"] != "user_opened_browser":
        raise InputError("浏览器探针版本或上下文无效。")
    observations = browser_input({"schema_version": "1", "context": data["context"], "observations": data["observations"]})
    network = data["network"]
    exact(network, {"ipv4", "ipv6", "webrtc"}, {"ipv4", "ipv6", "webrtc"})
    for family, endpoint in ((4, ENDPOINT), (6, IPV6_ENDPOINT)):
        obs = network["ipv" + str(family)]
        exact(obs, {"family", "endpoint", "at", "status", "ip"}, {"family", "endpoint", "at", "status", "ip"})
        if obs["family"] != family or obs["endpoint"] != endpoint or obs["status"] not in NETWORK_STATES:
            raise InputError("浏览器网络测量类型无效。")
        timestamp(obs["at"])
        if obs["status"] == "ok":
            try:
                address = ipaddress.ip_address(obs["ip"])
            except (ValueError, TypeError):
                raise InputError("浏览器出口地址无效。") from None
            if address.version != family:
                raise InputError("浏览器出口地址族不一致。")
        elif obs["ip"] is not None:
            raise InputError("失败测量不能携带成功出口。")
    legacy = next(o for o in observations if o["check_id"] == "browser.egress")
    v4 = network["ipv4"]
    state = v4["status"] if v4["status"] in ("ok", "error", "timeout", "skipped") else "error"
    if legacy["status"] != state or timestamp(legacy["at"]) != timestamp(v4["at"]) or (state == "ok" and legacy["facts"]["ip"] != v4["ip"]):
        raise InputError("浏览器文件中的 IPv4 观测相互矛盾。")
    rtc = network["webrtc"]
    exact(rtc, {"status", "at", "endpoint", "candidates", "complete"}, {"status", "at", "endpoint", "candidates", "complete"})
    if rtc["endpoint"] != STUN or rtc["status"] not in {"ok", "error", "timeout", "skipped", "unsupported", "no_candidates"} or type(rtc["complete"]) is not bool:
        raise InputError("WebRTC 测量状态无效。")
    timestamp(rtc["at"])
    if not isinstance(rtc["candidates"], list) or len(rtc["candidates"]) > 64:
        raise InputError("ICE 候选列表无效。")
    for item in rtc["candidates"]:
        exact(item, {"type", "protocol", "address", "mdns"}, {"type", "protocol", "address", "mdns"})
        if item["type"] not in {"host", "srflx", "relay", "prflx"} or item["protocol"] not in {"udp", "tcp"} or type(item["mdns"]) is not bool:
            raise InputError("ICE 候选类型无效。")
        if item["mdns"]:
            if item["address"] is not None or item["type"] != "host":
                raise InputError("mDNS 候选不能携带 IP。")
        else:
            try:
                ipaddress.ip_address(item["address"])
            except (ValueError, TypeError):
                raise InputError("ICE 候选地址无效。") from None
    if rtc["status"] in {"skipped", "unsupported", "no_candidates"} and rtc["candidates"]:
        raise InputError("WebRTC 状态与候选不一致。")
    if rtc["status"] == "ok" and (not rtc["complete"] or not rtc["candidates"]):
        raise InputError("WebRTC 成功必须有完成的候选观测。")
    if rtc["status"] in {"skipped", "unsupported", "timeout", "error"} and rtc["complete"]:
        raise InputError("未完成的 WebRTC 不能标为完成。")
    env = data["environment"]
    exact(env, {"languages", "timezone", "locale", "userAgent", "platform", "brands"},
          {"languages", "timezone", "locale", "userAgent", "platform", "brands"})
    if not isinstance(env["languages"], list) or len(env["languages"]) > 20:
        raise InputError("语言列表无效。")
    for language in env["languages"]:
        bounded_string(language)
    for name in ("timezone", "locale", "userAgent", "platform", "brands"):
        if env[name] is not None:
            bounded_string(env[name], 1000 if name == "userAgent" else 300)
    bundle = {"observations": observations, "network": network, "environment": env}
    if advanced:
        from .browser_details import validate_details
        bundle["details"] = validate_details(data["details"])
    if data["schema_version"] == "4":
        from .browser_extras import validate
        bundle["extras"] = validate(data["extras"])
    return bundle


def advanced_page():
    assets = files("zhibi").joinpath("assets")
    page = assets.joinpath("network.html").read_text(encoding="utf-8")
    code = assets.joinpath("network-probe.js").read_text(encoding="utf-8")
    code += "\n" + assets.joinpath("browser-details.js").read_text(encoding="utf-8")
    code += "\n" + assets.joinpath("browser-extras.js").read_text(encoding="utf-8")
    notices = assets.joinpath("third-party.txt").read_text(encoding="utf-8")
    return page.replace("/* ZHIBI_NETWORK_MODULE */", code).replace("<!-- ZHIBI_THIRD_PARTY_NOTICES -->", "<!--\n" + notices.replace("--", "—") + "\n-->")
