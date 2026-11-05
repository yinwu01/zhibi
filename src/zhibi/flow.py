"""五步主线的上层编排：看、建、配、验、交。评分与交付都在这层完成。"""
import json
import os
import shlex
import re
from html import escape
from pathlib import Path

from . import remote, score as scoring
from .models import InputError, now
from .storage import create_run, write

STEPS = ("check", "build", "browse", "accept", "deliver")
LEVEL_COLOR = {"low": "#2f7d4f", "medium": "#a97b16", "high": "#a53a2a", "insufficient": "#5b6470"}


def _target(args):
    return remote.target(args.host, args.user, args.port, args.identity)


def _egress(facts):
    org = (facts.get("egress_org") or "").strip()
    return {"ip": (facts.get("egress_ip") or "").strip() or None,
            "org": org or None,
            "datacenter": scoring.looks_datacenter(org) if org else None}


def _dns(facts):
    nameservers = [n for n in (facts.get("nameservers") or "").split() if n]
    return {"nameservers": nameservers, "public": remote.PUBLIC_DNS}


def _headline(result):
    """Three plain sentences for the user. No jargon."""
    s = result["score"]
    if s["level"] == "insufficient":
        first = "这次能确认的东西还太少，先不下结论。"
    else:
        first = "总体判断：%s（%d 分，覆盖 %d%% 的检查项）。" % (s["label"], s["score"], s["coverage"])
    issues = [d for d in s["dimensions"] if d["state"] in ("fail", "warn")]
    if issues:
        second = "需要处理的：" + "；".join(d["label"] for d in issues) + "。"
    else:
        second = "已经测到的项目里，没有需要处理的问题。"
    labels = {d["id"]: d["label"] for d in s["dimensions"]}
    missing = [labels.get(key, key) for key in s["unmeasured"]]
    third = ("这几项还没测：" + "、".join(missing) + "，所以它们不算通过。") if missing else "全部检查项都已测到。"
    return [first, second, third]


def check(args):
    item = _target(args)
    facts = remote.check(item, egress=getattr(args, "egress", False))
    result_score = scoring.score(egress=_egress(facts), facts=facts,
                                 expect_tz=args.timezone, expect_locale=args.locale,
                                 dns=_dns(facts))
    result = {"step": "check", "host": item["host"], "facts": facts,
              "findings": remote.findings(facts), "score": result_score,
              "headline": _headline({"score": result_score}), "at": now()}
    return result


def build(args):
    """对齐时间与语言，并把用户给的命令变成常驻服务。默认只出计划。"""
    item = _target(args)
    facts = remote.check(item)
    plan = remote.align_plan(facts, args.timezone, args.locale)
    directory = create_run(args.out) if args.apply else None
    if directory:
        write(directory / "before.private.json", {"target": item, "facts": facts, "alignment": plan})
    wrapped = None
    result = {"step": "build", "host": item["host"], "connection": item, "before": facts,
              "alignment": plan, "service": None, "applied": False}
    try:
        if args.apply:
            for step in plan:
                outcome = remote.execute(item, "set -e\n" + step["command"])
                step["applied"] = outcome["state"] == "ok"
                if not step["applied"]:
                    raise InputError("环境设置失败，已保存原值和部分结果；请先恢复或处理错误。")
        if args.command:
            name = args.unit or "zhibi-service"
            wrapped = remote.wrap_plan(item, name, args.command, args.run_user, args.workdir,
                                       args.restart, args.memory_mb, args.cpu_percent,
                                       apply=args.apply)
            result["service"] = wrapped
        result["applied"] = bool(args.apply) and (not wrapped or wrapped["applied"])
        result["summary"] = _build_summary(plan, wrapped, result["applied"])
        if args.apply:
            result["after"] = remote.check(item)
        return result
    finally:
        if directory:
            result["directory"] = str(directory)
            write(directory / "build.private.json", result)


def _build_summary(plan, wrapped, applied):
    lines = []
    if plan:
        lines.append("要改 %d 处：" % len(plan) + "、".join(
            {"timezone": "调整时间", "locale": "调整语言"}.get(s["id"], s["id"]) for s in plan))
    else:
        lines.append("时间与语言不需要改动。")
    if wrapped:
        state = "已经启动" if applied and wrapped.get("applied") else "还没启动"
        lines.append("你的命令会被交给系统托管，关机重启后自己起来（%s）。" % state)
    return " ".join(lines)


PATCH_FIELDS = ("timezone", "language", "webrtc")


