"""Decision-first interpretation shared by the human report and Agent.

Inputs are validated scan records. Output is fixed wording plus scoped counts,
provider names and scores, never IPs, provider free text or browser attributes.
"""
from .intelligence import PROVIDERS, KEY_SIGNUP, OPTIONAL_CAPABILITIES


def assess_scan(report):
    target = "浏览器" if report["target"] == "browser" else "Agent"
    subjects = {s["id"] for s in report["subjects"]}
    records = [r for r in report["intelligence"] if r["facts"] and r["subject"] in subjects]
    paths = report["paths"]
    primary = report["target"] + "-ipv4"
    measured = primary in subjects
    labels = {"vpn": "VPN", "proxy": "代理", "tor": "Tor", "hosting": "托管网络", "recent_abuse": "近期滥用"}
    flags = [(r, key, r["facts"]["flags"][key]) for r in records for key in labels
             if r["facts"]["flags"][key] is not None]
    scores = [(r, s) for r in records for s in r["facts"]["scores"]]
    reports = [r for r in records if r["facts"]["total_reports"] is not None]
    spam_records = [r for r in records if "spam" in r["facts"]]
    activity_records = [r for r in records if "activity" in r["facts"]]
    reputation = bool(flags or scores or reports or spam_records)
    conflicts = [f for f in report["findings"] if ":conflict:" in f["id"]]
    rows, actions, gaps = [], [], []

    def row(code, label, verdict, action, kind, refs):
        rows.append({"id": code, "label": label, "verdict": verdict, "action": action,
                     "kind": kind, "evidence_refs": refs})

    if measured:
        row("ipv4", "网络访问", target + " IPv4 诊断请求成功，出口已确认。", "保留当前 IPv4 配置。", "result", [primary])
    elif subjects:
        row("egress", "网络访问", target + " IPv6 已测得，IPv4 没有可用观测。",
            "仅能按 IPv6 结果判断；不要把它当成 IPv4 结果。", "result", sorted(subjects))
    else:
        row("egress", "网络访问", "没有取得可用于查询的" + target + "出口。",
            "重新采集实际使用环境的出口；本次不评价 IP 信誉。", "gap", [])
        gaps.append("目标出口：缺少有效观测，可能未测、失败、过期或属于自动化样本。")

    for sid in sorted(subjects):
        known = [r for r in records if r["subject"] == sid and r["facts"]["asn"] is not None]
        asns = {r["facts"]["asn"] for r in known}
        if len(asns) == 1:
            row(sid + ":identity", "网络归属", "IPv" + sid[-1] + "：" + str(len(known)) + " 个来源返回 ASN"
                + ("，结果一致。" if len(known) > 1 else "。"),
                "归属可查；不据此认定住宅或独享 IP。", "result",
                [r["subject"] + ":" + r["provider"] for r in known])

    for path in paths:
        if path["id"] == "path:webrtc":
            if path["status"] == "skipped":
                continue
            if path["https_relation"] == "different":
                row("webrtc", "WebRTC 路径", "WebRTC 和 HTTPS 使用不同出口。",
                    "检查浏览器 WebRTC 与 HTTPS 的路由配置，确认是否符合预期。", "review", [path["id"]])
                actions.append("检查 WebRTC 与 HTTPS 出口差异；这次已测到差异，需核对路由预期。")
            elif path["https_relation"] == "same_observed":
                row("webrtc", "WebRTC 路径", "本次可比的 WebRTC 与 HTTPS 出口一致。",
                    "本项无需调整。", "result", [path["id"]])
            else:
                gaps.append("WebRTC 路径：" + ("采集超时，" if path["status"] == "timeout" else "")
                            + str(path["candidate_count"]) + " 个候选，未形成可比结论。")
        elif path["matches_agent"] is False:
            intent = path["route_intent"]
            action = ("修正与共用出口预期不符的路由，再复测。" if intent == "same" else
                      "保留既定分流。" if intent == "different" else "不要求统一出口；后续以实际使用的浏览器为检测对象。")
            row(path["id"], "出口对比 IPv" + path["id"][-1],
                "浏览器与 Agent 出口不同，检测结果不能互相代替。", action,
                "review" if intent == "same" else "result", [path["id"]])
            if intent == "same":
                actions.append("路由结果与你声明的共用出口预期不符；核对两侧路由后复测。")
        elif path["matches_agent"] is True:
            row(path["id"], "出口对比 IPv" + path["id"][-1], "浏览器与 Agent 本次出口一致。",
                "本项无需调整。", "result", [path["id"]])
        elif path["status"] not in ("ok", "skipped"):
            if not (path["id"] == "path:browser-ipv6" and report.get("ipv6_confirmation")):
                gaps.append("浏览器 IPv" + path["id"][-1] + "：测量未成功；不能据此判定泄漏或已关闭。")

    if not reputation:
        row("reputation", "IP 信誉", "检测未完成：没有代理标签、欺诈评分或滥用记录。",
            "本项不能出具好坏判断；缺项不作为换 IP 的依据。", "gap", [])
        gaps.append("IP 信誉：选定来源未返回代理标签、欺诈评分或滥用记录。")
    else:
        # Resolve flags per subject so IPv4/IPv6 differences are not called source conflicts.
        for sid in sorted(subjects):
            for key, label in labels.items():
                matches = [(r, value) for r, field, value in flags if field == key and r["subject"] == sid]
                if not matches:
                    continue
                values = {value for _, value in matches}
                family = "IPv" + sid[-1]
                if len(values) > 1:
                    verdict = family + " " + label + "：来源结论冲突，不能定性。"
                    action, kind = "先核实来源差异，不用多数票选结论。", "review"
                elif True in values:
                    names = "、".join(PROVIDERS[r["provider"]]["name"] for r, _ in matches)
                    verdict = family + "：" + names + " 将其标记为" + label + "。"
                    action, kind = "核对该标签是否符合实际网络用途；存在误标时向数据源更正。", "review"
                else:
                    verdict = family + "：本次返回的 " + label + " 标签均为否。"
                    action, kind = "保留本次结果，本项不提出配置修改。", "result"
                row(sid + ":" + key, label, verdict, action, kind,
                    [r["subject"] + ":" + r["provider"] for r, _ in matches])
        meanings = {"fraud_score": "IPQS 欺诈评分", "abuse_confidence": "AbuseIPDB 举报置信分",
                    "company_abuse_ratio": "公司网段滥用比例", "asn_abuse_ratio": "ASN 滥用比例",
                    "proxycheck_risk": "ProxyCheck 风险分", "ipquery_risk": "IPQuery 风险分", "scamalytics_score": "Scamalytics 评分", "ip2location_fraud": "IP2Location 欺诈分"}
        for r, score in scores:
            verdict = "IPv" + r["subject"][-1] + "：" + str(score["value"]) + " / " + str(score["scale"])
            action, kind = "该值描述整个网络，不据此归因于当前 IP。", "result"
            if score["name"] == "fraud_score":
                # IPQS response-parameters, fraud_score definition; checked 2026-10-19.
                if score["value"] >= 90:
                    verdict += "，达到 IPQS 的高风险阈值。"
                    action, kind = "向网络运营方核实 IP 信誉和近期滥用记录；这是 IPQS 评级，不是 上游判定。", "review"
                elif score["value"] >= 75:
                    verdict += "，达到 IPQS 的可疑阈值。"
                    action, kind = "核对代理标签与滥用记录；该分数不等于当前用户存在欺诈。", "review"
                else:
                    verdict += "，低于 IPQS 的 75 分可疑阈值。"
                    action = "该来源评分未达到可疑阈值；继续按其他实测项判断。"
            elif score["name"] == "abuse_confidence":
                verdict += "，" + ("该来源报告了滥用置信分。" if score["value"] > 0 else "该来源当前评分为零。")
                action = "结合该来源的举报数量和窗口核实；不与欺诈评分混用。"
                kind = "review" if score["value"] > 0 else "result"
            elif score["name"] == "proxycheck_risk":
                verdict += "，由代理类型和活动历史共同形成。"
                kind = "review" if score["value"] > 25 else "result"
                action = ("该值超出 ProxyCheck v3 最低分段，核对下面的标签和活动记录。" if kind == "review" else
                          "位于 ProxyCheck v3 的 0–25 分段；结合代理标签判断，不换算为欺诈概率。")
            elif score["name"] == "ipquery_risk":
                verdict += "，该来源的恶意活动风险指标。"
                action = "供应商未在当前文档给出分段阈值；保留原值，不套用 IPQS 阈值。"
            elif score["name"] in ("scamalytics_score", "ip2location_fraud"):
                action = "保留该供应商原始分数，不套用其他供应商的阈值。"
            else:
                verdict += "，描述整个网络的滥用比例。"
            row(r["subject"] + ":" + score["name"], meanings[score["name"]],
                verdict, action, kind, [r["subject"] + ":" + r["provider"]])
        for r in reports:
            facts = r["facts"]
            count = facts["total_reports"]
            row(r["subject"] + ":reports", "滥用举报", "IPv" + r["subject"][-1] + "：该来源 "
                + str(r["observation_window_days"]) + " 天窗口内有 " + str(count) + " 条举报。",
                "由网络运营方核实历史举报；不归因于当前使用者。" if count else "本次来源窗口内无举报，本项不提出修改。",
                "review" if count else "result", [r["subject"] + ":" + r["provider"]])
        for r in spam_records:
            spam = r["facts"]["spam"]
            row(r["subject"] + ":spam", "垃圾信息举报", "IPv" + r["subject"][-1] + "：StopForumSpam " +
                ("命中，返回频次 " + str(spam["frequency"]) + "。" if spam["listed"] else "未命中，返回频次 0。"),
                "核对历史使用者和记录时间，误报可向该来源申请更正。" if spam["listed"] else
                "本库未发现垃圾信息记录；不代表其他类型的滥用库也无记录。",
                "review" if spam["listed"] else "result", [r["subject"] + ":" + r["provider"]])
        for r in activity_records:
            activity = r["facts"]["activity"]
            counts = activity["attack_counts"]
            total = sum(counts.values()) if counts is not None else None
            row(r["subject"] + ":attacks", "攻击活动记录", "IPv" + r["subject"][-1] + "：ProxyCheck " +
                ("返回活动计数合计 " + str(total) + "。" if total is not None else "未提供攻击活动明细（null）。"),
                "核对活动类别和观测范围；不等同于独立举报人数。" if total is not None else
                "没有可报告的活动计数；不把 null 填成零。",
                "review" if total else "gap" if total is None else "result", [r["subject"] + ":" + r["provider"]])
        for sid in sorted(subjects):
            present = {key for r, key, _ in flags if r["subject"] == sid}
            missing = [labels[key] for key in ("vpn", "proxy", "tor", "hosting") if key not in present]
            if missing:
                gaps.append("IPv" + sid[-1] + " 标签缺项：" + "、".join(missing) + "。")
            names = {s["name"] for r, s in scores if r["subject"] == sid}
            if not names.intersection({"fraud_score", "abuse_confidence", "proxycheck_risk", "ipquery_risk", "scamalytics_score", "ip2location_fraud"}):
                gaps.append("IPv" + sid[-1] + "：没有 IP 信誉评分。")
            if any(r["subject"] == sid and r["provider"] == "abuseipdb"
                   and r["facts"]["total_reports"] is None for r in records):
                gaps.append("IPv" + sid[-1] + "：本次 AbuseIPDB 响应缺少举报计数；不能当作零举报。")

    for conflict in conflicts:
        field = conflict["id"].rsplit(":", 1)[-1]
        if field in ("asn", "country_code"):
            row(conflict["id"], "网络归属", ("ASN" if field == "asn" else "国家归属") + "存在来源冲突。",
                "保留各来源读数；不能给出唯一归属结论。", "review", conflict["evidence_refs"])

    basics = {f["rule_id"]: f["assessment"] for f in report["baseline"]["findings"]}
    if basics.get("browser.context") == "needs_confirmation":
        actions.append("浏览器探针的基础能力未获确认；在实际站点核实 Cookie 与存储权限，确认受限后再改设置。")
    if basics.get("client.installed") == "needs_action":
        actions.append("当前 PATH 找不到所需的 目标客户端；安装或修复 PATH 后复测。")
    has_review = any(r["kind"] == "review" for r in rows)
    if not subjects:
        headline, status = "没有取得有效出口，本次检测未完成", "incomplete"
    elif actions:
        headline, status = "发现需要核对的具体配置问题", "attention"
    elif conflicts:
        headline, status = "IP 情报存在来源冲突，不能给出单一判断", "attention"
    elif has_review:
        headline, status = "查到需要核实的 IP 标签、评分或历史记录", "attention"
    elif not reputation:
        headline, status = target + (" IPv4 出口已确认；IP 信誉检测未完成" if measured else "出口已测得；IP 信誉检测未完成"), "incomplete"
    else:
        all_core = all(any(r["subject"] == sid and r["facts"]["flags"][key] is not None for r in records)
                       for sid in subjects for key in ("vpn", "proxy", "tor", "hosting"))
        if all_core and not any(value for _, _, value in flags):
            headline = "已查到 IP 信誉：未命中代理标签"
            if spam_records and all(not r["facts"]["spam"]["listed"] for r in spam_records):
                headline += "，垃圾信息库未命中"
        else:
            headline = "IP 信誉已有实测结果，已列出标签、评分与记录"
        status = "measured"
    if actions:
        recommendation = actions[0]
    elif not subjects:
        recommendation = "先重新取得实际使用环境的出口，再进行 IP 查询。"
    elif has_review:
        recommendation = "先核实下列标签、评分、举报或来源冲突，再决定是否调整网络。"
    else:
        recommendation = "已查 IP 数据不要求更换 IP；IPv6 出站按专用环境策略核对。" + ("IP 信誉还需补测。" if not reputation else "")
    readings = [{"label": PROVIDERS[r["provider"]]["name"] + " · IPv" + r["subject"][-1],
                 "value": str(s["value"]) + " / " + str(s["scale"]),
                 "meaning": {"fraud_score": "IP 欺诈评分", "abuse_confidence": "举报置信分",
                             "proxycheck_risk": "代理与活动风险分", "ipquery_risk": "恶意活动风险分",
                             "scamalytics_score": "Scamalytics 欺诈分", "ip2location_fraud": "IP2Location 欺诈分"}[s["name"]]
                            + "；越低风险越低" + ("；服务返回 0，非缺失补零" if s["value"] == 0 else "")}
                for r, s in scores if s["name"] in {"fraud_score", "abuse_confidence", "proxycheck_risk", "ipquery_risk", "scamalytics_score", "ip2location_fraud"}]
    readings += [{"label": "StopForumSpam · IPv" + r["subject"][-1],
                  "value": ("命中" if r["facts"]["spam"]["listed"] else "未命中") + " · " + str(r["facts"]["spam"]["frequency"]),
                  "meaning": "垃圾信息库命中 / 频次"} for r in spam_records]
    enhancements = [{"provider": name, "name": PROVIDERS[name]["name"], "capability": capability,
                     "signup_url": KEY_SIGNUP[name], "configure_command": "configure " + name,
                     "observations": [{"subject": r["subject"], "status": r["status"],
                                       "product_tier": r["product_tier"]}
                                      for r in report["intelligence"] if r["provider"] == name]}
                    for name, capability in OPTIONAL_CAPABILITIES.items()]
    decision = {"format": "zhibi-assessment-1", "status": status, "headline": headline,
            "recommendation": recommendation, "conclusions": rows, "user_actions": actions,
            "reputation_readings": readings,
            "optional_enhancements": enhancements,
            "tool_gaps": list(dict.fromkeys(gaps)), "measured_at": report["generated_at"],
            "scope": "诊断端点、网络情报与本次观测；未检测 账号资格或账号处置结果。"}
    from .status_view import status_view
    decision["overview"] = status_view(report, decision)
    return decision
