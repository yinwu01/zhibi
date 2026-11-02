"""Small reviewed rules with provenance. No learned or arbitrary risk score."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from importlib.resources import files

from . import __version__
from .models import ASSESSMENTS, STATUSES, InputError, bounded_string, coverage, exact, profile, timestamp, validate_observations

LABELS = {
    "host.runtime": "运行环境", "host.proxy": "代理环境变量摘要", "host.dns": "DNS 配置摘要",
    "client.installed": "目标客户端 安装存在性", "browser.context": "实际浏览器上下文",
    "browser.egress": "浏览器出口", "network.egress": "命令行出口", "network.metadata": "第三方 IP 归属",
    "network.ipv6": "IPv6 端点出口", "network.connectivity": "公共首页连接诊断",
}
STATUS_TEXT = {"ok": "已取得观测", "error": "测量失败", "timeout": "测量超时",
               "unsupported": "当前平台不支持此检查", "skipped": "尚未测量"}


def bundle(name):
    return json.loads(files("zhibi").joinpath("data").joinpath(name + ".json").read_text(encoding="utf-8"))


def source_state(source, at):
    checked = timestamp(source["checked_at"])
    if checked > at:
        return "future"
    if source["effective_at"] and timestamp(source["effective_at"]) > at:
        return "not_effective"
    days = source["review_after_days"]
    if days is not None and (at - checked).total_seconds() > days * 86400:
        return "stale"
    return "current"


def decide(rule, obs, context, at):
    key = rule["id"]
    item = obs.get(key)
    if key == "policy.context":
        return ("needs_confirmation", "注册条件需要按真实情况核对。",
                "打开报告中的官方来源，核对真实使用地区、目标产品与适用注册条件；在官方流程完成验证。",
                "记录所核对政策的适用范围与生效日期。")
    if key == "history.coverage":
        return ("unknown", "本次检查无法判断长期稳定性或平台内部关联。",
                "需要复查变化时保存前后两次报告；案例研究另行记录观察窗口。",
                "比较可比观测，并区分配置变化与账号结果。")
    if key == "network.connectivity" and item and item["status"] in ("ok", "error", "timeout"):
        facts = item["facts"]
        if facts["outcome"] == "http_response":
            code = facts["http_status"]
            return ("verified" if 200 <= code < 300 else "needs_confirmation",
                    "公共首页 HEAD 请求取得 HTTP " + str(code) + " 响应。",
                    "在实际浏览器核对页面提示；HEAD 响应可能与浏览器页面不同，也没有验证登录。",
                    "不跟随重定向、不重试；需要时在同一客户端重新测量。")
        return ("unknown", "公共首页连接未完成：" + facts["outcome"] + "。",
                "按解析、证书、超时或传输层排查；代理可能使故障层次不可区分。保持 TLS 验证。",
                "修复已定位的连接问题后复测；不从连接失败推断账号限制。")
    if key == "network.route":
        a, b, browser = (obs.get(k) for k in ("network.egress", "browser.egress", "browser.context"))
        if not all(x and x["status"] == "ok" for x in (a, b, browser)):
            return ("unknown", "尚不能比较浏览器与命令行出口。", "可选：在实际使用的浏览器导出联网探针，再运行带 --network 的检查。", "两侧需成功测量同一端点。")
        delta = abs((timestamp(a["at"]) - timestamp(b["at"])).total_seconds())
        fresh = all(-30 <= (at - timestamp(x["at"])).total_seconds() <= 900 for x in (a, b, browser))
        if (browser["facts"]["automated"] or delta > 300 or not fresh or
                a["facts"]["endpoint"] != b["facts"]["endpoint"] or a["facts"]["family"] != b["facts"]["family"]):
            return ("unknown", "两次出口观测不具备可比条件。", "使用实际浏览器，在五分钟内重测同一端点和地址族。", "自动化浏览器、过期或不匹配的样本不能替代实际使用环境。")
        same = a["facts"]["ip"] == b["facts"]["ip"]
        if same:
            return ("verified", "两个入口在这次诊断端点测量中使用相同出口。",
                    "保留观测即可；该结论仅适用于本次端点与时间窗口。", "变更配置后按相同条件重测。")
        if context["route_intent"] == "different":
            return ("verified", "出口不同，与用户声明的分流预期一致。",
                    "保留有意分流；仅在实际访问出现问题时继续定位。", "配置变更后核对分流是否仍符合预期。")
        return ("needs_confirmation", "两个入口出口不同，需要确认是否符合预期。",
                "核对浏览器与命令行各自的网络设置；确认属于意外分流后再处理。", "使用相同端点与地址族，在五分钟内复测。")
    if key == "client.installed" and context["product"] == "web":
        return ("not_applicable", "使用网页版无需先安装 目标客户端。", None, None)
    if not item or item["status"] != "ok":
        return ("unknown", "这项检查尚未取得可用结果。",
                "查看测量状态；按需启用对应检查或补充浏览器文件。", "取得成功观测后重新评估。")
    facts = item["facts"]
    if key == "host.proxy":
        if facts["unsupported_scheme"] or facts["conflicting"]:
            return ("needs_confirmation", "代理环境变量存在本工具无法明确解释的配置。",
                    "检查大小写变量是否冲突，以及是否使用 SOCKS；本工具的 HTTP 适配器不支持 SOCKS。", "修正本工具的运行配置，或改用实际浏览器探针复验。")
        return ("verified", "已检查代理环境变量的配置状态。",
                "此结果不涵盖系统代理、浏览器扩展或透明代理。", "网络路径仍需独立测量。")
    if key == "browser.context":
        fresh = -30 <= (at - timestamp(item["at"])).total_seconds() <= 900
        if facts["automated"] or not fresh:
            return ("unknown", "浏览器上下文为自动化样本或已过期。",
                    "在准备使用的浏览器手动打开探针并重新导出。", "重新导入十五分钟内的人工浏览器样本。")
        if not facts["cookies_enabled"] or not facts["storage_available"]:
            return ("needs_confirmation", "当前探针页的 Cookie 或存储能力受限。",
                    "检查实际 目标站点页面的权限提示；本地文件页的限制可能不影响该站点。", "在实际站点核实后再调整对应设置。")
        return ("verified", "当前探针页的基础浏览器能力可用。",
                "无需为了匹配地区而改变自己的语言；实际站点权限需单独核实。", "更换浏览器或权限设置后复查。")
    if key == "client.installed":
        if not facts["present"]:
            return ("needs_action", "当前命令搜索路径中未找到 目标客户端。",
                    "若使用 目标客户端，按官方安装文档安装；若已安装，检查当前终端的 PATH。", "在新的终端中重新运行检查。")
        return ("verified", "命令搜索路径中可找到 目标客户端。", "这不代表已登录或账号状态正常。", "实际客户端状态需在官方客户端确认。")
    if key == "host.dns":
        return ("verified", "已读取 DNS 配置文件中的解析器数量。",
                "该观测不能判断 DNS 泄漏，也不涵盖浏览器安全 DNS。", "遇到实际解析故障时再针对对应客户端定位。")
    if key == "network.metadata":
        return ("verified", "已取得第三方国家与 ASN 信息。",
                "将归属信息作为背景；发现冲突时向数据源复核，不能据此判定注册资格。", "更换出口或数据源更新后重新查询。")
    if key == "network.ipv6":
        return ("verified", "IPv6 专用端点返回了 IPv6 出口。",
                "若使用代理，这可能是代理的出口；没有验证浏览器 IPv6 或是否绕过预期路径。",
                "只有明确路径预期并取得同一上下文的可比观测，才讨论泄漏。")
    raise InputError("规则没有对应的受控处理器。")


def evaluate(items, context=None, flows=None, sample=False, at=None, sources=None, claims=None):
    items = validate_observations(items)
    context = profile(context)
    at = at or datetime.now(timezone.utc)
    sources = sources if sources is not None else bundle("sources")
    rules = bundle("rules")
    claims = bundle("claims") if claims is None else claims
    claim_map = {c["id"]: c for c in claims}
    if any(r["claim"] not in claim_map for r in rules):
        raise InputError("规则引用的研究主张不存在。")
    rule_sources = {rule["id"]: list(dict.fromkeys(rule["sources"] + claim_map[rule["claim"]]["sources"]))
                    for rule in rules}
    used_sources = {sid for ids in rule_sources.values() for sid in ids}
    sources = [s for s in sources if s["id"] in used_sources]
    if {s["id"] for s in sources} != used_sources:
        raise InputError("规则或主张引用的来源不存在。")
    obs = {i["check_id"]: i for i in items}
    evidence = [{k: s[k] for k in ("id", "kind", "title", "source", "checked_at", "scope")} for s in sources]
    evidence.append({"id": "measurement", "kind": "project_design" if sample else "measurement",
                     "title": "合成示例观测" if sample else "本次本地观测",
                     "source": "synthetic fixture" if sample else "local snapshot (not exported)",
                     "checked_at": at.isoformat(), "scope": "模拟数据" if sample else "仅限当前设备、探针与执行时间。"})
    observations = [
        {"id": i["check_id"], "check_id": i["check_id"], "check_version": __version__,
         "measurement_status": i["status"], "observed_at": i["at"],
        "subject": ("actual_browser" if i["check_id"].startswith("browser.") else
                    "cli" if i["check_id"].startswith(("network.", "client.")) else "host"),
         "scope": LABELS[i["check_id"]], "summary": STATUS_TEXT[i["status"]],
         "limitations": ["采集状态不表示账号安全。"], "evidence_refs": ["measurement"]}
        for i in items
    ]
    for cid, subject, summary in [("intake.context", "user_input", "仅接受产品、阶段、地区代码与分流预期。"),
                                   ("history.context", "local_history", "没有平台内部关联或长期账号结果数据。")]:
        observations.append({"id": cid, "check_id": cid, "check_version": __version__,
                             "measurement_status": "ok" if cid == "intake.context" else "skipped",
                             "observed_at": at.isoformat(), "subject": subject, "scope": "背景信息",
                             "summary": summary, "limitations": ["不构成账号资格或长期结果证明。"],
                             "evidence_refs": ["method"]})
    existing = {o["id"] for o in observations}
    # Absent checks must remain visible as missing evidence.
    for rule in rules:
        for cid in rule["checks"]:
            if cid not in existing:
                observations.append({"id": cid, "check_id": cid, "check_version": __version__,
                                     "measurement_status": "skipped", "observed_at": None, "subject": "host",
                                     "scope": "缺少输入", "summary": "没有提供这项观测。",
                                     "limitations": ["不能推断结果。"], "evidence_refs": ["method"]})
                existing.add(cid)
    source_map = {s["id"]: s for s in sources}
    findings = []
    for rule in rules:
        assessment, statement, next_step, recheck = decide(rule, obs, context, at)
        limits = [rule["counterexample"]]
        claim = claim_map[rule["claim"]]
        if claim["status"] != "supported" or claim["scope_kind"] not in ("measurement_semantics", "official_disclosure"):
            assessment = "unknown"
            statement = "这条判断所依赖的主张尚不能作为产品结论。"
            limits.append("待验证假设、跨平台类比和已撤回主张不能直接生成确定判断。")
            next_step = "先审查主张的证据、适用范围和可反驳条件。"
        if rule["id"] == "network.route":
            limits.append("诊断端点不代表到 目标站点的路由；出口一致不代表账号不会被限制。")
        invalid = [sid for sid in rule_sources[rule["id"]] if source_state(source_map[sid], at) != "current"]
        if invalid:
            assessment = "needs_confirmation" if rule["id"] == "policy.context" else "unknown"
            limits.append("引用来源存在未生效、未来核对时间或超过复核期限的情况。")
            next_step = "先打开引用来源，核对适用范围、生效时间与更新内容，再解释该项。"
        findings.append({"id": rule["id"], "rule_id": rule["id"], "assessment": assessment,
                         "observation_ids": rule["checks"], "evidence_refs": rule_sources[rule["id"]] + ["measurement"],
                         "statement": statement, "limitations": limits, "next_step": next_step, "recheck": recheck})
    report = {"schema_version": "0.1", "sample": sample, "run_id": "demo" if sample else at.strftime("%Y%m%dT%H%M%S"),
              "generated_at": at.isoformat(), "purpose": {"registration": "registration_preparation",
              "troubleshooting": "troubleshooting", "recheck": "recheck"}[context["stage"]],
              "coverage": coverage(items), "observations": observations, "findings": findings,
              "evidence": evidence, "data_flows": flows or []}
    validate_report(report)
    return report


def validate_report(report):
    if not isinstance(report, dict) or report.get("schema_version") != "0.1":
        raise InputError("报告版本无效。")
    required = {"schema_version", "sample", "run_id", "generated_at", "purpose", "coverage",
                "observations", "findings", "evidence", "data_flows"}
    if set(report) != required or type(report["sample"]) is not bool:
        raise InputError("报告字段无效。")
    timestamp(report["generated_at"])
    if report["coverage"] not in ("complete", "partial", "unavailable"):
        raise InputError("覆盖状态无效。")
    if report["purpose"] not in ("registration_preparation", "troubleshooting", "recheck"):
        raise InputError("报告用途无效。")
    bounded_string(report["run_id"], 200)
    for field in ("observations", "findings", "evidence", "data_flows"):
        if not isinstance(report[field], list) or len(report[field]) > 100:
            raise InputError("报告列表无效。")
    fields = {
        "observations": {"id", "check_id", "check_version", "measurement_status", "observed_at", "subject",
                         "scope", "summary", "limitations", "evidence_refs"},
        "findings": {"id", "rule_id", "assessment", "observation_ids", "evidence_refs", "statement",
                     "limitations", "next_step", "recheck"},
        "evidence": {"id", "kind", "title", "source", "checked_at", "scope"},
        "data_flows": {"purpose", "recipient", "fields", "sent"},
    }
    nullable = {"observed_at", "checked_at", "next_step", "recheck"}
    lists = {"limitations", "evidence_refs", "observation_ids", "fields"}
    for section, keys in fields.items():
        for item in report[section]:
            exact(item, keys, keys)
            for key, value in item.items():
                if key in nullable and value is None:
                    continue
                if key in lists:
                    if not isinstance(value, list) or len(value) > 100:
                        raise InputError("报告子列表无效。")
                    for text in value:
                        bounded_string(text, 4000)
                    if key in ("evidence_refs", "observation_ids") and (not value or len(value) != len(set(value))):
                        raise InputError("报告引用列表无效。")
                elif key == "sent":
                    if type(value) is not bool:
                        raise InputError("数据流标记无效。")
                else:
                    bounded_string(value, 8000)
                    if not value:
                        raise InputError("报告必要文本为空。")
    for obs in report["observations"]:
        if obs["measurement_status"] not in STATUSES or obs["subject"] not in (
                "host", "actual_browser", "cli", "browser_cli_comparison", "user_input", "local_history"):
            raise InputError("观测状态或对象无效。")
        if obs["measurement_status"] == "ok" or obs["observed_at"] is not None:
            timestamp(obs["observed_at"])
    for source in report["evidence"]:
        if source["kind"] not in ("official_policy", "official_disclosure", "measurement", "code_review",
                                  "third_party", "cohort", "community", "project_design"):
            raise InputError("来源类别无效。")
        if source["checked_at"] is not None:
            timestamp(source["checked_at"])
    obs_ids = [x["id"] for x in report["observations"]]
    evidence_ids = [x["id"] for x in report["evidence"]]
    finding_ids = [x["id"] for x in report["findings"]]
    if any(len(x) != len(set(x)) for x in (obs_ids, evidence_ids, finding_ids)):
        raise InputError("报告 ID 重复。")
    for obs in report["observations"]:
        if not set(obs["evidence_refs"]) <= set(evidence_ids):
            raise InputError("观测来源引用不存在。")
    for finding in report["findings"]:
        if finding["assessment"] not in ASSESSMENTS:
            raise InputError("报告判断状态无效。")
        if not set(finding["observation_ids"]) <= set(obs_ids) or not set(finding["evidence_refs"]) <= set(evidence_ids):
            raise InputError("报告引用不存在。")
    return report


def explain(rule_id):
    rules = {r["id"]: r for r in bundle("rules")}
    if rule_id not in rules:
        raise InputError("未找到规则。")
    rule = rules[rule_id]
    claim = next(c for c in bundle("claims") if c["id"] == rule["claim"])
    return {"rule": rule, "claim": claim,
            "features": [f for f in bundle("features") if f["id"] in claim["features"]],
            "sources": [s for s in bundle("sources") if s["id"] in set(rule["sources"] + claim["sources"])],
            "edges": [{"from": cid, "relation": "feeds", "to": rule_id} for cid in rule["checks"]] +
                     [{"from": sid, "relation": "supports_scope_of", "to": rule_id} for sid in rule["sources"]]}
