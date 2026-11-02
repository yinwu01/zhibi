"""Optional resolver observation using a fixed public diagnostic name, never account data."""
from __future__ import annotations

import ipaddress
import re
import shutil
import subprocess
from html import escape
from importlib.resources import files
from pathlib import Path

from .models import now
from .storage import create_run, write

DOMAIN = "whoami.ds.akahelp.net."
SOURCE = "https://www.akamai.com/blog/developers/introducing-new-whoami-tool-dns-resolver-information"
STATUSES = {"ok": "取得解析器观测", "skipped": "未启用联网", "unsupported": "未找到 dig",
            "configuration_present": "存在自定义 .digrc，未执行以免引入额外查询",
            "timeout": "测量超时", "error": "命令执行失败", "no_answer": "没有解析器记录",
            "invalid_response": "响应不符合契约"}


def plan():
    return {"context": "dig_default_resolver", "domain": DOMAIN, "record_type": "TXT",
            "max_process_invocations": 1, "process_timeout_seconds": 8,
            "external_services": [{"recipient": "configured DNS resolver chain and Akamai akahelp.net authority",
                "fields": ["diagnostic_query_name", "resolver_source_ip", "ecs_subnet_if_forwarded"]}],
            "notice": "独立于 HTTP 代理。DNS 递归链可能涉及多个服务；缓存命中时不一定联系权威端。未观测浏览器 DoH 或操作系统分域解析。"}


def parse_answer(raw):
    """Only retain known address fields; never pass provider-controlled text to the model."""
    if not isinstance(raw, bytes) or len(raw) > 32768:
        raise ValueError("response size")
    text = raw.decode("ascii")
    lines = text.splitlines()
    if len(lines) > 64:
        raise ValueError("record count")
    resolvers, subnets = set(), set()
    for line in lines:
        line = line.strip()
        if not line or line.startswith(";;"):
            continue
        match = re.fullmatch(r'"(ns|ecs|ip)"\s+"([^"\\]{1,100})"', line)
        if not match:
            raise ValueError("unexpected TXT record")
        kind, value = match.groups()
        if kind in {"ns", "ip"}:
            address = ipaddress.ip_address(value)
            if not address.is_global or address.is_multicast or "%" in value:
                raise ValueError("nonpublic address")
            if kind == "ns":
                resolvers.add(str(address))
            # Akamai's `ip` is an ECS representative, never a measured client IP.
        else:
            parts = value.split("/")
            if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
                raise ValueError("invalid ECS")
            network = ipaddress.ip_network(parts[0] + "/" + parts[1], strict=True)
            if not 0 <= int(parts[2]) <= network.max_prefixlen:
                raise ValueError("invalid ECS scope")
            subnets.add((str(network), int(parts[2])))
    return {"resolvers": sorted(resolvers), "ecs": [{"subnet": n, "scope_prefix": p} for n, p in sorted(subnets)]}


def measure(enabled=False, runner=None, finder=None):
    result = {"status": "skipped", "at": now(), "context": "dig_default_resolver",
              "domain": DOMAIN, "source": SOURCE, "attempted": False, "facts": None}
    if not enabled:
        return result
    executable = (finder or shutil.which)("dig")
    if not executable:
        result["status"] = "unsupported"
        return result
    # Apple's bundled dig lacks -r. Refuse custom defaults without reading or changing them.
    config = Path.home() / ".digrc"
    if config.exists() or config.is_symlink():
        result["status"] = "configuration_present"
        return result
    # Fixed arguments, no shell, no credentials or caller-controlled domains.
    command = [executable, DOMAIN, "TXT", "+short", "+time=3", "+tries=1",
               "+nosearch", "+fail", "+ignore", "+notcp"]
    result["attempted"] = True
    try:
        completed = (runner or subprocess.run)(command, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=8, check=False)
        if completed.returncode != 0:
            result["status"] = "error"
            return result
        facts = parse_answer(completed.stdout)
        result["facts"] = facts
        result["status"] = "ok" if facts["resolvers"] else "no_answer"
    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
    except OSError:
        result["status"] = "error"
    except (ValueError, UnicodeError):
        result["status"] = "invalid_response"
    return result


