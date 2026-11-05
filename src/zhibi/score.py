"""网络环境评分。只对实测项计分；未测项不计入，也不当成通过。"""
from .models import InputError

LEVELS = ((80, "low"), (60, "medium"), (0, "high"))
LABELS = {"low": "已测项基本符合配置目标", "medium": "部分配置需要核对", "high": "存在配置问题"}

# 维度权重。总和 100；未测维度不参与加权，覆盖率单独报告。
WEIGHTS = {
    "egress": 25,
    "consistency": 25,
    "leakage": 25,
    "reputation": 15,
    "stability": 10,
}

DATACENTER_HINTS = (
    "amazon", "aws", "google", "microsoft", "azure", "digitalocean", "linode",
    "vultr", "hetzner", "ovh", "contabo", "oracle", "alibaba", "tencent",
    "hosting", "server", "cloud", "vps", "datacenter", "data center", "colo",
    "bandwagon", "dmit", "racknerd", "hostwinds", "cloudflare",
)
RESIDENTIAL_HINTS = ("telecom", "unicom", "mobile", "broadband", "fiber", "cable", "isp", "communications")


def looks_datacenter(org):
    """从组织名做保守判断。判断不了就返回 None，不猜。"""
    if not isinstance(org, str) or not org.strip():
        return None
    text = org.lower()
    if any(h in text for h in RESIDENTIAL_HINTS):
        return False
    if any(h in text for h in DATACENTER_HINTS):
        return True
    return None


def _dim(identifier, label, weight, score, state, reasons, fix=None):
    return {"id": identifier, "label": label, "weight": weight, "score": int(score),
            "state": state, "reasons": [r for r in reasons if r], "fix": fix}


def egress_dimension(egress):
    egress = egress or {}
    org = egress.get("org")
    datacenter = egress.get("datacenter")
    if datacenter is None:
        datacenter = looks_datacenter(org)
    label = "数据中心" if datacenter is True else "运营商" if datacenter is False else "未知类型"
    return _dim("egress", "出口归属（背景）", WEIGHTS["egress"], 0, "not_measured",
                ["组织信息：%s；名称推测为%s。归属标签不证明路径可用或账号风险。" % (org or "未取得", label)],
                None)


def consistency_dimension(facts, expect_tz=None, expect_locale=None):
    reasons, score, measured = [], 100, 0
    tz = (facts or {}).get("tz")
    if expect_tz:
        measured += 1
        if tz in (None, "", "unknown"):
            measured -= 1
        elif tz != expect_tz:
            score -= 40
            reasons.append("机器认为自己在 %s，但预期是 %s。" % (tz, expect_tz))
        else:
            reasons.append("时间与所在地区一致。")
    locale = (facts or {}).get("lc_all")
    if locale in (None, "unset"):
        locale = (facts or {}).get("lang")
    if expect_locale:
        measured += 1
        if locale in (None, "", "unset", "unknown"):
            measured -= 1
        elif locale != expect_locale:
            score -= 30
            reasons.append("系统语言是 %s，预期 %s。" % (locale, expect_locale))
        else:
            reasons.append("系统语言与地区一致。")
    ntp = (facts or {}).get("ntp") if isinstance(facts, dict) and "ntp" in (facts or {}) else None
    if ntp in ("yes", "no"):
        measured += 1
        if ntp != "yes":
            score -= 25
            reasons.append("系统时钟没有确认同步。")
        else:
            reasons.append("系统时钟已同步。")
    if measured == 0:
        return _dim("consistency", "内部一致性", WEIGHTS["consistency"], 0, "not_measured",
                    ["没有可对比的一致性项。"], None)
    state = "ok" if score >= 80 else ("warn" if score >= 50 else "fail")
    fix = None if state == "ok" else "把时间、语言、时钟三者对齐到这条线路所在地区。"
    return _dim("consistency", "内部一致性", WEIGHTS["consistency"], max(0, score), state, reasons, fix)


