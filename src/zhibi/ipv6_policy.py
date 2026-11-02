"""Scoped, operator-reviewed IPv6 configuration evidence; never infer it from timeout."""
import hashlib
import json
import re
from pathlib import Path

from .models import InputError, exact, now, read_json, timestamp

ADVICE = "在专用环境的代理客户端或出口防火墙中禁用 IPv6 出站，保存并重启该环境，再核对生效配置。"


def scan_digest(report):
    data = {k: v for k, v in report.items() if k != "ipv6_confirmation"}
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def ipv6_reachable(report):
    return any(s["family"] == 6 for s in report["subjects"]) or (report["target"] == "browser" and any(
        p["id"] == "path:browser-ipv6" and p["status"] == "ok" and not p["automated"] for p in report["paths"]))


def validate_confirmation(report):
    item = report.get("ipv6_confirmation")
    if item is None:
        return
    fields = {"format", "target", "scope", "configuration", "method", "confirmed_at", "scan_sha256", "evidence_sha256"}
    exact(item, fields, fields)
    if (item["format"] != "zhibi-ipv6-confirmation-1" or item["target"] != report["target"]
            or item["scope"] != "dedicated_environment" or item["configuration"] not in {"disabled", "blocked"}
            or item["method"] not in {"settings_ui", "local_config"}):
        raise InputError("IPv6 确认必须来自同一专用环境的配置核对。")
    for key in ("scan_sha256", "evidence_sha256"):
        if not isinstance(item[key], str) or not re.fullmatch(r"[a-f0-9]{64}", item[key]):
            raise InputError("IPv6 配置确认缺少有效证据摘要。")
    if item["scan_sha256"] != scan_digest(report):
        raise InputError("IPv6 确认不属于这份检测；环境或观测变化后需重新核对。")
    age = (timestamp(item["confirmed_at"]) - timestamp(report["generated_at"])).total_seconds()
    if not 0 <= age <= 900:
        raise InputError("IPv6 配置核对应在本次检测后十五分钟内完成。")
    if ipv6_reachable(report):
        raise InputError("本次仍测到 IPv6 连接，不能标记为已关闭；请核对配置后重新检测。")


def policy_row(report):
    validate_confirmation(report)
    if report.get("ipv6_confirmation"):
        return {"label": "IPv6 出站策略", "state": "measured", "result": "通过",
                "advice": "已核对专用环境的 IPv6 禁用或阻断配置，保持当前设置。"}
    return {"label": "IPv6 出站策略", "state": "attention",
            "result": "建议关闭" if ipv6_reachable(report) else "待确认", "advice": ADVICE}


def confirm_run(run_dir, evidence, configuration, method, reviewed=False, out=None):
    """Record an operator's configuration review, not an automatic firewall audit."""
    from .scan import validate_scan, render_scan, scan_markdown, scan_summary
    from .storage import create_run, write
    if not reviewed:
        raise InputError("先核对同一专用环境的生效配置，再用 --reviewed 记录确认；请求失败不能代替配置证据。")
    source = Path(run_dir)
    report = validate_scan(read_json(source / "report.json"))
    snapshot = read_json(source / "snapshot.private.json")
    file = Path(evidence).expanduser().resolve()
    if not file.is_file() or not 0 < file.stat().st_size <= 10 * 1024 * 1024:
        raise InputError("请提供已核对的配置文件或设置截图，大小须为 1 字节至 10 MiB。")
    digest = hashlib.sha256(file.read_bytes()).hexdigest()
    report["ipv6_confirmation"] = {
        "format": "zhibi-ipv6-confirmation-1", "target": report["target"], "scope": "dedicated_environment",
        "configuration": configuration, "method": method, "confirmed_at": now(),
        "scan_sha256": scan_digest(report), "evidence_sha256": digest}
    validate_scan(report)
    html = render_scan(report, snapshot)
    summary = scan_summary(report)
    directory = create_run(out)
    write(directory / "report.json", report)
    write(directory / "snapshot.private.json", snapshot)
    write(directory / "ipv6-evidence.private.json", {"path": str(file), "sha256": digest,
          "review": "operator-reviewed configuration; not automatically verified"})
    write(directory / "report.html", html)
    write(directory / "report.md", scan_markdown(report))
    write(directory / "agent-summary.json", summary)
    return {"directory": str(directory), "report": str(directory / "report.html"), "summary": summary}