def browse(args):
    """从服务器读数反推指纹浏览器该填什么。不代填，不推荐品牌。"""
    item = _target(args)
    facts = remote.check(item)
    timezone = args.timezone or facts.get("tz")
    locale = (facts.get("lc_all") if facts.get("lc_all") not in (None, "unset") else facts.get("lang")) or ""
    language = locale.split(".")[0].replace("_", "-") if "." in locale else locale.replace("_", "-")
    if not timezone and not language:
        raise InputError("服务器没有读到时间或语言，无法反推浏览器参数。")
    patch = {}
    if timezone:
        patch["timezone"] = timezone
    if language:
        patch["language"] = [language]
    patch["webrtc"] = "proxy"
    return {"step": "browse", "host": item["host"], "source_facts": facts, "patch": patch,
            "fields": [
                {"field": "时区（时间）", "value": timezone, "why": "和服务器认为的时间一致"},
                {"field": "语言", "value": language, "why": "和系统语言一致"},
                {"field": "网络通道", "value": "服务器", "why": "让浏览器从这里出去"},
                {"field": "WebRTC", "value": "跟随通道", "why": "堵住会把本地位置漏出去的便道"},
            ],
            "notice": "填完必须关掉浏览器再重开，然后重新测一遍才算生效。"}


def browser_readings(path):
    """Normalize validated probe exports; stale/automated observations cannot pass."""
    from .browser import parse_bundle
    from .models import timestamp
    from .scan import browser_paths
    with open(path, encoding="utf-8") as handle:
        bundle = parse_bundle(json.load(handle))
    context = next(o for o in bundle["observations"] if o["check_id"] == "browser.context")
    facts = context["facts"]
    fresh = lambda at: -60 <= (timestamp(now()) - timestamp(at)).total_seconds() <= 900
    if context["status"] != "ok" or facts.get("automated") or not fresh(context["at"]):
        return {}
    readings = {"timezone": facts.get("timezone"), "language": facts.get("language")}
    egress = next(o for o in bundle["observations"] if o["check_id"] == "browser.egress")
    if egress["status"] == "ok" and fresh(egress["at"]):
        readings["egress_ip"] = egress["facts"]["ip"]
    paths, _, _ = browser_paths(bundle, [], {"route_intent": "proxy"})
    rtc = next((p for p in paths if p["id"] == "path:webrtc"), {})
    relation = rtc.get("https_relation")
    readings["webrtc_leak"] = {"different": True, "same_observed": False}.get(relation)
    return readings


def accept(args):
    """两端逐项对撞并重新评分。没有本地读数时，本机项记为未测量。"""
    item = _target(args)
    facts = remote.check(item, egress=getattr(args, "egress", False))
    unit_state = enabled = None
    if args.unit:
        remote._check(remote.UNIT, args.unit, "服务名无效。")
        outcome = remote.execute(item, "systemctl is-active " + args.unit)
        unit_state = outcome["value"].strip() if outcome["state"] == "ok" else None
        outcome = remote.execute(item, "systemctl is-enabled " + args.unit)
        enabled = outcome["value"].strip() == "enabled" if outcome["state"] == "ok" else None
    far = remote.verify(facts, args.timezone, args.locale, args.unit, unit_state)
    local_readings = {}
    if getattr(args, "browser", None):
        local_readings = browser_readings(args.browser)
    near = []
    for key, expect, measured in (
            ("时区", args.timezone, local_readings.get("timezone")),
            ("语言", args.language, local_readings.get("language")),
            ("对外身份", facts.get("egress_ip"), local_readings.get("egress_ip")),
            ("WebRTC 与 HTTPS 出口", "一致", {True: "不同", False: "一致"}.get(local_readings.get("webrtc_leak")))):
        state = "not_measured" if measured in (None, "") or expect in (None, "") else ("ok" if str(measured) == str(expect) else "fail")
        near.append({"key": key, "expected": expect, "measured": measured, "state": state})
    result_score = scoring.score(
        egress=_egress(facts), facts=facts, expect_tz=args.timezone, expect_locale=args.locale,
        dns=_dns(facts), webrtc={"leak": local_readings.get("webrtc_leak")},
        service={"active": unit_state == "active" if unit_state else None,
                 "enabled": enabled})
    return {"step": "accept", "host": item["host"], "at": now(), "facts": facts, "remote": far, "local": near,
            "score": result_score, "headline": _headline({"score": result_score}),
            "notice": "远端与本地分开计数；未测量的项不计入通过。"}


