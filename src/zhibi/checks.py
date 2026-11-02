"""Read-only checks: configuration summaries, never credential directories."""
from __future__ import annotations

import ipaddress
import os
import platform
import shutil
import sys
from pathlib import Path
from urllib.parse import urlsplit

from .models import ENDPOINT, IPV6_ENDPOINT, observation, validate_observations
from .transport import NetworkError


def declared_client():
    """用户声明的目标客户端命令名；未声明时不猜测任何客户端。"""
    value = os.environ.get("ZHIBI_CLIENT", "").strip()
    return value or None


def proxy_check(env=None):
    env = os.environ if env is None else env
    values = [env[k] for k in ("http_proxy", "https_proxy", "all_proxy",
                               "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY") if env.get(k)]
    auth = unsupported = False
    for value in values:
        try:
            parsed = urlsplit(value)
            auth |= bool(parsed.username or parsed.password)
            unsupported |= parsed.scheme not in ("http", "https") or not parsed.hostname
        except ValueError:
            unsupported = True
    conflict = any(env.get(k) and env.get(k.upper()) and env[k] != env[k.upper()]
                   for k in ("http_proxy", "https_proxy", "all_proxy"))
    return observation("host.proxy", "ok", {
        "configured": bool(values), "authenticated": auth,
        "unsupported_scheme": unsupported, "conflicting": conflict})


def collect(transport, browser=None):
    system = platform.system()
    client = declared_client()
    items = [
        observation("host.runtime", "ok", {"python_supported": sys.version_info >= (3, 9),
                    "os_family": system if system in ("Darwin", "Linux", "Windows") else "Other"}),
        proxy_check(),
        observation("client.installed", "ok", {"present": shutil.which(client) is not None}) if client
        else observation("client.installed", "skipped"),
    ]
    if system in ("Darwin", "Linux"):
        try:
            with Path("/etc/resolv.conf").open() as f:
                content = f.read(8192)
            count = sum(1 for line in content.splitlines() if line.strip().startswith("nameserver "))
            items.append(observation("host.dns", "ok", {"nameserver_count": count}))
        except OSError:
            items.append(observation("host.dns", "error"))
    else:
        items.append(observation("host.dns", "unsupported"))
    if browser:
        items.extend(browser)
    else:
        items.extend([observation("browser.context", "skipped"), observation("browser.egress", "skipped")])
    ip = None
    if transport.enabled:
        try:
            result = transport.get("ipify")
            address = ipaddress.ip_address(result.get("ip"))
            if address.version != 4 or not address.is_global:
                raise NetworkError()
            ip = str(address)
            items.append(observation("network.egress", "ok", {"ip": ip, "family": 4, "endpoint": ENDPOINT}))
        except NetworkError as exc:
            items.append(observation("network.egress", exc.status))
        except (ValueError, TypeError):
            items.append(observation("network.egress", "error"))
    else:
        items.append(observation("network.egress", "skipped"))
    if transport.metadata and ip:
        try:
            result = transport.get("ipwhois", ip)
            if result.get("success") is not True:
                raise NetworkError()
            item = observation("network.metadata", "ok", {
                "country_code": result.get("country_code"),
                "asn": result.get("connection", {}).get("asn")})
            validate_observations([item])
            items.append(item)
        except NetworkError as exc:
            items.append(observation("network.metadata", exc.status))
        except (ValueError, TypeError, AttributeError):
            items.append(observation("network.metadata", "error"))
    else:
        items.append(observation("network.metadata", "skipped"))
    if transport.enabled and transport.ipv6:
        try:
            address = ipaddress.ip_address(transport.get("ipify6").get("ip"))
            if address.version != 6 or not address.is_global:
                raise NetworkError()
            items.append(observation("network.ipv6", "ok", {"ip": str(address), "family": 6, "endpoint": IPV6_ENDPOINT}))
        except NetworkError as exc:
            items.append(observation("network.ipv6", exc.status))
        except (ValueError, TypeError):
            items.append(observation("network.ipv6", "error"))
    else:
        items.append(observation("network.ipv6", "skipped"))
    if transport.enabled and transport.connectivity:
        facts = transport.probe_target()
        state = "ok" if facts["outcome"] == "http_response" else "timeout" if facts["outcome"] == "timeout" else "error"
        items.append(observation("network.connectivity", state, facts))
    else:
        items.append(observation("network.connectivity", "skipped"))
    return validate_observations(items)
