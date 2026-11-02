"""Skill-oriented scan: local facts -> scoped intelligence -> evidence -> action."""
from __future__ import annotations

import copy
import ipaddress
import json
from datetime import timedelta
from pathlib import Path

from . import __version__
from .checks import collect
from .engine import evaluate, validate_report
from .intelligence import PROVIDERS, Client, load_keys, public_ip, query, validate_records
from .models import ENDPOINT, IPV6_ENDPOINT, InputError, exact, now, profile, read_json, timestamp
from .storage import create_run, write
from .transport import Transport
from .browser import parse_bundle

MOTIVATIONS = {
    "service_eligibility": "服务范围、合同与验证要求；需要核对官方条件。",
    "routing_integrity": "请求路径和会话上下文能否被解释；本地能测路径，不能读取平台判断。",
    "network_reputation": "限制共享网络上的自动化滥用，同时减少企业网络等正常场景的误伤。",
    "fraud_prevention": "识别异常注册、支付和账号滥用；IP 情报只是其中一个输入。",
    "measurement_quality": "避免错误、陈旧或同源信号被当作独立证据，造成误判。",
    "account_relationships": "平台可能结合账户、设备、行为和时间关系；本工具无法看到其内部账户图。",
}
STATE_NAMES = {"ok": "已取得", "partial": "部分字段缺失", "skipped": "未启用", "missing_key": "未配置密钥",
               "quota_exceeded": "配额或套餐限制", "auth_error": "认证或访问受限", "timeout": "超时",
               "error": "查询失败", "invalid_response": "响应不符合接口契约", "blocked_dependency": "缺少可用的目标 IP"}
LABELS = {"vpn": "VPN", "proxy": "代理", "tor": "Tor", "hosting": "托管网络", "mobile": "移动网络",
          "recent_abuse": "近期滥用", "active_vpn": "活跃 VPN", "active_tor": "活跃 Tor"}


def scan_plan(network=False, providers=(), ipv6=False, target="agent"):
    providers = list(dict.fromkeys(providers))
    if any(p not in PROVIDERS for p in providers):
        raise InputError("未知的情报来源。")
    if (providers or ipv6) and not network:
        raise InputError("外部情报与 IPv6 测量必须显式启用 --network。")
    if target not in ("agent", "browser"):
        raise InputError("检测对象应为 agent 或 browser。")
    endpoints = []
    if network:
        endpoints.append({"recipient": "api.ipify.org", "max_requests": 1, "fields": ["request_source_ip"]})
    if ipv6:
        endpoints.append({"recipient": "api6.ipify.org", "max_requests": 1, "fields": ["request_source_ip"]})
    for p in providers:
        fields = ["request_source_ip", "queried_ip", "query_profile"]
        if PROVIDERS[p]["key"]:
            fields.append("provider_key_if_configured")
        endpoints.append({"recipient": PROVIDERS[p]["host"], "provider": p, "max_requests": 2 if ipv6 else 1,
                          "fields": fields,
                          "profile": PROVIDERS[p]["profile"], "requires_key": PROVIDERS[p]["key_required"]})
    return {"version": __version__, "target": target, "providers": providers, "external_services": endpoints,
            "retries": 0, "redirects": False, "socket_timeout_seconds": 8,
            "dns_timeout": "operating-system controlled", "credentials_in_model": False,
            "notice": "仅支持密钥的选定来源会在本地读取其密钥。IPWhois 不读取或发送密钥。套餐费用以供应商为准；不会自动注册或购买服务。"}


def finding(code, layer, motivation, state, statement, action, counterexample, refs):
    return {"id": code, "layer": layer, "motivation": motivation, "state": state, "statement": statement,
            "next_step": action, "normal_counterexample": counterexample, "evidence_refs": refs,
            "basis": "zhibi_interpretation_of_measurements"}


