"""Optional bounded diagnostics; target browser and collector host are distinct subjects."""
import ipaddress
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .intelligence import public_ip
from .models import InputError, now, read_json
from .transport import NoRedirect

SERVICES = {
    "tiktok": "https://www.tiktok.com/", "disney": "https://www.disneyplus.com/",
    "netflix": "https://www.netflix.com/", "youtube": "https://www.youtube.com/",
    "primevideo": "https://www.primevideo.com/", "reddit": "https://www.reddit.com/",
}
SMTP = {"gmail": "smtp.gmail.com", "outlook": "smtp-mail.outlook.com"}
DNSBL = {"spamhaus": "zen.spamhaus.org", "spamcop": "bl.spamcop.net"}


def result(state, facts=None, recipients=(), subject="collector_host"):
    return dict(status=state, at=now(), subject=subject, facts=facts, recipients=list(recipients))


def private_config(path):
    path = Path(path).expanduser().absolute()
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file() or path.stat().st_size > 65536:
        raise InputError("配置必须是本地普通小文件，不能经过符号链接。")
    if os.name == "posix" and path.stat().st_mode & 0o077:
        raise InputError("私人配置权限应为 600。")
    data = read_json(path)
    if not isinstance(data, dict):
        raise InputError("配置应为 JSON 对象。")
    return data


def command(args, timeout=8, stdin=None):
    """Never return stderr or inherited authentication variables to reports."""
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "SystemRoot", "SYSTEMROOT", "WINDIR", "LANG", "LC_ALL", "TMPDIR")}
    try:
        process = subprocess.run(args, input=stdin, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 encoding="utf-8", errors="replace", timeout=timeout, env=env)
        if len(process.stdout) > 131072:
            return None, "invalid_response"
        return process.stdout, "ok" if process.returncode == 0 else "error"
    except subprocess.TimeoutExpired:
        return None, "timeout"
    except OSError:
        return None, "unavailable"


def service(name, opener=None):
    url = SERVICES[name]
    host = urllib.parse.urlsplit(url).hostname
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Zhibi-Diagnostics/0.3"})
    try:
        with (opener or urllib.request.build_opener(NoRedirect())).open(request, timeout=6) as response:
            code = response.status
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
    except (OSError, ValueError):
        return result("error", recipients=[host])
    # An HTTP response proves only this endpoint responded; not authentication/region entitlement.
    state = "ok" if 200 <= code < 400 else "review"
    return result(state, dict(http_status=code, account_access_verified=False, region_access_verified=False), [host])


def smtp(name, port, connector=None):
    if name not in SMTP or port not in (25, 465, 587):
        raise InputError("SMTP 仅支持预定义服务与 25/465/587 端口。")
    host = SMTP[name]
    try:
        with (connector or socket.create_connection)((host, port), timeout=4):
            pass
        return result("ok", {"port": port, "tcp_connected": True, "mail_sent": False}, [host])
    except OSError:
        return result("error", {"port": port, "tcp_connected": False, "mail_sent": False}, [host])


def dnsbl(address, name, runner=command):
    ip = ipaddress.ip_address(public_ip(address))
    if name == "spamcop" and ip.version == 6:
        return result("unsupported", subject="selected_ip")
    if not shutil.which("dig"):
        return result("missing_dependency", subject="selected_ip")
    if (Path.home() / ".digrc").exists():
        return result("configuration_required", subject="selected_ip")
    reverse = ".".join(reversed(str(ip).split("."))) if ip.version == 4 else ".".join(reversed(ip.exploded.replace(":", "")))
    host = DNSBL[name]
    def lookup(name):
        return runner(["dig", "+time=2", "+tries=1", "+nosearch", "+noall", "+comments", "+answer", name + ".", "A"], timeout=4)
    if name == "spamhaus":
        positive, pos_state = lookup("2.0.0.127." + host)
        negative, neg_state = lookup("1.0.0.127." + host)
        if pos_state != "ok" or neg_state != "ok" or not re.search(r"\sIN\s+A\s+127\.0\.0\.(?:2|4|10)\b", positive or "") or "status: NXDOMAIN" not in (negative or ""):
            return result("access_restricted", recipients=[host], subject="selected_ip")
    output, state = lookup(reverse + "." + host)
    if state != "ok":
        return result(state, recipients=[host], subject="selected_ip")
    status = re.search(r"status: ([A-Z]+)", output)
    if not status or status[1] not in ("NXDOMAIN", "NOERROR"):
        return result("error", recipients=[host], subject="selected_ip")
    codes = re.findall(r"\sIN\s+A\s+(\d+\.\d+\.\d+\.\d+)", output)
    if any(c.startswith("127.255.") or not c.startswith("127.0.0.") for c in codes):
        return result("access_restricted", recipients=[host], subject="selected_ip")
    # Only documented list return codes count. Unknown positives are not an abuse verdict.
    allowed = {"127.0.0.2"} if name == "spamcop" else {"127.0.0." + str(n) for n in (2, 3, 4, 9, 10, 11)}
    if any(c not in allowed for c in codes) or (status[1] == "NXDOMAIN" and codes) or (status[1] == "NOERROR" and not codes):
        return result("invalid_response", recipients=[host], subject="selected_ip")
    return result("review" if codes else "ok", {"listed": bool(codes), "codes": codes, "resolver_scope": "collector_default"}, [host], "selected_ip")