FIRST_READ = """# 先读我

这份文件夹是这次搭建留下的记录。

## 现在是什么状态

{summary}

## 想临时停掉

    {stop}

## 想恢复本轮服务与时区

    bash rollback.sh

## 里面有什么

| 文件 | 内容 |
| --- | --- |
| 报告.html | 完整细节，双击就能看 |
| remote.md | 服务器上改了什么、日志在哪看 |
| browser.md | 浏览器每个字段填了什么、为什么 |
| verification.json | 两端读数与逐项结果 |
| reproduce.sh | 重新检查服务器 |
| rollback.sh | 按部署回执恢复服务与时区 |
"""


def render_html(report):
    """One self-contained page. Full detail lives here, not in the chat."""
    s = report["score"]
    rows = "".join(
        "<tr><td>%s</td><td>%s</td><td>%d</td><td>%s</td></tr>" % (
            escape(d["label"]), escape(d["state"]), d["score"],
            escape(" ".join(d["reasons"]) or "—"))
        for d in s["dimensions"])
    checks = "".join(
        "<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            escape(str(c.get("key"))), escape(str(c.get("measured"))), escape(c.get("state", "")))
        for c in (report.get("remote") or {}).get("checks", []) + report.get("local", []))
    facts = "".join("<tr><td>%s</td><td>%s</td></tr>" % (escape(k), escape(str(v)))
                    for k, v in sorted((report.get("facts") or {}).items()))
    color = LEVEL_COLOR.get(s["level"], "#5b6470")
    return """<!doctype html><html lang="zh"><meta charset="utf-8">
<title>环境准备记录</title>
<style>
body{{font:15px/1.7 -apple-system,system-ui,sans-serif;max-width:820px;margin:40px auto;padding:0 20px;color:#222}}
h1{{font-size:22px;margin:0 0 4px}} .sub{{color:#666;font-size:13px}}
.badge{{display:inline-block;padding:6px 14px;border-radius:14px;color:#fff;background:{color};font-size:17px;margin:14px 0}}
table{{border-collapse:collapse;width:100%;margin:14px 0;font-size:14px}}
th,td{{border-bottom:1px solid #e6e6e6;padding:7px 8px;text-align:left;vertical-align:top}}
th{{color:#666;font-weight:600}} .muted{{color:#777;font-size:13px}}
</style>
<h1>环境准备记录</h1>
<div class="sub">{host} · {at}</div>
<div class="badge">{label} · {score} 分 · 覆盖 {coverage}%</div>
<h2>分项</h2>
<table><tr><th>项目</th><th>状态</th><th>得分</th><th>依据</th></tr>{rows}</table>
<h2>逐项核对</h2>
<table><tr><th>项目</th><th>实测</th><th>状态</th></tr>{checks}</table>
<h2>服务器读数</h2>
<table>{facts}</table>
<p class="muted">{notice}</p>
</html>""".format(color=color, host=escape(str(report.get("host", ""))),
                 at=escape(str(report.get("at", ""))), label=escape(s["label"]),
                 score=s["score"], coverage=s["coverage"], rows=rows, checks=checks,
                 facts=facts, notice=escape(s["notice"]))


def deliver_files(destination, report, unit=None, timezone=None, locale=None, facts=None):
    """Write the folder the user keeps. Pure file work, no network."""
    destination = Path(destination)
    s = report["score"]
    summary = "；".join(report.get("headline") or [s["label"]])
    target = report.get("connection") or remote.target(report["host"])
    def on_server(command):
        return " ".join(shlex.quote(v) for v in remote.ssh_argv(target, command))
    if unit:
        remote._check(remote.UNIT, unit, "服务名无效。")
    stop = on_server("systemctl stop " + unit) if unit else "本次没有后台服务。"
    receipt = report.get("deployment") or {}
    recovery = (receipt.get("service") or {}).get("rollback")
    if recovery and not re.fullmatch(r"sh /var/lib/zhibi/deployments/[a-f0-9]{32}/rollback\.sh", recovery):
        raise InputError("部署恢复路径无效。")
    destination.mkdir(parents=True, mode=0o700, exist_ok=False)
    write(destination / "先读我.md", FIRST_READ.format(
        summary=summary, stop=stop))
    write(destination / "报告.html", render_html(report))
    write(destination / "verification.json", report)
    write(destination / "remote.md", "# 服务器观测与部署记录\n\n" + json.dumps(
        {"facts": report.get("facts") or facts or {}, "deployment": receipt,
         "stop": stop, "logs": on_server("journalctl -u " + unit + " -n 50 --no-pager") if unit else None},
        ensure_ascii=False, indent=2) + "\n")
    write(destination / "browser.md", "# 浏览器实际验收\n\n" + json.dumps(
        {"checks": report.get("local", []), "timezone_target": timezone,
         "locale_target": locale, "notice": "这里只记录观测与目标，不代表已经修改配置。"},
        ensure_ascii=False, indent=2) + "\n")
    recheck = ["zhibi", "check", "--host", target["host"], "--user", target["user"], "--port", str(target["port"])]
    if target.get("identity"):
        recheck += ["--identity", target["identity"]]
    recheck += ["--egress"]
    write(destination / "reproduce.sh", "#!/bin/sh\nset -e\n" + " ".join(shlex.quote(v) for v in recheck) + "\n")
    commands = [on_server(recovery)] if recovery else []
    for change in reversed(receipt.get("alignment", [])):
        if change.get("applied") and change.get("id") == "timezone":
            old = remote._check(remote.TZONE, change.get("before"), "原时区无效。")
            commands.append(on_server("timedatectl set-timezone " + old))
    write(destination / "rollback.sh", "#!/bin/sh\nset -e\n" + (
        "\n".join(commands) + "\n" if commands else
        "echo '没有本次部署回执，不能自动恢复。请提供 --build-receipt。' >&2\nexit 1\n"))
    if os.name == "posix":
        for name in ("reproduce.sh", "rollback.sh"):
            os.chmod(destination / name, 0o700)
    return destination