def interpret(records):
    findings = []
    for r in records:
        ref = r["subject"] + ":" + r["provider"]
        name = PROVIDERS[r["provider"]]["name"]
        if r["status"] not in ("ok", "partial"):
            findings.append(finding(ref + ":coverage", "L2", "measurement_quality", "unknown",
                name + "：" + STATE_NAMES[r["status"]] + "，没有可用结论。",
                "需要该来源时先核对密钥、配额和网络；不要把失败当成零风险。",
                "服务限流或网络失败与用户是否存在欺诈没有等价关系。", [ref]))
            continue
        facts = r["facts"]
        if r["missing_fields"]:
            findings.append(finding(ref + ":coverage", "L2", "measurement_quality", "unknown",
                name + " 没有覆盖全部预期字段。", "查看缺失字段和实际套餐；只解释已返回的数据。",
                "匿名接口可以返回归属而省略所有代理标签。", [ref]))
        labels = [LABELS[k] for k, v in facts["flags"].items() if v is True and k != "mobile"]
        if labels:
            findings.append(finding(ref + ":labels", "L2", "network_reputation", "review",
                name + " 标记了：" + "、".join(labels) + "。",
                "核对网络用途、标签时效及其他来源。怀疑误标时向该数据源申请更正。",
                "企业出口、隐私 VPN 和多人共享地址也可能具有这些标签；标签不证明个人滥用。", [ref]))
        for score in facts["scores"]:
            findings.append(finding(ref + ":" + score["name"], "L2", "fraud_prevention", "observed",
                name + " 返回 " + score["name"] + " = " + str(score["value"]) + "/" + str(score["scale"]) + "。",
                "结合该来源的查询参数、评分对象与观察窗口解释，不与其他评分取平均。",
                "网段滥用比例、IP 欺诈评分和举报置信度的对象与含义不同；都不是 账号处置概率。", [ref]))
        if facts["total_reports"] is not None:
            findings.append(finding(ref + ":reports", "L2", "network_reputation", "observed",
                "选定窗口内举报数：" + str(facts["total_reports"]) + "；独立举报者数：" + str(facts["distinct_reporters"]) + "。",
                "核对最近举报日期与窗口，必要时由网络运营方处理问题。",
                "同一地址可能被多人使用，历史举报不能直接归因于当前使用者。", [ref]))
    for subject in sorted({r["subject"] for r in records}):
        valid = [r for r in records if r["subject"] == subject and r["facts"]]
        for field in ("country_code", "asn"):
            values = {r["facts"][field] for r in valid if r["facts"][field] is not None}
            if len(values) > 1:
                refs = [subject + ":" + r["provider"] for r in valid if r["facts"][field] is not None]
                findings.append(finding(subject + ":conflict:" + field, "L2", "measurement_quality", "review",
                    "不同来源对 " + field + " 的描述不一致。", "核对数据来源、更新时间与字段定义，保留分歧。",
                    "归属注册地和实际地理定位可能不同；多数票不等于真值。", refs))
        for label in LABELS:
            values = {r["facts"]["flags"][label] for r in valid if r["facts"]["flags"][label] is not None}
            if len(values) > 1:
                refs = [subject + ":" + r["provider"] for r in valid if r["facts"]["flags"][label] is not None]
                findings.append(finding(subject + ":conflict:" + label, "L2", "measurement_quality", "review",
                    "不同来源的 " + LABELS[label] + " 标签存在分歧。", "保留各来源的定义和时间，先排除数据覆盖差异。",
                    "供应商采集范围、刷新周期和代理定义可以不同。", refs))
    return findings


def evidence_graph(records, findings, paths=()):
    nodes, edges = {}, []
    for mid, label in MOTIVATIONS.items():
        nodes["motivation:" + mid] = {"id": "motivation:" + mid, "type": "research_motivation", "label": label}
    for p in paths:
        nodes[p["id"]] = {"id": p["id"], "type": "local_path_observation", "status": p["status"], "at": p["at"]}
    for r in records:
        sid, oid = "source:" + r["provider"], r["subject"] + ":" + r["provider"]
        nodes[sid] = {"id": sid, "type": "public_source", "url": r["source"]}
        nodes[oid] = {"id": oid, "type": "observation", "status": r["status"], "at": r["queried_at"], "subject": r["subject"]}
        edges.append({"from": sid, "to": oid, "relation": "reported_by_source"})
        for upstream in r["upstream_sources"]:
            uid = "upstream:" + upstream
            nodes[uid] = {"id": uid, "type": "declared_upstream", "label": upstream}
            edges.append({"from": uid, "to": sid, "relation": "shared_data_dependency"})
    for f in findings:
        fid, aid = "finding:" + f["id"], "action:" + f["id"]
        nodes[fid] = {"id": fid, "type": "interpretation", "state": f["state"]}
        nodes[aid] = {"id": aid, "type": "next_step", "label": f["next_step"]}
        edges.extend([{"from": ref, "to": fid, "relation": "evidence_for"} for ref in f["evidence_refs"] if ref in nodes])
        edges += [{"from": "motivation:" + f["motivation"], "to": fid, "relation": "research_context"},
                  {"from": fid, "to": aid, "relation": "suggests"}]
    return {"nodes": list(nodes.values()), "edges": edges,
            "scope": "Local evidence lineage only; not the upstream service's internal account graph."}


