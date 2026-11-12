"""Live evidence from the bound execution environment, with an optional outage drill."""
import ipaddress
import json
import shlex
import subprocess
import sys
from pathlib import Path

from . import remote
from .models import InputError, now

PROBE = r'''
import ipaddress,json,os,socket,urllib.request
from pathlib import Path
r={'execution':'ok','egress':{'state':'error'},'dns':{'state':'not_measured'},'ipv6':{'state':'not_measured'}}
try:
    socket.setdefaulttimeout(6)
    r['dns']={'state':'observed','addresses':sorted({x[4][0] for x in socket.getaddrinfo('api.ipify.org',443,socket.AF_INET)})}
except Exception:
    r['dns']={'state':'error'}
try:
    with urllib.request.urlopen('https://api.ipify.org',timeout=8) as response:
        ip=str(ipaddress.ip_address(response.read(128).decode().strip()))
    r['egress']={'state':'observed','ip':ip}
except Exception:
    pass
try:
    values={p.parent.name:p.read_text().strip() for p in Path('/proc/sys/net/ipv6/conf').glob('*/disable_ipv6')}
    boot_disabled='ipv6.disable=1' in Path('/proc/cmdline').read_text().split() and not values
    r['ipv6']={'state':'observed','disabled':boot_disabled or bool(values) and {'all','default','lo'} <= values.keys() and all(v=='1' for v in values.values()),'interfaces':values}
except OSError:
    pass
print(json.dumps(r))
'''


def measure(data):
    expression = "python3 -c " + shlex.quote(PROBE)
    prefix = data.get("probe_prefix", [])
    if prefix:
        expression = " ".join(shlex.quote(item) for item in prefix) + " " + expression
    if data["backend"] == "remote":
        outcome = remote.execute(remote.target(**data["target"]), expression, timeout=45)
        text = outcome["value"] if outcome["state"] == "ok" else ""
    else:
        from . import pvm_backend as pvm
        _, vm = pvm.load(data["vm_workspace"])
        try:
            done = subprocess.run(pvm.guest_command(vm, expression), env=pvm.environment(vm),
                                  capture_output=True, text=True, timeout=45)
            text = done.stdout if done.returncode == 0 else ""
        except subprocess.TimeoutExpired:
            text = ""
    try:
        result = json.loads(text)
        if result.get("execution") != "ok" or not isinstance(result.get("egress"), dict):
            raise ValueError()
        if result["egress"].get("ip"):
            ipaddress.ip_address(result["egress"]["ip"])
        return result
    except (ValueError, AttributeError, TypeError):
        return {"execution": "error", "egress": {"state": "not_measured"}}


def connected(observation):
    return observation.get("execution") == "ok" and observation.get("egress", {}).get("state") == "observed"


def control(path):
    from .connect import command_text
    # Read/validate both control scripts before the outage starts. No shell filename
    # interpolation; script text is an explicitly supplied private action.
    text = command_text(path)
    try:
        done = subprocess.run(["sh", "-c", text], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=45)
        return done.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def outage(data, before, disconnect, reconnect):
    from .connect import command_text
    command_text(disconnect)
    command_text(reconnect)
    if not connected(before):
        return {"state": "not_measured", "reason": "baseline_not_connected"}
    result = {"state": "not_measured"}
    try:
        result["disconnect_succeeded"] = control(disconnect)
        if result["disconnect_succeeded"]:
            result["during"] = measure(data)
    finally:
        result["reconnect_succeeded"] = control(reconnect)
        result["after"] = measure(data)
    during = result.get("during", {})
    after = result["after"]
    if not result["reconnect_succeeded"] or not connected(after):
        result.update(state="fail", reason="restoration_failed")
    elif after["egress"]["ip"] != before["egress"]["ip"]:
        result.update(state="fail", reason="exit_changed_after_restoration")
    elif connected(during):
        result.update(state="fail", reason="network_still_reachable_during_outage")
    elif during.get("execution") != "ok":
        result.update(state="not_measured", reason="probe_unreachable_during_outage")
    elif during.get("egress", {}).get("state") == "error":
        result.update(state="ok", reason="https_failed_during_outage_and_recovered")
    return result


def audit(args, data):
    if not args.network:
        return {"attempted": False, "recipient": "api.ipify.org", "complete": False}
    if bool(args.disconnect_file) != bool(args.reconnect_file):
        raise InputError("断网演练必须同时提供断开和恢复脚本。")
    expected = str(ipaddress.ip_address(args.expected_ip)) if args.expected_ip else None
    before = measure(data)
    checks = {}
    ip = before.get("egress", {}).get("ip")
    checks["egress"] = {"state": "not_measured" if not ip else "observed" if not expected else "ok" if ip == expected else "fail",
                        "ip": ip, "expected_ip": expected}
    checks["application_scope"] = {"state": "ok" if data.get("probe_prefix") or data["backend"] == "pvm" else "not_measured",
                                   "detail": "configured application runner" if data.get("probe_prefix") else "whole VM" if data["backend"] == "pvm" else "server host only; application runner not supplied"}
    checks["dns_resolution"] = before.get("dns", {"state": "not_measured"})
    checks["dns_route"] = {"state": "not_measured"}
    checks["udp"] = {"state": "not_measured"}
    checks["ipv6"] = before.get("ipv6", {"state": "not_measured"})
    checks["browser_exit"] = {"state": "not_measured"}
    if args.browser:
        from .flow import browser_readings
        readings = browser_readings(args.browser)
        browser_ip = readings.get("egress_ip")
        checks["browser_exit"] = {"state": "not_measured" if not ip or not browser_ip else "ok" if browser_ip == ip else "fail",
                                   "ip": browser_ip}
    checks["outage"] = outage(data, before, args.disconnect_file, args.reconnect_file) if args.disconnect_file else {"state": "not_measured"}
    report = {"version": 1, "at": now(), "backend": data["backend"], "checks": checks,
              "complete": False, "scope": "selected HTTPS endpoint and imported browser observations",
              "notice": "DNS 解析成功不证明解析路径；IPv6 sysctl 不证明无泄漏；单一 HTTPS 断网演练不覆盖所有协议。"}
    if data["backend"] == "pvm":
        from . import pvm_backend as pvm
        from types import SimpleNamespace
        report["pvm"] = pvm.dispatch(SimpleNamespace(action="audit", workspace=data["vm_workspace"], network=True))
    report["requires_attention"] = any(item["state"] in ("fail", "error") for item in checks.values())
    if args.out:
        from .project import save
        save(Path(args.out).expanduser(), json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report