def summary(record):
    facts = record["facts"] or {"resolvers": [], "ecs": []}
    obtained = record["status"] == "ok"
    return {"format": "zhibi-dns-summary-1", "context": record["context"], "status": record["status"],
            "at": record["at"], "attempted": record["attempted"], "source": SOURCE,
            "resolver_count": len(facts["resolvers"]),
            "resolver_families": sorted({ipaddress.ip_address(a).version for a in facts["resolvers"]}),
            "ecs_reported": bool(facts["ecs"]) if obtained else None,
            "cache_freshness": "not_established", "dnssec_validation": "not_performed", "browser_dns": "unobserved",
            "finding": {"layer": "L1", "motivation": "routing_integrity",
                "state": "observed" if obtained else "unknown",
                "statement": "已取得该诊断名称返回的递归解析器信息。" if obtained else "未取得有效递归解析器观测：" + STATUSES[record["status"]] + "。",
                "normal_counterexample": "递归解析器出口通常不同于 HTTPS 出口；转发、缓存和分域解析都可能影响结果，差异本身不证明泄漏。",
                "next_step": "与自己预期的 DNS 服务核对；检查浏览器 DoH、系统分域与应用代理时需分别取得对应证据。"},
            "privacy": "原始解析器 IP 与 ECS 子网只保存在本机私人快照；未读取浏览器或账号凭据。"}


def run_dns(network=False, out=None, runner=None, finder=None):
    directory = create_run(out)  # Fail before making the optional DNS request.
    record = measure(network, runner, finder)
    result = summary(record)
    evidence = {"nodes": [{"id": "source:akamai", "type": "diagnostic_service", "url": SOURCE},
                          {"id": "dns:dig-default", "type": "observation", "at": record["at"], "status": record["status"]},
                          {"id": "motivation:routing_integrity", "type": "research_motivation"},
                          {"id": "finding:dns", "type": "interpretation"},
                          {"id": "action:dns", "type": "next_step"}],
                "edges": [{"from": "source:akamai", "to": "dns:dig-default", "relation": "source_of_claim"},
                          {"from": "dns:dig-default", "to": "finding:dns", "relation": "evidence_for"},
                          {"from": "motivation:routing_integrity", "to": "finding:dns", "relation": "research_context"},
                          {"from": "finding:dns", "to": "action:dns", "relation": "suggests"}]}
    report = {"summary": result, "plan": plan(), "graph": evidence}
    write(directory / "snapshot.private.json", record)
    write(directory / "agent-summary.json", result)
    write(directory / "report.json", report)
    f = result["finding"]
    content = "# 知彼 · DNS 解析器观察\n\n" + f["statement"] + "\n\n" + f["normal_counterexample"] + "\n\n下一步：" + f["next_step"] + "\n"
    write(directory / "report.md", content)
    css = files("zhibi").joinpath("assets").joinpath("report.css").read_text(encoding="utf-8")
    body = "".join("<p>" + escape(p) + "</p>" for p in (f["statement"], f["normal_counterexample"], f["next_step"], result["privacy"]))
    page = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src &#39;none&#39;; style-src &#39;unsafe-inline&#39;;"><title>知彼 · DNS 解析器观察</title><style>' + css + '</style><main><h1>DNS 解析器观察</h1>' + body + '<p>观测范围：dig 默认解析器；浏览器 DNS 未测量。缓存新鲜度未确认。</p><p>解析器数量：' + str(result["resolver_count"]) + '</p><a rel="noreferrer noopener" href="' + SOURCE + '">诊断服务说明</a></main></html>'
    write(directory / "report.html", page)
    return {"directory": str(directory), "report": str(directory / "report.html"), "summary": result}
