"""Human-readable, local-only scan report. Never use this view as model input."""
import ipaddress
from datetime import datetime
from html import escape
from importlib.resources import files

from .browser import parse_bundle
from .intelligence import PROVIDERS, public_ip
from .models import InputError, exact, profile, validate_observations


def local_observations(report, snapshot):
    """Join a caller-selected private snapshot to its report, without exporting it."""
    if snapshot is None:
        return {}, {}
    fields = {"format", "subjects", "observations", "browser", "profile", "sample", "generated_at"}
    exact(snapshot, fields, fields)
    if (snapshot["format"] != "zhibi-scan-private-1" or snapshot["sample"] != report["sample"]
            or snapshot["generated_at"] != report["generated_at"]):
        raise InputError("私人快照与报告不对应。")
    profile(snapshot["profile"])
    observations = {o["check_id"]: o for o in validate_observations(snapshot["observations"])}
    bundle = snapshot["browser"]
    if bundle:
        exact(bundle, {"observations", "network", "environment", "details", "extras"}, {"observations", "network", "environment"})
        if bundle["network"] is None:
            parse_bundle({"schema_version": "1", "context": "user_opened_browser", "observations": bundle["observations"]})
        else:
            parse_bundle({"schema_version": "4" if "extras" in bundle else "3" if "details" in bundle else "2", "context": "user_opened_browser", **bundle})
        if any(observations.get(o["check_id"]) != o for o in bundle["observations"]):
            raise InputError("私人快照中的浏览器观测不一致。")
    from .browser_details import summarize
    if summarize(bundle.get("details") if bundle else None) != report.get("browser_details"):
        raise InputError("浏览器深入检查与私人快照不一致。")
    subjects = snapshot["subjects"]
    if not isinstance(subjects, list) or len(subjects) != len(report["subjects"]):
        raise InputError("私人快照检测对象不完整。")
    addresses = {}
    for subject in subjects:
        fields = {"id", "family", "measured_at", "endpoint", "ip"}
        exact(subject, fields, fields)
        if subject["id"] in addresses or {k: v for k, v in subject.items() if k != "ip"} not in report["subjects"]:
            raise InputError("私人快照检测对象不匹配。")
        address = public_ip(subject["ip"])
        if ipaddress.ip_address(address).version != subject["family"]:
            raise InputError("私人快照地址族不匹配。")
        if subject["id"] == "browser-ipv6":
            observed = bundle["network"]["ipv6"] if bundle and bundle["network"] else None
            at = observed["at"] if observed else None
            facts = observed
        else:
            cid = "browser.egress" if subject["id"] == "browser-ipv4" else "network.egress" if subject["family"] == 4 else "network.ipv6"
            observed = observations.get(cid)
            at = observed["at"] if observed else None
            facts = observed["facts"] if observed else None
        if (not observed or observed["status"] != "ok" or at != subject["measured_at"]
                or facts.get("endpoint") != subject["endpoint"] or public_ip(facts.get("ip")) != address):
            raise InputError("私人快照 IP 与对应测量不一致。")
        addresses[subject["id"]] = address
    return addresses, observations