def browser_paths(bundle, items, context):
    if not bundle or not bundle["network"]:
        return [], [], []
    network = bundle["network"]
    automated = next(o for o in bundle["observations"] if o["check_id"] == "browser.context")["facts"]["automated"]
    def fresh(at):
        return -60 <= (timestamp(now()) - timestamp(at)).total_seconds() <= 900
    paths, findings, flows = [], [], []
    for family in (4, 6):
        obs = network["ipv" + str(family)]
        pid = "path:browser-ipv" + str(family)
        paths.append({"id": pid, "status": obs["status"], "at": obs["at"], "endpoint": obs["endpoint"], "automated": automated, "route_intent": context["route_intent"]})
        if obs["status"] != "skipped":
            flows.append({"recipient": "api.ipify.org" if family == 4 else "api6.ipify.org", "purpose": "imported browser observation", "fields": ["request_source_ip"], "sent": True})
        agent = next((o for o in items if o["check_id"] == ("network.egress" if family == 4 else "network.ipv6")), None)
        comparable = (not automated and obs["status"] == "ok" and fresh(obs["at"]) and agent and agent["status"] == "ok"
                      and fresh(agent["at"]) and abs((timestamp(obs["at"]) - timestamp(agent["at"])).total_seconds()) <= 300
                      and agent["facts"]["endpoint"] == obs["endpoint"])
        same = ipaddress.ip_address(obs["ip"]) == ipaddress.ip_address(agent["facts"]["ip"]) if comparable else None
        paths[-1]["matches_agent"] = same
    rtc = network["webrtc"]
    paths.append({"id": "path:webrtc", "status": rtc["status"], "at": rtc["at"], "endpoint": rtc["endpoint"],
                  "candidate_count": len(rtc["candidates"]), "types": sorted({c["type"] for c in rtc["candidates"]}),
                  "complete": rtc["complete"], "automated": automated})
    if rtc["status"] not in ("skipped", "unsupported"):
        flows.append({"recipient": "stun.l.google.com:19302", "purpose": "imported STUN observation", "fields": ["request_source_ip", "stun_binding"], "sent": True})
    comparisons = []
    if not automated and rtc["status"] == "ok" and fresh(rtc["at"]):
        for candidate in rtc["candidates"]:
            if candidate["mdns"] or candidate["type"] != "srflx":
                continue
            address = ipaddress.ip_address(candidate["address"])
            https = network["ipv" + str(address.version)]
            if address.is_global and not address.is_multicast and https["status"] == "ok" and fresh(https["at"]) and abs((timestamp(https["at"]) - timestamp(rtc["at"])).total_seconds()) <= 300:
                comparisons.append(address == ipaddress.ip_address(https["ip"]))
    mismatch = any(value is False for value in comparisons)
    paths[-1]["https_relation"] = "different" if mismatch else "same_observed" if comparisons else "unknown"
    return paths, interpret_paths(paths), flows


def interpret_paths(paths):
    findings = []
    for p in paths:
        if p["id"] == "path:webrtc":
            relation = p["https_relation"]
            findings.append(finding("path:webrtc", "L1", "routing_integrity", "review" if relation == "different" else "observed" if relation == "same_observed" else "unknown",
                "WebRTC 与同地址族 HTTPS 观测" + ("出现不同出口。" if relation == "different" else "中的可比出口一致。" if relation == "same_observed" else "尚不能比较。"),
                "结合预期检查 UDP/STUN 与 HTTPS 路径；未取得候选时先确认浏览器和网络是否支持测量。",
                "不同协议可使用不同路径；mDNS、浏览器隐私机制或 UDP 被阻断都可能使候选不可见。", [p["id"]]))
        else:
            same, family = p["matches_agent"], p["id"][-1]
            state = "unknown" if same is None else "observed" if same or p["route_intent"] == "different" else "review"
            statement = "浏览器与 Agent 的 IPv" + family + (" 出口一致。" if same else " 出口不同。" if same is False else " 当前不具备可比观测。")
            findings.append(finding(p["id"], "L1", "routing_integrity", state, statement,
                "核对两者是否应使用相同路径；在实际浏览器与当前终端、相近时间复测。",
                "远程 Agent、分流策略、不同设备可以合理地使用不同出口。", [p["id"]]))
    return findings


