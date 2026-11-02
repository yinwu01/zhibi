"""Rebuild a minimal summary. Never export original text or raw facts."""
from .engine import bundle, validate_report


def agent_summary(report):
    validate_report(report)
    known = {r["id"]: r for r in bundle("rules")}
    return {
        "format": "zhibi-agent-summary-1",
        "sample": report["sample"],
        "coverage": report["coverage"],
        "findings": [{"rule_id": f["rule_id"], "assessment": f["assessment"],
                      "topic": known[f["rule_id"]]["title"]}
                     for f in report["findings"] if f["rule_id"] in known],
        "notice": "只含固定规则主题和状态；没有 IP、地区、浏览器属性、时间、凭据或用户自由文本。"
    }


def compare_reports(before, after):
    validate_report(before)
    validate_report(after)
    known = {r["id"] for r in bundle("rules")}
    left = {f["rule_id"]: f["assessment"] for f in before["findings"] if f["rule_id"] in known}
    right = {f["rule_id"]: f["assessment"] for f in after["findings"] if f["rule_id"] in known}
    return {"format": "zhibi-comparison-1",
            "sample": before["sample"] or after["sample"],
            "changes": [{"rule_id": key, "before": left.get(key), "after": right.get(key)}
                        for key in sorted(left.keys() | right.keys()) if left.get(key) != right.get(key)],
            "notice": "只比较报告状态；状态变化不表示风险升降或防封效果。不同上下文与政策版本需另行核对。"}