def leakage_dimension(dns=None, webrtc=None):
    # Resolver addresses describe configuration, not the actual DNS route.
    leak = (webrtc or {}).get("leak")
    if type(leak) is not bool:
        return _dim("leakage", "WebRTC 路径比较", WEIGHTS["leakage"], 0, "not_measured",
                    ["没有可比较的 WebRTC 与 HTTPS 出口；DNS 配置地址不能证明解析路径。"], None)
    return _dim("leakage", "WebRTC 路径比较", WEIGHTS["leakage"], 0 if leak else 100,
                "fail" if leak else "ok",
                ["本次 WebRTC 与同地址族 HTTPS 出口不同。" if leak else
                 "本次可比较的 WebRTC 与 HTTPS 出口一致；未覆盖全部 DNS 或网络流量。"],
                "核对浏览器和代理的实际路由，再复测。" if leak else None)


def reputation_dimension(reputation):
    value = (reputation or {}).get("score")
    if value is None:
        return _dim("reputation", "信誉读数", WEIGHTS["reputation"], 0, "not_measured",
                    ["没有查询信誉来源，或来源没有返回分数。"],
                    "这是可选的；不查不影响其它项，但这一项会记成未测。")
    try:
        value = max(0, min(100, float(value)))
    except (TypeError, ValueError):
        raise InputError("信誉分数必须是数字。") from None
    state = "ok" if value >= 80 else ("warn" if value >= 60 else "fail")
    reasons = ["来源给出的综合分是 %d（越高越好）。" % value]
    if (reputation or {}).get("sources"):
        reasons.append("来源：%s。" % "、".join(reputation["sources"]))
    return _dim("reputation", "信誉读数", WEIGHTS["reputation"], value, state, reasons,
                None if state == "ok" else "换一条线路通常比调配置更有效。")


def stability_dimension(service=None, facts=None):
    reasons, score, measured = [], 100, 0
    active = (service or {}).get("active")
    if active is not None:
        measured += 1
        if not active:
            score -= 60
            reasons.append("要长期跑的程序现在没有在运行。")
        else:
            reasons.append("程序正在运行。")
    enabled = (service or {}).get("enabled")
    if enabled is not None:
        measured += 1
        if not enabled:
            score -= 20
            reasons.append("重启之后不会自动起来。")
        else:
            reasons.append("关机重启后会自动起来。")
    if measured == 0:
        return _dim("stability", "稳定性", WEIGHTS["stability"], 0, "not_measured",
                    ["没有部署服务，也没有读到常驻机制。"], None)
    state = "ok" if score >= 80 else ("warn" if score >= 50 else "fail")
    return _dim("stability", "稳定性", WEIGHTS["stability"], max(0, score), state, reasons,
                None if state == "ok" else "把程序交给系统托管，并打开开机自起。")


def score(egress=None, facts=None, expect_tz=None, expect_locale=None,
          dns=None, webrtc=None, reputation=None, service=None):
    """汇总成一个总分。未测维度不摊薄其它维度，覆盖率单独给出。"""
    dims = [
        egress_dimension(egress),
        consistency_dimension(facts, expect_tz, expect_locale),
        leakage_dimension(dns, webrtc),
        reputation_dimension(reputation),
        stability_dimension(service, facts),
    ]
    measured = [d for d in dims if d["state"] != "not_measured"]
    weight = sum(d["weight"] for d in measured)
    total = 0
    if weight:
        total = round(sum(d["score"] * d["weight"] for d in measured) / weight)
    coverage = round(weight / sum(WEIGHTS.values()) * 100)
    if coverage < 50:
        level = "insufficient"
    else:
        level = next(name for threshold, name in LEVELS if total >= threshold)
    high_risk = [
        {"id": d["id"], "label": d["label"], "why": " ".join(d["reasons"]), "fix": d["fix"]}
        for d in dims if d["state"] == "fail"
    ]
    return {
        "score": total,
        "level": level,
        "label": LABELS.get(level, "证据不足"),
        "coverage": coverage,
        "dimensions": dims,
        "high_risk": high_risk,
        "unmeasured": [d["id"] for d in dims if d["state"] == "not_measured"],
        "notice": "分数只描述这次实测到的项目，不代表任何服务端的判断，也不预测账号结果。"
                  "未测项不参与计分，覆盖率低于 50% 时不给等级。",
    }