def validate_scan(report):
    fields = {"format", "version", "generated_at", "sample", "target", "subjects", "baseline", "intelligence", "findings", "graph", "paths", "data_flows", "unobserved", "plan"}
    exact(report, fields | {"ipv6_confirmation", "browser_details"}, fields)
    from .browser_details import validate_summary
    validate_summary(report.get("browser_details"))
    if report["format"] != "zhibi-scan-1" or type(report["sample"]) is not bool or report["target"] not in ("agent", "browser"):
        raise InputError("不是有效的知彼扫描报告。")
    timestamp(report["generated_at"])
    validate_report(report["baseline"])
    if report["sample"] != report["baseline"]["sample"]:
        raise InputError("合成与真实标记不一致。")
    validate_records(report["intelligence"])
    paths = report["paths"]
    if not isinstance(paths, list) or len(paths) not in (0, 3):
        raise InputError("路径记录数量无效。")
    seen = set()
    for p in paths:
        common = {"id", "status", "at", "endpoint", "automated"}
        rtc = p.get("id") == "path:webrtc" if isinstance(p, dict) else False
        required = common | ({"candidate_count", "types", "complete", "https_relation"} if rtc else {"matches_agent", "route_intent"})
        exact(p, required, required)
        if p["id"] in seen or p["id"] not in {"path:browser-ipv4", "path:browser-ipv6", "path:webrtc"} or type(p["automated"]) is not bool:
            raise InputError("路径记录无效或重复。")
        seen.add(p["id"])
        timestamp(p["at"])
        endpoint = "stun:stun.l.google.com:19302" if rtc else IPV6_ENDPOINT if p["id"].endswith("6") else ENDPOINT
        if p["endpoint"] != endpoint:
            raise InputError("路径端点不在范围内。")
        if rtc:
            if p["status"] not in {"ok", "error", "timeout", "skipped", "unsupported", "no_candidates"} or type(p["complete"]) is not bool or type(p["candidate_count"]) is not int or not 0 <= p["candidate_count"] <= 64:
                raise InputError("WebRTC 摘要无效。")
            if not isinstance(p["types"], list) or len(p["types"]) > 4 or any(t not in {"host", "srflx", "relay", "prflx"} for t in p["types"]) or p["https_relation"] not in {"unknown", "different", "same_observed"}:
                raise InputError("WebRTC 关系无效。")
            if p["https_relation"] != "unknown" and (p["automated"] or p["status"] != "ok" or not p["complete"]):
                raise InputError("缺少可比 WebRTC 观测。")
        else:
            if p["status"] not in {"ok", "error", "timeout", "skipped", "invalid_response", "quota_exceeded"} or (p["matches_agent"] is not None and type(p["matches_agent"]) is not bool) or p["route_intent"] not in {"same", "different", "unknown"}:
                raise InputError("HTTPS 路径关系无效。")
            if p["matches_agent"] is not None and (p["automated"] or p["status"] != "ok"):
                raise InputError("缺少可比 HTTPS 观测。")
    expected = interpret_paths(paths) + interpret(report["intelligence"])
    if report["findings"] != expected or report["graph"] != evidence_graph(report["intelligence"], expected, paths):
        raise InputError("解释或证据图与观测不一致；拒绝导入任意结论。")
    if not isinstance(report["unobserved"], list) or any(v not in {"platform_account_graph", "account_payment_verification", "actual_dns_path", "webrtc"} for v in report["unobserved"]):
        raise InputError("覆盖范围无效。")
    if not isinstance(report["subjects"], list) or len(report["subjects"]) > 2:
        raise InputError("扫描对象数量无效。")
    for s in report["subjects"]:
        exact(s, {"id", "family", "measured_at", "endpoint"}, {"id", "family", "measured_at", "endpoint"})
        if s["id"] not in {report["target"] + "-ipv4", report["target"] + "-ipv6"} or type(s["family"]) is not int or s["family"] not in (4, 6) or s["id"][-1] != str(s["family"]) or s["endpoint"] != (ENDPOINT if s["family"] == 4 else IPV6_ENDPOINT):
            raise InputError("扫描对象与端点不一致。")
        timestamp(s["measured_at"])
    hosts = {p["host"] for p in PROVIDERS.values()} | {"api.ipify.org", "api6.ipify.org", "stun.l.google.com:19302"}
    if not isinstance(report["data_flows"], list) or len(report["data_flows"]) > 5 + 2 * len(PROVIDERS):
        raise InputError("请求记录无效。")
    for flow in report["data_flows"]:
        exact(flow, {"provider", "recipient", "purpose", "fields", "sent"}, {"recipient", "fields", "sent"})
        if flow["recipient"] not in hosts or type(flow["sent"]) is not bool or not isinstance(flow["fields"], list) or any(f not in {"request_source_ip", "network_metadata", "queried_ip", "query_profile", "provider_api_key", "stun_binding"} for f in flow["fields"]):
            raise InputError("请求记录包含未知字段。")
    from .ipv6_policy import validate_confirmation
    validate_confirmation(report)
    return report