def tls_observer(opener=None):
    host = "tls.peet.ws"
    try:
        request = urllib.request.Request("https://tls.peet.ws/api/all", headers={"Accept": "application/json", "User-Agent": "Zhibi-Diagnostics/0.3"})
        with (opener or urllib.request.build_opener(NoRedirect())).open(request, timeout=8) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise ValueError()
        data = json.loads(raw)
        tls = data.get("tls", {})
        facts = {"http_version": data.get("http_version"), "tls_version": tls.get("tls_version_negotiated"),
                 "ja3": tls.get("ja3_hash"), "ja4": tls.get("ja4")}
        if any(v is not None and (not isinstance(v, str) or len(v) > 200 or any(ord(c) < 32 for c in v)) for v in facts.values()):
            raise ValueError()
        if not any(facts.values()):
            raise ValueError()
        return result("ok", facts, [host])
    except (OSError, ValueError, TypeError, AttributeError):
        return result("error", recipients=[host])


def local_database(address, path):
    if not path:
        return result("configuration_required", subject="selected_ip")
    try:
        import maxminddb
    except ImportError:
        return result("missing_dependency", subject="selected_ip")
    path = Path(path).expanduser()
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 2 * 1024 ** 3:
        return result("invalid_configuration", subject="selected_ip")
    try:
        with maxminddb.open_database(str(path)) as reader:
            data, meta = reader.get(public_ip(address)), reader.metadata()
        facts = {"database_type": str(meta.database_type)[:100], "build_epoch": meta.build_epoch, "matched": data is not None}
        if data:
            facts.update(country_code=(data.get("country") or {}).get("iso_code"), asn=data.get("autonomous_system_number"),
                         organization=data.get("autonomous_system_organization"))
        return result("ok" if data else "no_record", facts, subject="selected_ip")
    except (OSError, ValueError, TypeError):
        return result("error", subject="selected_ip")


def native(runner=command):
    facts = {"os": platform.system(), "architecture": platform.machine(), "logical_processors": os.cpu_count(), "timezone": datetime.now().astimezone().tzname()}
    if platform.system() == "Darwin":
        for field, args in (("cpu_model", ["sysctl", "-n", "machdep.cpu.brand_string"]),
                            ("locale", ["defaults", "read", "-g", "AppleLocale"]),
                            ("languages", ["defaults", "read", "-g", "AppleLanguages"])):
            value, state = runner(args)
            facts[field] = value.strip()[:500] if state == "ok" else None
        proxy, state = runner(["scutil", "--proxy"])
        facts["system_proxy_enabled"] = bool(re.search(r"(?:HTTP|HTTPS|SOCKS|ProxyAutoConfig)Enable\s*:\s*1", proxy or "")) if state == "ok" else None
    elif platform.system() == "Linux":
        value, state = runner(["locale"])
        facts["locale"] = next((line[5:].strip('"') for line in (value or "").splitlines() if line.startswith("LANG=")), None)
        facts["cpu_model"] = platform.processor() or None
    else:
        facts["cpu_model"] = platform.processor() or None
        facts["locale"] = None
    return result("ok", facts)


def cli_installation(client=None, runner=command):
    if not client:
        return result("not_declared")
    executable = shutil.which(client)
    if not executable:
        return result("not_installed")
    resolved = str(Path(executable).resolve())
    method = "brew" if "/Cellar/" in resolved or "/Caskroom/" in resolved else "npm" if "node_modules" in resolved else "bun" if "/.bun/" in resolved else "native" if "/.local/" in resolved else "unknown"
    value, state = runner([executable, "--version"], timeout=8)
    match = re.search(r"\b(\d+\.\d+\.\d+(?:[-+][\w.-]+)?)\b", value or "")
    return result("ok" if state == "ok" and match else state if state != "ok" else "invalid_response",
                  {"method": method, "version": match[1] if match else None, "executable": resolved})


def route(config, family=4, runner=command):
    if not config:
        return result("configuration_required")
    if set(config) - {"proxy_url", "interface", "expected_ip"}:
        raise InputError("route 配置有未知字段。")
    proxy = config.get("proxy_url")
    interface = config.get("interface")
    if proxy is not None:
        parsed = urllib.parse.urlsplit(proxy)
        if parsed.scheme not in ("http", "https", "socks5", "socks5h") or not parsed.hostname or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise InputError("代理 URL 格式无效。")
    if interface is not None and (not isinstance(interface, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", interface)):
        raise InputError("网卡名格式无效。")
    if not proxy and not interface:
        raise InputError("route 至少选择 proxy_url 或 interface。")
    expected = public_ip(config["expected_ip"]) if config.get("expected_ip") else None
    def quote(value):
        if not isinstance(value, str) or len(value) > 4096 or any(ord(c) < 32 for c in value):
            raise InputError("路由配置值无效。")
        return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'
    # -q disables .curlrc; credentials only travel over stdin, never argv or stderr.
    lines = ['url = "https://api' + ("6" if family == 6 else "") + '.ipify.org?format=json"', 'max-time = 8', 'connect-timeout = 4', 'silent', 'fail', 'max-filesize = 32768']
    if proxy:
        lines += ["proxy = " + quote(proxy), 'noproxy = ""']
    else:
        lines += ['proxy = ""']
    if interface:
        lines.append("interface = " + quote(interface))
    value, state = runner(["curl", "-q", "-" + str(family), "--config", "-"], timeout=10, stdin="\n".join(lines) + "\n")
    host = "api6.ipify.org" if family == 6 else "api.ipify.org"
    if state != "ok":
        return result(state, recipients=[host], subject="explicit_route")
    try:
        address = public_ip(json.loads(value)["ip"])
        if ipaddress.ip_address(address).version != family:
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        return result("invalid_response", recipients=[host], subject="explicit_route")
    return result("review" if expected and expected != address else "ok", {"ip": address, "expected_matches": expected == address if expected else None, "family": family}, [host], "explicit_route")
