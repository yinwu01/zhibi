"""Strict v4 extension import; render hashes never appear in the Agent summary."""
import math
import re
import ipaddress
from urllib.parse import urlsplit
from .models import InputError, exact, timestamp

LABELS = {"canvas": "Canvas 渲染一致性", "webgl": "WebGL 图形信息", "audio": "离线 Audio 渲染", "tls": "浏览器 TLS / HTTP 观测", "dns": "浏览器 DNS 权威观测"}


def validate(data):
    exact(data, {"at", "checks"}, {"at", "checks"})
    timestamp(data["at"])
    exact(data["checks"], set(LABELS), set(LABELS))
    for key, item in data["checks"].items():
        exact(item, {"status", "facts"}, {"status", "facts"})
        if item["status"] not in {"ok", "skipped", "unsupported", "error", "timeout", "configuration_required", "no_record"}:
            raise InputError("扩展检查状态无效。")
        f = item["facts"]
        if item["status"] != "ok" and not (key == "dns" and item["status"] == "no_record"):
            if f is not None:
                raise InputError("未取得的扩展检查不能携带读数。")
            continue
        fields = {"canvas": {"sha256", "repeated_equal", "width", "height"}, "webgl": {"vendor", "renderer", "version", "max_texture_size", "unmasked"}, "audio": {"samples", "sample_rate", "absolute_sum"}, "tls": {"http_version", "tls_version", "ja3", "ja4"}, "dns": {"observer", "resolvers", "ecs", "transport_from_browser"}}[key]
        exact(f, fields, fields)
        if key == "canvas":
            valid = isinstance(f["sha256"], str) and re.fullmatch("[a-f0-9]{64}", f["sha256"]) and type(f["repeated_equal"]) is bool and f["width"] == 240 and f["height"] == 80
        elif key == "webgl":
            valid = all(isinstance(f[k], str) and len(f[k]) <= 300 and not any(ord(c) < 32 for c in f[k]) for k in ("vendor", "renderer", "version")) and type(f["unmasked"]) is bool and type(f["max_texture_size"]) is int and 0 < f["max_texture_size"] <= 1048576
        elif key == "audio":
            valid = type(f["samples"]) is int and f["samples"] == 5000 and f["sample_rate"] == 44100 and type(f["absolute_sum"]) in (float, int) and math.isfinite(f["absolute_sum"]) and 0 <= f["absolute_sum"] <= 5000
        elif key == "dns":
            try:
                u = urlsplit(f["observer"])
                valid = u.scheme == "https" and u.hostname and u.netloc == u.hostname and not u.path and not u.query and not u.fragment and f["transport_from_browser"] == "not_observable" and isinstance(f["resolvers"], list) and len(f["resolvers"]) <= 16 and isinstance(f["ecs"], list) and len(f["ecs"]) <= 16
                for address in f["resolvers"]:
                    ipaddress.ip_address(address)
                for subnet in f["ecs"]:
                    ipaddress.ip_network(subnet)
                valid = valid and bool(f["resolvers"]) == (item["status"] == "ok")
            except (ValueError, TypeError):
                valid = False
        else:
            valid = all(v is None or isinstance(v, str) and len(v) <= 200 and not any(ord(c) < 32 for c in v) for v in f.values()) and any(f.values())
        if not valid:
            raise InputError("扩展检查读数无效。")
    return data