def run_scan(network=False, providers=(), ipv6=False, browser_path=None, target="agent", out=None,
             profile_path=None, client=None, transport=None, keys=None, sample=False, collector=None, progress=None):
    plan = scan_plan(network, providers, ipv6, target)
    context = profile(read_json(profile_path) if profile_path else None)
    bundle = parse_bundle(read_json(browser_path)) if browser_path else None
    browser = bundle["observations"] if bundle else None
    if target == "browser" and not browser:
        raise InputError("browser 目标需要 --browser 提供实际浏览器导出的文件。")
    # Reserve output before any outbound request; a failed destination never incurs API charges.
    keys = load_keys() if keys is None and any(PROVIDERS[p]["key"] for p in providers) else (keys or {})
    directory = create_run(out)
    progress = progress or (lambda message: None)
    progress("正在读取本地信息并测量已选择的网络…")
    transport = transport or Transport(network, ipv6=ipv6)
    items = (collector or collect)(transport, browser)
    baseline = evaluate(items, context, list(transport.flows), sample=sample)
    subjects = []
    check_ids = (("network.egress", "agent-ipv4"), ("network.ipv6", "agent-ipv6")) if target == "agent" else (("browser.egress", "browser-ipv4"),)
    for cid, sid in check_ids:
        obs = next((o for o in items if o["check_id"] == cid), None)
        if not obs or obs["status"] != "ok":
            continue
        age = (timestamp(now()) - timestamp(obs["at"])).total_seconds()
        if not -60 <= age <= 900:
            continue
        if target == "browser" and next(o for o in browser if o["check_id"] == "browser.context")["facts"]["automated"]:
            continue
        try:
            address = public_ip(obs["facts"]["ip"])
        except InputError:
            continue
        subjects.append({"id": sid, "ip": address, "family": ipaddress.ip_address(address).version, "measured_at": obs["at"], "endpoint": obs["facts"]["endpoint"]})
    if target == "browser" and ipv6 and bundle and bundle["network"]:
        obs = bundle["network"]["ipv6"]
        automated = next(o for o in browser if o["check_id"] == "browser.context")["facts"]["automated"]
        if obs["status"] == "ok" and not automated and -60 <= (timestamp(now()) - timestamp(obs["at"])).total_seconds() <= 900:
            try:
                address = public_ip(obs["ip"])
                subjects.append({"id": "browser-ipv6", "ip": address, "family": 6, "measured_at": obs["at"], "endpoint": obs["endpoint"]})
            except InputError:
                pass
    client = client or Client(network)
    records = []
    for subject in subjects:
        for provider in plan["providers"]:
            # Progress contains fixed labels only; never addresses, keys or provider response text.
            name = PROVIDERS[provider]["name"]
            progress("正在查询 " + name + "…")
            record = query(client, provider, subject["ip"], subject["id"], keys.get(provider))
            records.append(record)
            progress(name + "：" + STATE_NAMES[record["status"]])
    if not subjects:
        for p in plan["providers"]:
            records.append({"provider": p, "subject": target + "-unmeasured", "status": "blocked_dependency",
                "queried_at": now(), "source_updated_at": None, "observation_window_days": None,
                "product_tier": "unknown", "query_profile": PROVIDERS[p]["profile"], "source": PROVIDERS[p]["docs"],
                "upstream_sources": PROVIDERS[p]["upstream_sources"], "facts": None, "missing_fields": []})
    progress("正在生成本地报告…")
    paths, path_findings, browser_flows = browser_paths(bundle, items, context)
    findings = path_findings + interpret(records)
    report = {"format": "zhibi-scan-1", "version": __version__, "generated_at": now(), "sample": sample,
              "target": target, "subjects": [{k: v for k, v in s.items() if k != "ip"} for s in subjects],
              "baseline": baseline, "intelligence": records, "findings": findings,
              "graph": evidence_graph(records, findings, paths), "paths": paths, "data_flows": list(transport.flows) + browser_flows + client.flows,
              "unobserved": ["platform_account_graph", "account_payment_verification", "actual_dns_path"] + ([] if bundle and bundle["network"] and bundle["network"]["webrtc"]["status"] == "ok" else ["webrtc" ]),
              "plan": plan}
    if bundle and "details" in bundle:
        from .browser_details import summarize
        report["browser_details"] = summarize(bundle["details"])
    summary = scan_summary(report)
    snapshot = {"format": "zhibi-scan-private-1", "subjects": subjects,
                "observations": items, "browser": bundle, "profile": context, "sample": sample, "generated_at": report["generated_at"]}
    write(directory / "snapshot.private.json", snapshot)
    write(directory / "report.json", report)
    write(directory / "agent-summary.json", summary)
    write(directory / "report.html", render_scan(report, snapshot))
    write(directory / "report.md", scan_markdown(report))
    progress("报告已生成。")
    return {"directory": str(directory), "report": str(directory / "report.html"), "summary": summary}