def render(report, snapshot=None):
    from .scan import LABELS, STATE_NAMES
    from .assessment import assess_scan
    decision = assess_scan(report)
    overview = decision["overview"]
    addresses, observations = local_observations(report, snapshot)
    e = lambda value: escape(str(value), quote=True)
    state = lambda value: STATE_NAMES.get(value, {"unsupported": "不支持", "no_candidates": "无候选"}.get(value, value))
    records = report["intelligence"]
    valid = [r for r in records if r["facts"]]
    flag_count = sum(any(r["facts"]["flags"][key] is not None for r in valid)
                     for key in ("vpn", "proxy", "tor", "hosting"))
    score_names = {s["name"] for r in valid for s in r["facts"]["scores"]}
    score_count = len(score_names)
    identity = any(r["facts"][key] is not None for r in valid for key in ("asn", "country_code", "organization"))
    subject = "实际浏览器" if report["target"] == "browser" else "Agent 进程"
    primary = addresses.get(report["target"] + "-ipv4") or addresses.get(report["target"] + "-ipv6")
    headline = primary or ("未载入私人快照" if snapshot is None and report["subjects"] else "未取得可查询的出口")
    when = datetime.fromisoformat(report["generated_at"].replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d %H:%M %Z")

    def table(headers, rows, label):
        return '<div class="table-wrap" role="region" tabindex="0" aria-label="' + e(label) + '"><table><thead><tr>' + ''.join(
            '<th scope="col">' + e(h) + '</th>' for h in headers) + '</tr></thead><tbody>' + ''.join(
            '<tr>' + ''.join('<' + ('th scope="row"' if i == 0 else 'td') + '>' + e(v) + '</' + ('th' if i == 0 else 'td') + '>'
                             for i, v in enumerate(row)) + '</tr>' for row in rows) + '</tbody></table></div>'

    def detail(value):
        return "未返回" if value is None else str(value)

    # Preserve original values in the expandable evidence view.
    identity_rows = []
    for r in valid:
        f = r["facts"]
        identity_rows.append([r["subject"], PROVIDERS[r["provider"]]["name"], detail(f["country_code"]),
                              "AS" + str(f["asn"]) if f["asn"] is not None else "未返回",
                              detail(f["organization"]), detail(f["network_type"])])
    identity_html = table(["检测对象", "来源", "国家代码", "ASN", "组织", "网络类型"], identity_rows, "网络归属实测值") if identity_rows else '<p class="empty">没有可用归属数据。</p>'
    label_rows = []
    for key in ("vpn", "proxy", "tor", "hosting", "recent_abuse"):
        readings = []
        for r in valid:
            value = r["facts"]["flags"][key]
            if value is not None:
                readings.append(r["subject"] + " / " + PROVIDERS[r["provider"]]["name"] + "：" + ("标记为是" if value else "标记为否"))
        if readings:
            label_rows.append([LABELS[key], "；".join(readings)])
    label_html = table(["特征", "本次来源读数"], label_rows, "代理与滥用标签") if label_rows else ''
    scores = []
    semantics = {"fraud_score": ("IPQS 欺诈评分", "该次 IP 查询的评分"),
                 "abuse_confidence": ("AbuseIPDB 举报置信分", "举报形成的滥用置信度"),
                 "proxycheck_risk": ("ProxyCheck 风险分", "代理类型及活动历史；v3 评分，非欺诈概率"),
                 "ipquery_risk": ("IPQuery 风险分", "恶意活动风险指标；不使用其他厂商的阈值"),
                 "company_abuse_ratio": ("公司网段滥用比例", "整个网络，不能归因于此 IP"),
                 "asn_abuse_ratio": ("ASN 滥用比例", "整个 ASN，不能归因于此 IP"),
                 "scamalytics_score": ("Scamalytics 原始评分", "聚合情报模型的 IP 评分；与直接来源有重叠"),
                 "ip2location_fraud": ("IP2Location 欺诈分", "仅套餐实际返回时展示")}
    for r in valid:
        for s in r["facts"]["scores"]:
            name, meaning = semantics[s["name"]]
            scores.append([r["subject"], PROVIDERS[r["provider"]]["name"], name,
                           str(s["value"]) + " / " + str(s["scale"]), meaning])
        if r["facts"]["total_reports"] is not None:
            f = r["facts"]
            scores.append([r["subject"], PROVIDERS[r["provider"]]["name"], "举报记录",
                           str(f["total_reports"]) + " 条 / " + detail(f["distinct_reporters"]) + " 个独立举报者",
                           str(r["observation_window_days"]) + " 天窗口；最近举报：" + (f["last_reported_at"] or "未返回")])
        if "spam" in r["facts"]:
            s = r["facts"]["spam"]
            scores.append([r["subject"], "StopForumSpam", "垃圾信息库记录",
                           ("命中" if s["listed"] else "未命中") + "；频次 " + str(s["frequency"]),
                           "库内记录，未限定时间窗口；最近记录：" + (s["last_seen"] + "（源未提供时区）" if s["last_seen"] else "未返回")])
        if "activity" in r["facts"]:
            a = r["facts"]["activity"]
            counts = a["attack_counts"]
            scores.append([r["subject"], "ProxyCheck", "攻击活动明细",
                           "未提供（null，不能当作 0）" if counts is None else
                           "; ".join(k + ": " + str(v) for k, v in counts.items()) or "空记录对象",
                           "供应商默认观察范围随数据源变化，未声明统一天数"])
            scores.append([r["subject"], "ProxyCheck", "检测活动与置信度",
                           "检测置信度 " + detail(a["detection_confidence"]) + " / 100；观察次数 " + detail(a["times_seen"]),
                           "首次：" + detail(a["first_seen"]) + "；最近：" + detail(a["last_seen"]) + "；置信度不是风险分"])
    scores_html = table(["对象", "来源", "指标", "读数", "含义 / 窗口"], scores, "信誉与举报实测值") if scores else '<p class="empty"><b>IP 信誉检测未完成。</b> 本次没有取得欺诈分、网段滥用比例或举报记录。这个缺项属于检测工具，不是用户风险。</p>'

    # Pair actual IPs locally; no IPs are added to report.json or agent-summary.json.
    path_rows = []
    for cid, name in (("browser.egress", "浏览器 IPv4"), ("network.egress", "Agent IPv4"), ("network.ipv6", "Agent IPv6")):
        o = observations.get(cid)
        if o:
            path_rows.append([name, o["facts"].get("ip", "未取得"), state(o["status"]), o["at"], o["facts"].get("endpoint", "—")])
    for p in report["paths"]:
        if p["id"] == "path:browser-ipv6":
            path_rows.append(["浏览器 IPv6", addresses.get("browser-ipv6", "未取得"), state(p["status"]), p["at"], p["endpoint"]])
        elif p["id"] == "path:webrtc":
            path_rows.append(["浏览器 WebRTC", str(p["candidate_count"]) + " 个候选；" + ("采集完成" if p["complete"] else "采集未完成"), state(p["status"]), p["at"], p["endpoint"]])
        elif snapshot is None:
            path_rows.append(["浏览器 IPv4", "未载入私人快照", state(p["status"]), p["at"], p["endpoint"]])
    path_html = table(["测量对象", "出口 / 观测值", "状态", "测量时间", "诊断端点"], path_rows, "浏览器和 Agent 的网络路径") if path_rows else '<p class="empty">没有载入路径观测；请同时选择对应私人快照。</p>'
    context_rows = []
    o = observations.get("browser.context")
    if o and o["status"] == "ok":
        f = o["facts"]
        context_rows = [["时区", f["timezone"]], ["语言", f["language"]],
                        ["Cookie 能力", "可用" if f["cookies_enabled"] else "不可用"],
                        ["本地存储能力", "可用" if f["storage_available"] else "不可用"],
                        ["webdriver 自报", str(f["automated"]).lower()]]
    context_html = table(["浏览器属性", "本次观测"], context_rows, "浏览器基础能力") if context_rows else '<p>未载入浏览器背景观测。</p>'
    from .browser_details import rows, readings, compact_readings
    optional_rows = rows(report.get("browser_details"))
    details = (snapshot.get("browser") or {}).get("details") if snapshot else None
    details_html = ''
    if optional_rows:
        local_values = compact_readings(details)
        optional_rows = [[label, local_values.get(label, status), advice] for label, status, advice in optional_rows]
        details_html = '<section id="browser-details"><h2>可选浏览器检查</h2>' + table(["检查项", "结果", "建议"], optional_rows, "可选浏览器检查")
        details_html += '<p class="muted">这些是环境观察，不计入 IP 检查的通过或风险数量。未选择的项目不显示为失败。</p><details><summary>查看本地读数</summary>'
        details_html += (table(["检查项", "本次读数", "如何理解"], readings(details), "浏览器深入检查读数") if details else '<p>载入对应私人快照后查看实际属性。</p>') + '</details></section>'

    conclusions_html = table(["检查", "结论", "你该做什么"],
        [[r["label"], r["verdict"], r["action"]] for r in decision["conclusions"]], "本次检测结论")
    actions = ('<ol>' + ''.join('<li>' + e(a) + '</li>' for a in decision["user_actions"]) + '</ol>'
               if decision["user_actions"] else '<p>本次没有列出需要你执行的配置修改任务。</p>')
    gaps = '<ul>' + ''.join('<li>' + e(g) + '</li>' for g in decision["tool_gaps"]) + '</ul>'
    gaps += '<p>这些是工具需要补齐的测量，不计入用户风险，也不自动要求用户更换 IP、代理或浏览器。</p>'

    coverage_rows = [[r["subject"], PROVIDERS[r["provider"]]["name"], state(r["status"]),
                      r["product_tier"], r["queried_at"], r["source_updated_at"] or "未提供"] for r in records]
    coverage_html = table(["对象", "来源", "查询结果", "响应覆盖", "查询时间", "源数据更新时间"], coverage_rows, "数据源覆盖") if records else '<p>本次未启用情报查询。</p>'
    contacted = sorted({f["recipient"] for f in report["data_flows"] if f["sent"]})
    references = ''.join('<li><a rel="noreferrer noopener" href="' + e(PROVIDERS[p]["docs"]) + '">' + e(PROVIDERS[p]["name"]) + '</a></li>' for p in dict.fromkeys(r["provider"] for r in records))
    css = files("zhibi").joinpath("assets").joinpath("scan-report.css").read_text(encoding="utf-8")
    readings_html = '<div class="coverage">' + ''.join('<div><span>' + e(m["label"]) +
        '</span><strong>' + e(m["value"]) + '</strong><span>' + e(m["meaning"]) + '</span></div>'
        for m in decision["reputation_readings"]) + '</div>' if decision["reputation_readings"] else ''
    enhancement_rows = []
    for item in decision["optional_enhancements"]:
        status_text = "未选择（可选）" if not item["observations"] else "；".join(
            obs["subject"] + "：" + ("未配置 Key，未查询（可选）" if obs["status"] == "missing_key"
                                  else state(obs["status"])) for obs in item["observations"])
        enhancement_rows.append([item["name"], item["capability"], status_text, item["configure_command"]])
    enhancement_html = table(["可选来源", "额外提供", "本次状态", "单独配置"], enhancement_rows, "可选增强数据源")
    signup_links = ' · '.join('<a rel="noreferrer noopener" href="' + e(item["signup_url"]) + '">'
                              + e(item["name"]) + ' 免费注册</a>' for item in decision["optional_enhancements"])
    icons = {"measured": "✓", "attention": "!", "incomplete": "—"}
    checks_html = '<div class="results"><table aria-label="检测结果与建议"><colgroup><col class="check-col"><col class="result-col"><col></colgroup><thead><tr><th scope="col">检查项</th><th scope="col">结果</th><th scope="col">建议</th></tr></thead><tbody>' + ''.join(
        '<tr><th scope="row">' + e(item["label"]) + '</th><td><span class="result-badge" data-state="' + e(item["state"])
        + '"><span aria-hidden="true">' + icons[item["state"]] + '</span>' + e(item["result"])
        + '</span></td><td>' + e(item["advice"]) + '</td></tr>' for item in overview["table_rows"]) + '</tbody></table></div>'
    counts_html = ''.join('<span data-state="' + key + '"><b>' + str(overview["counts"][key]) + '</b> 项' + label + '</span>'
                          for key, label in (("measured", "已查通过"), ("attention", "待核对"), ("incomplete", "待补查")))
    next_action = overview["next_action"]
    next_html = ('<section class="next-action" aria-labelledby="next-title"><p class="section-kicker">接下来怎么做</p>'
                 '<h2 id="next-title">' + e(next_action["title"]) + '</h2><p>' + e(next_action["detail"]) + '</p>'
                 '<p class="verify"><b>完成依据：</b>' + e(next_action["verify"]) + '</p>'
                 '<p class="muted">这是基于检测的下一步建议；本次检测未修改环境设置。具备 computer use 能力的 Agent 可继续核对并执行已授权操作。</p></section>')
    confirmation = report.get("ipv6_confirmation")
    policy_evidence = ('<p>配置核对时间：' + e(confirmation["confirmed_at"]) + '；核对方式：'
                       + ('设置界面人工核对' if confirmation["method"] == "settings_ui" else '本地生效配置人工核对')
                       + '。证据与本次报告绑定；这是已记录的配置核对，不是自动防火墙审计。</p>') if confirmation else '<p>尚未记录同一专用环境的禁用配置证据；请求失败或超时不能代替确认。</p>'
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<meta name="referrer" content="no-referrer"><title>知彼 · {e(subject)}环境检查</title><style>{css}</style></head>
<body><main><header><a class="brand" href="#">知彼<span>ZHIBI</span></a><span class="edition">{'合成示例 · 非真实测量' if report['sample'] else '环境检查 · 本地报告'}</span></header>
<div class="report-meta"><p>{e(subject)} · <strong>{e(headline)}</strong></p><p>检测于 {e(when)}</p></div>
<div class="journey" aria-label="主流程"><span>01 选择环境</span><span class="current">02 主动检查</span><span>03 协助配置</span><span>04 复查交付</span></div>
<section class="verdict" data-status="{e(overview['status'])}" aria-labelledby="status-title">
<p class="section-kicker">本次结论</p><h1 id="status-title">{e(overview['headline'])}</h1>
<div class="result-counts" aria-label="检查数量">{counts_html}</div></section>
{next_html}
{checks_html}
<p class="scope">{e(overview['scope'])}</p>
<!-- ZHIBI_OPTIONAL_RESULTS -->
<details id="evidence"><summary>查看检测依据与技术详情</summary>
<p class="muted">以下保留各项读数，供复核使用。页面更新不代表重新测量。</p>
<section><h2>逐项判断</h2><p>{e(decision['headline'])}</p>{conclusions_html}{actions}</section>
<section id="identity"><h2>网络归属</h2>{identity_html}<p class="muted">ASN 和组织属于网络归属信息；不能单凭运营商名称认定住宅 IP、独享 IP 或没有代理。</p></section>
<section id="paths"><h2>网络路径</h2>{path_html}</section>
<section id="ipv6-policy"><h2>IPv6：默认关闭专用环境的出站</h2>
<ol><li>确认当前浏览器属于哪个专用环境，以及它使用的代理客户端或出口规则。</li>
<li>在该专用环境关闭 IPv6 出站，或在它的出口防火墙阻断 IPv6；仅“优先 IPv4”、隐藏 IPv6 DNS 记录或禁用 WebRTC 不等于完成此项。</li>
<li>保存并重启该环境，核对生效配置，再用同一环境复测；保留设置截图或配置文件作为本地证据。</li></ol>
<p>不要默认关闭整台日常电脑的 IPv6。若软件无法单独限制此环境，应先确定可隔离的出口方案。确需 IPv6 时，应验证其路由后采用单独方案；本默认方案不会将“已连通”判作“已关闭”。</p>{policy_evidence}</section>
<section id="reputation"><h2>信誉读数与记录</h2>{readings_html}{label_html}{scores_html}<p class="muted">分数来自各家服务，越低表示该服务评估的风险越低；0 分不代表绝对安全。代理标签未命中也不代表实际没有使用代理。原始分数、网络比例和举报数各有含义，不转换成 账号处置概率；未查询或缺失的结果不会填成 0。</p></section>
<section><h2>浏览器背景</h2>{context_html}<p class="muted">时区、语言以及 webdriver 自报值不被直接解释为欺诈或账号结果。</p></section>
{details_html}
<section><h2>来源覆盖与测量范围</h2>{gaps}
<div class="coverage"><div><span>网络归属</span><strong>{'已取得' if identity else '未取得'}</strong></div><div><span>代理相关标签</span><strong>{flag_count} / 4 项有读数</strong></div><div><span>IP 信誉分</span><strong>{score_count} 个指标有读数</strong></div></div>{coverage_html}<p>本次尝试联系：{e('、'.join(contacted) or '无')}。</p><ul>{references}</ul>
<p>主表仅覆盖本次基础检查。额外 DNS、TLS、浏览器属性与研究模型在显式选择后单独展示，不能替代基础结论。平台内部账号/设备关联仍不可见；本地证据关系记录只用于追溯依据。</p></section></details>
<details id="optional"><summary>可选增强：需要更多数据时自行配置</summary>
<p>默认检测无需注册这三家，也无需 API Key。不配置不影响已有检测结果；未选择不算检测失败。只有想取得下面的额外数据时才需要配置，可任选一家。</p>
{enhancement_html}<p>{signup_links}</p>
<ol><li>到所选服务官网注册、完成验证，并从账户控制台取得自己的 API Key。</li>
<li>在你自己的终端进入安装的 Skill 目录，运行 <code>python3 scripts/zhibi.py configure ipqs</code>；其他来源将 <code>ipqs</code> 替换成 <code>abuseipdb</code> 或 <code>ipapi</code>。隐藏输入，保存在本机，不要把 Key 发到聊天。</li>
<li>告诉 Agent 你想使用哪家可选来源，并重新检测同一个实际使用环境。仅保存 Key 不会自动启用查询。</li></ol>
<p>各家提供免费额度，具体限额与可用字段以其当前套餐为准。查询会向所选供应商发送待查 IP 和其自己的 Key；不发送 账号 Cookie。可选来源的失败保留在来源覆盖中，不抹掉其他已取得的结果。</p></details>
<footer>报告保存在本机 · 分享前请检查其中的 IP 与个人环境信息</footer>
</main></body></html>'''
