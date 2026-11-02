"""Plain-language presentation of validated evidence; no new risk score."""


def status_view(report, decision):
    records = [r for r in report["intelligence"] if r["facts"]]
    rows = decision["conclusions"]
    reviews = [r for r in rows if r["kind"] == "review"]
    connected = bool(report["subjects"])
    flags = [(k, v) for r in records for k, v in r["facts"]["flags"].items()
             if k in {"proxy", "vpn", "tor", "hosting", "recent_abuse"} and v is not None]
    scores = [s for r in records for s in r["facts"]["scores"]
              if s["name"] in {"fraud_score", "abuse_confidence", "proxycheck_risk", "ipquery_risk", "scamalytics_score", "ip2location_fraud"}]
    unclassified_score = any(s["name"] in {"ipquery_risk", "scamalytics_score", "ip2location_fraud"} and s["value"] > 0 for s in scores)
    conflict = any(":conflict:" in f["id"] for f in report["findings"])
    risk_review = [r for r in reviews if not r["id"].startswith("path:") and r["id"] != "webrtc"]
    target = "浏览器" if report["target"] == "browser" else "运行检测的环境"
    checks = [{"label": "网络连接", "value": "已连通" if connected else "未测成",
               "detail": target + "已成功访问检测服务。" if connected else "还没有取得这次检测的有效网络结果。",
               "state": "measured" if connected else "incomplete"}]

    if conflict:
        names = list(dict.fromkeys(r["label"] for r in risk_review))
        detail = "不同服务的判断不一致。" + ("需核实：" + "、".join(names) + "。" if names else "需要核实后再作判断。")
        value, state = "结果有分歧", "attention"
    elif risk_review:
        names = list(dict.fromkeys(r["label"] for r in risk_review))
        value, detail, state = "有需要核实的提示", "涉及：" + "、".join(names) + "。", "attention"
    elif unclassified_score:
        value, detail, state = "有非零风险评分", "这项评分缺少明确的分级标准，不能直接判断高低。", "attention"
    elif flags or scores:
        value, detail, state = "已查项未见风险提示", "查询到的标签和评分未提示需要处理的问题。", "measured"
    else:
        value, detail, state = "尚未查到", "本次没有取得可用的标签或风险评分。", "incomplete"
    checks.append({"label": "IP 信誉", "value": value, "detail": detail, "state": state})

    history, history_positive = [], False
    for r in records:
        f = r["facts"]
        if f["total_reports"] is not None:
            n = f["total_reports"]
            history.append(str(r["observation_window_days"]) + " 天内" + ("有滥用举报。" if n else "未查到滥用举报。"))
            history_positive |= bool(n)
        if "spam" in f:
            history.append("垃圾信息库" + ("有历史记录。" if f["spam"]["listed"] else "未发现记录。"))
            history_positive |= f["spam"]["listed"]
        activity = f.get("activity", {}).get("attack_counts")
        if activity is not None and sum(activity.values()) > 0:
            history.append("查到了历史攻击活动记录。")
            history_positive = True
    checks.append({"label": "历史记录", "value": "发现历史记录" if history_positive else
                   "本次未发现记录" if history else "尚无可用结果",
                   "detail": "".join(dict.fromkeys(history)) if history else "本次没有取得可用的历史记录。",
                   "state": "attention" if history_positive else "measured" if history else "incomplete"})

    if decision["status"] == "incomplete":
        headline = "还不能判断当前环境" if not connected else "网络已连通，IP 信誉还未查到"
        next_step = "重新运行实际使用环境的检测，再查看结果。" if not connected else "重新运行 IP 信誉检测；暂时不用因此修改网络配置。"
    elif decision["status"] == "attention":
        headline = "发现需要核实的问题"
        next_step = "先核实下面的提示，再决定是否调整网络。"
        if any(r["id"] == "webrtc" for r in reviews):
            next_step = "浏览器的不同连接使用了不同 IP，请先核对是否符合你的网络设置预期。"
        elif any(r["id"].startswith("path:") for r in reviews):
            next_step = "实际连接与你预期的网络设置不一致，请先核对路由设置。"
        elif decision["user_actions"]:
            next_step = decision["user_actions"][0]
        elif conflict:
            next_step = "先核对下面有分歧的判断及风险提示，再决定是否调整网络。"
    elif unclassified_score:
        headline = "查到风险读数，还需结合记录判断"
        next_step = "先查看该评分对应的标签和记录，单凭这个读数不能决定是否更换 IP。"
    else:
        headline = "已查项目未发现需要处理的问题"
        next_step = "暂时不需要更换 IP，也不需要修改浏览器配置。"
    table_rows = []
    result_names = {"measured": "通过", "attention": "需注意", "incomplete": "未完成"}

    def add(label, state, advice):
        table_rows.append({"label": label, "state": state, "result": result_names[state], "advice": advice})

    add("网络连接", checks[0]["state"], "已连通检测服务，无需调整。" if connected else "重新检测当前使用的网络。")
    ip_check, history_check = checks[1:]
    add("IP 信誉", ip_check["state"],
        "已查标签和评分未提示风险，无需调整。" if ip_check["state"] == "measured" else
        ip_check["detail"] + "请核对检测依据。" if ip_check["state"] == "attention" else "重新查询；缺少数据不作为换 IP 的依据。")
    add("历史记录", history_check["state"], history_check["detail"] +
        ("核对记录时间及是否误报。" if history_positive else "无需处理。" if history else "可重试查询。"))
    from .ipv6_policy import policy_row
    ipv6 = policy_row(report)
    table_rows.append(ipv6)
    for path in report["paths"]:
        if path["id"] == "path:webrtc" and path["status"] != "skipped":
            relation = path["https_relation"]
            add("浏览器直连检查", "measured" if relation == "same_observed" else "attention" if relation == "different" else "incomplete",
                "已测到的连接出口一致，无需调整。" if relation == "same_observed" else
                "发现不同出口，请核对浏览器的网络设置。" if relation == "different" else "查看专用浏览器的 WebRTC/UDP 策略；若已禁用，保留设置并记录配置依据。本次无可比出口。")
    for item in reviews:
        if item["id"].startswith("path:"):
            add("网络路由", "attention", "连接出口与预期不一致，请核对路由设置。")
            break
    status = "attention" if unclassified_score and decision["status"] == "measured" else decision["status"]
    if ipv6["state"] == "attention" and status == "measured":
        status = "attention"
        headline = "已查 IP 项目未见风险提示，IPv6 设置待确认"
        next_step = "先完成专用环境的 IPv6 出站设置，再按下表核对。"
    # Derive the next operation from evidence, not from the size of the tool catalog.
    # These are proposed actions. The scan never claims to have operated a setting.
    primary_attention = any(r["state"] == "attention" for r in table_rows if r["label"] != "IPv6 出站策略")
    incomplete = [r for r in table_rows if r["state"] == "incomplete"]
    if not connected:
        next_action = {"id": "collect_browser" if report["target"] == "browser" else "collect_exit",
                       "title": "Agent 重新检查实际使用环境的连接",
                       "detail": "打开本次探针，核对连接状态并重新测量；暂不调整 IP 或浏览器画像。",
                       "verify": "同一环境取得新的有效出口后，再查询 IP 信息。"}
    elif primary_attention:
        next_action = {"id": "review_finding", "title": "Agent 先核对具体提示的依据",
                       "detail": next_step,
                       "verify": "核对对应设置或数据来源；有依据且已授权的修改完成后，在同一环境复查。"}
    elif incomplete and any(r["label"] in {"IP 信誉", "历史记录"} for r in incomplete):
        next_action = {"id": "retry_intelligence", "title": "Agent 补查尚无结果的免费来源",
                       "detail": "保留成功结果，针对失败项重试；不要求先注册额外服务。",
                       "verify": "取得有效响应；仍失败时明确保留缺项，不把缺失当作 0 分。"}
    elif ipv6["state"] != "measured":
        next_action = {"id": "inspect_ipv6", "title": "Agent 核对专用环境的 IPv6 设置",
                       "detail": "打开该环境的代理或出口设置，检查是否已有禁用配置。需要修改时先说明作用范围，再按授权处理。",
                       "verify": "生效配置与同一环境的新测量相互印证。没有独立控制项时，明确交代需要谁处理哪一项。"}
    elif incomplete:
        next_action = {"id": "inspect_webrtc", "title": "Agent 核对浏览器的 WebRTC 设置",
                       "detail": "检查专用浏览器是否限制 WebRTC/UDP；无候选只是未取得可比结果，不要求关闭现有保护。",
                       "verify": "保留实际配置依据；需要测量时重新检查同一浏览器的连接路径。"}
    else:
        next_action = {"id": "retain", "title": "保留当前配置",
                       "detail": "本次已查项目没有需要处理的问题。协助模式可继续你提供的下一步准备流程。",
                       "verify": "配置或网络改变后再检查；本次结果不代表注册资格或账号结果。"}
    if not primary_attention and connected and not incomplete and ipv6["state"] == "measured":
        headline = "本次已查项目无需调整"
    elif not primary_attention and connected and ipv6["state"] != "measured" and not any(
            r["label"] in {"IP 信誉", "历史记录"} for r in incomplete):
        headline = "IP 已查项未见需处理的问题，下一步核对环境设置"
    next_step = next_action["detail"]
    counts = {key: sum(r["state"] == key for r in table_rows) for key in result_names}
    return {"status": status,
            "headline": headline, "next_step": next_step, "checks": checks,
            "table_rows": table_rows, "counts": counts,
            "next_action": next_action,
            "pending_count": len(decision["tool_gaps"]),
            "scope": "“通过”仅指本次已查项目未发现需处理的问题，不代表 账号状态。"}