def scan_summary(report):
    validate_scan(report)
    from .assessment import assess_scan
    # No provider strings, raw addresses, arbitrary imported text, device attributes or credentials.
    return {"format": "zhibi-scan-summary-2", "sample": report["sample"], "target": report["target"],
            "assessment": assess_scan(report),
            "providers": [{"provider": r["provider"], "subject": r["subject"], "status": r["status"],
                           "missing_fields": r["missing_fields"], "product_tier": r["product_tier"]}
                          for r in report["intelligence"]],
            "paths": report["paths"],
            "browser_details": report.get("browser_details"),
            "contacted_services": sorted({f["recipient"] for f in report["data_flows"] if f["sent"]}),
            "unobserved": report["unobserved"],
            "notice": "仅分享固定解释与选定数值。完整结果和测量 IP 留在本机；未查询不等于低风险。"}


def scan_markdown(report):
    validate_scan(report)
    from .assessment import assess_scan
    decision = assess_scan(report)
    overview = decision["overview"]
    lines = ["# 知彼 · IP 与环境检查", "", "## " + overview["headline"], "", overview["next_action"]["title"], "", overview["next_step"], "", "完成依据：" + overview["next_action"]["verify"], ""]
    lines += ["| 检查项 | 结果 | 建议 |", "| --- | --- | --- |"]
    lines += ["| " + " | ".join(c[k] for k in ("label", "result", "advice")) + " |" for c in overview["table_rows"]]
    lines += ["", overview["scope"], ""]
    from .browser_details import rows
    optional_rows = rows(report.get("browser_details"))
    if optional_rows:
        lines += ["<details><summary>可选浏览器检查</summary>", "", "| 检查项 | 结果 | 建议 |", "| --- | --- | --- |"]
        lines += ["| " + " | ".join(row) + " |" for row in optional_rows]
        lines += ["", "实际属性只在本地 HTML 的读数详情中展示；这些观察不增加 IP 风险项。", "", "</details>", ""]
    if overview["pending_count"]:
        lines += ["还有 " + str(overview["pending_count"]) + " 项检查尚未确认，详见下方测量缺项。", ""]
    lines += ["<details>", "<summary>查看检测依据与技术详情</summary>", "",
             "| 检查 | 结论 | 你该做什么 |", "| --- | --- | --- |"]
    lines += ["| " + " | ".join(r[k] for k in ("label", "verdict", "action")) + " |" for r in decision["conclusions"]]
    lines += ["", "## 检测工具的缺项", ""] + ["- " + g for g in decision["tool_gaps"]]
    lines += ["", "## 可选增强（不影响默认检测）", "",
              "IPQS、AbuseIPDB、ipapi.is 均为自选。无需全部配置，保存 Key 也不会自动启用查询。", ""]
    for item in decision["optional_enhancements"]:
        states = "；".join(obs["subject"] + "：" + STATE_NAMES[obs["status"]] for obs in item["observations"]) or "未选择"
        lines += ["- " + item["name"] + "：" + item["capability"] + "。本次：" + states + "。"
                  + "[自行注册](" + item["signup_url"] + ")，在自己的终端运行 `python3 <Skill目录>/scripts/zhibi.py "
                  + item["configure_command"] + "` 隐藏输入 Key；之后显式选择该来源复测。"]
    lines += ["", "## 来源与依据", ""]
    for r in report["intelligence"]:
        lines += ["- " + r["subject"] + " / " + r["provider"] + "：" + STATE_NAMES[r["status"]]]
    for f in report["findings"]:
        lines += ["", "## " + f["statement"], "", "平台动机（研究视角）：" + MOTIVATIONS[f["motivation"]],
                  "", "下一步：" + f["next_step"], "", "正常反例：" + f["normal_counterexample"]]
    lines += ["", "</details>", ""]
    return "\n".join(lines) + "\n"