def deliver(args):
    item = _target(args)
    report = accept(args)
    report["step"] = "deliver"
    facts, result_score = report["facts"], report["score"]
    report["connection"] = item
    if getattr(args, "build_receipt", None):
        with open(args.build_receipt, encoding="utf-8") as handle:
            receipt = json.load(handle)
        if receipt.get("connection") != item or receipt.get("step") != "build":
            raise InputError("部署回执与当前目标不一致。")
        report["deployment"] = receipt
    base = Path(os.path.expanduser(args.out or "~/Desktop")).absolute()
    folder = base / ("zhibi-" + item["host"].replace(".", "-") + "-" + now()[:10])
    if folder.exists():
        raise InputError("目标文件夹已存在，请换一个输出目录。")
    destination = deliver_files(folder, report, args.unit, args.timezone, args.locale, facts)
    session = create_run(None)
    write(session / "report.json", report)
    return {"step": "deliver", "directory": str(destination), "score": result_score,
            "headline": report["headline"], "session": str(session)}


def dispatch(args):
    result = {"check": check, "build": build, "browse": browse,
              "accept": accept, "deliver": deliver}[args.command](args)
    if args.command in ("check", "browse", "accept") and getattr(args, "out", None):
        directory = create_run(args.out)
        write(directory / (args.command + ".private.json"), result)
        result["directory"] = str(directory)
    return result


def register(sub):
    for name, text in (("check", "看服务器现状并给出评分，不改任何东西"),
                       ("build", "让命令常驻并对齐时间与语言；默认只出计划"),
                       ("browse", "算出指纹浏览器该填什么"),
                       ("accept", "两端逐项对撞并重新评分"),
                       ("deliver", "把结果写成一个能留住的文件夹")):
        p = sub.add_parser(name, help=text)
        p.add_argument("--host", required=True, help="服务器地址")
        p.add_argument("--user", default="root", help="SSH 用户")
        p.add_argument("--port", type=int, default=22, help="SSH 端口")
        p.add_argument("--identity", help="私钥文件路径（权限 600）")
        p.add_argument("--timezone", help="目标时区，例如 Europe/Berlin")
        p.add_argument("--locale", help="目标 locale，例如 en_US.UTF-8")
        p.add_argument("--unit", help="服务名")
        p.add_argument("--out", help="交付目录，默认桌面")
        p.add_argument("--egress", action="store_true",
                       help="允许服务器发起两次查询以取得自己的对外身份（可选）")
        if name == "deliver":
            p.add_argument("--build-receipt", help="本轮 build.private.json，用于生成远端恢复步骤")
        if name == "build":
            p.add_argument("--command", help="要长期运行的命令，由用户提供，原样使用")
            p.add_argument("--run-user", default="root")
            p.add_argument("--workdir")
            p.add_argument("--restart", type=int, default=10)
            p.add_argument("--memory-mb", type=int)
            p.add_argument("--cpu-percent", type=int)
            p.add_argument("--apply", action="store_true", help="真正执行；默认只出计划")
        if name in ("accept", "deliver"):
            p.add_argument("--language", help="本地浏览器语言")
            p.add_argument("--browser", help="本地浏览器读数 JSON")