def render_scan(report, snapshot=None):
    validate_scan(report)
    from .scan_report import render
    return render(report, snapshot)


def compare_scans(before_dir, after_dir, same_context=False):
    """Read private IPs inside the core; export only comparisons, never identifiers."""
    reports = [validate_scan(read_json(Path(p) / "report.json")) for p in (before_dir, after_dir)]
    left, right = reports
    if left["sample"] != right["sample"]:
        raise InputError("不能比较合成场景与真实测量。")
    if timestamp(right["generated_at"]) <= timestamp(left["generated_at"]):
        raise InputError("复查报告应晚于原报告。")
    result = {"format": "zhibi-scan-comparison-1", "sample": left["sample"], "comparability": "not_established",
              "subject_changes": [], "provider_changes": [],
              "notice": "同上下文需要用户声明；仅比较观测变化，不推出因果、封号概率或风险升降。"}
    if not same_context or left["target"] != right["target"]:
        return result
    snapshots = [read_json(Path(p) / "snapshot.private.json") for p in (before_dir, after_dir)]
    addresses = []
    for snapshot, report in zip(snapshots, reports):
        required = {"format", "subjects", "observations", "browser", "profile", "sample", "generated_at"}
        exact(snapshot, required, required)
        if snapshot["format"] != "zhibi-scan-private-1" or snapshot["sample"] != report["sample"] or snapshot["generated_at"] != report["generated_at"]:
            raise InputError("私人快照与报告不对应。")
        profile(snapshot["profile"])
        subjects = snapshot["subjects"]
        if not isinstance(subjects, list) or len(subjects) > 2:
            raise InputError("私人快照对象无效。")
        mapping = {}
        for s in subjects:
            exact(s, {"id", "family", "measured_at", "endpoint", "ip"}, {"id", "family", "measured_at", "endpoint", "ip"})
            if s["id"] in mapping or {k: v for k, v in s.items() if k != "ip"} not in report["subjects"]:
                raise InputError("私人快照对象不匹配。")
            mapping[s["id"]] = public_ip(s["ip"])
        if len(mapping) != len(report["subjects"]):
            raise InputError("私人快照对象不完整。")
        addresses.append(mapping)
    if snapshots[0]["profile"] != snapshots[1]["profile"]:
        return result
    result["comparability"] = "user_declared_same_context"
    comparable = set()
    for sid in sorted(addresses[0].keys() | addresses[1].keys()):
        same = addresses[0].get(sid) == addresses[1].get(sid) and sid in addresses[0] and sid in addresses[1]
        if same:
            comparable.add(sid)
        result["subject_changes"].append({"subject": sid, "same_observed_ip": same,
            "state": "same_subject" if same else "subject_changed_or_unmeasured"})
    a = {(r["subject"], r["provider"]): r for r in left["intelligence"]}
    b = {(r["subject"], r["provider"]): r for r in right["intelligence"]}
    for sid, provider in sorted(a.keys() | b.keys()):
        old, new = a.get((sid, provider)), b.get((sid, provider))
        if sid not in comparable or old is None or new is None:
            state = "not_comparable"
        elif old["query_profile"] != new["query_profile"] or old["product_tier"] != new["product_tier"]:
            state = "query_coverage_changed"
        elif old["status"] != new["status"]:
            state = "measurement_status_changed"
        elif old["facts"] != new["facts"]:
            state = "observed_values_changed"
        else:
            state = "unchanged"
        result["provider_changes"].append({"subject": sid, "provider": provider, "state": state})
    return result
