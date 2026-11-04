"""五步主线的上层编排：看、建、配、验、交。只调 remote 与本地能力，不新增测量逻辑。"""
import json
import os
import shutil
from pathlib import Path

from . import remote
from .models import InputError, now
from .storage import create_run, write

STEPS = ("check", "build", "browse", "accept", "deliver")


def _target(args):
    return remote.target(args.host, args.user, args.port, args.identity)


def check(args):
    item = _target(args)
    facts = remote.check(item)
    return {"step": "check", "host": item["host"], "facts": facts,
            "findings": remote.findings(facts), "at": now()}


def build(args):
    """对齐时间与语言，并把用户给的命令变成常驻服务。默认只出计划。"""
    item = _target(args)
    facts = remote.check(item)
    plan = remote.align_plan(facts, args.timezone, args.locale)
    wrapped = None
    if args.command:
        name = args.unit or "zhibi-service"
        wrapped = remote.wrap_plan(item, name, args.command, args.run_user, args.workdir,
                                   args.restart, args.memory_mb, args.cpu_percent,
                                   apply=args.apply)
    result = {"step": "build", "host": item["host"], "before": facts,
              "alignment": plan, "service": wrapped, "applied": bool(args.apply)}
    if args.apply:
        for step in plan:
            outcome = remote.execute(item, "set -e\n" + step["command"])
            step["applied"] = outcome["state"] == "ok"
        result["after"] = remote.check(item)
    return result


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
    return {"step": "browse", "host": item["host"], "source_facts": facts,
            "patch": patch,
            "fields": [
                {"field": "时区", "value": timezone, "why": "和服务器认为的时间一致"},
                {"field": "语言", "value": language, "why": "和系统语言一致"},
                {"field": "网络通道", "value": "服务器", "why": "让浏览器从这里出去"},
                {"field": "WebRTC", "value": "跟随通道", "why": "堵住会把本地位置漏出去的便道"},
            ],
            "notice": "这些是浏览器里要填的值；填完必须关掉浏览器再重开，然后重新读数才算生效。"}


def accept(args):
    """两端逐项对撞。没有本地读数时，本机项记为未测量，不记为通过。"""
    item = _target(args)
    facts = remote.check(item)
    unit_state = None
    if args.unit:
        outcome = remote.execute(item, "systemctl is-active " + args.unit)
        unit_state = outcome["value"].strip() if outcome["state"] == "ok" else None
    far = remote.verify(facts, args.timezone, args.locale, args.unit, unit_state)
    near = []
    local = None
    if args.browser:
        from .browser import parse_bundle
        local = parse_bundle(__import__("json").loads(open(args.browser, encoding="utf-8").read()))
    for key, expect in (("timezone", args.timezone), ("language", args.language),
                        ("egress", "server"), ("webrtc", "no local leak")):
        measured = local.get(key) if isinstance(local, dict) else None
        state = "not_measured" if measured is None else ("ok" if str(measured) == str(expect) else "fail")
        near.append({"key": key, "expected": expect, "measured": measured, "state": state})
    return {"step": "accept", "host": item["host"], "remote": far, "local": near,
            "notice": "远端与本地分开计数；未测量的项不计入通过。"}


FIRST_READ = """# 先读我

这份文件夹是这次环境搭建的记录。

## 现在是什么状态

{summary}

## 想临时停掉

    {stop}

## 想全部撤回

    bash rollback.sh

## 里面有什么

| 文件 | 内容 |
| --- | --- |
| 报告.html | 完整技术细节，双击就能看 |
| remote.md | 服务器上改了什么、日志在哪看 |
| browser.md | 浏览器每个字段填了什么、为什么 |
| verification.json | 两端读数与逐项结果 |
| reproduce.sh | 从零再来一遍 |
| rollback.sh | 全部撤回 |
"""


def deliver(args):
    """把本次结果写成用户能留住的文件夹。"""
    item = _target(args)
    facts = remote.check(item)
    unit_state = None
    if args.unit:
        outcome = remote.execute(item, "systemctl is-active " + args.unit)
        unit_state = outcome["value"].strip() if outcome["state"] == "ok" else None
    far = remote.verify(facts, args.timezone, args.locale, args.unit, unit_state)
    destination = Path(os.path.expanduser(args.out or "~/Desktop")).absolute() / (
        "zhibi-" + item["host"].replace(".", "-") + "-" + now()[:10])
    if destination.exists():
        raise InputError("目标文件夹已存在，请换一个输出目录。")
    destination.mkdir(parents=True, mode=0o700)
    counts = far["counts"]
    summary = ("远端各项已按要求确认。" if not counts.get("fail") and not counts.get("not_measured")
               else "有 %d 项没通过、%d 项没测，具体见报告。" % (counts.get("fail", 0), counts.get("not_measured", 0)))
    write(destination / "先读我.md", FIRST_READ.format(
        summary=summary, stop="systemctl stop " + (args.unit or "<服务名>")))
    write(destination / "verification.json", far)
    write(destination / "remote.md", "# 服务器上做了什么\n\n" + json.dumps(facts, ensure_ascii=False, indent=2) + "\n")
    write(destination / "browser.md", "# 浏览器要填什么\n\n" + json.dumps(
        {"时区": args.timezone or facts.get("tz"),
         "语言": args.locale or facts.get("lc_all") or facts.get("lang")}, ensure_ascii=False, indent=2) + "\n")
    write(destination / "reproduce.sh", "#!/bin/sh\nset -e\nzhibi check --host " + item["host"] + "\n")
    write(destination / "rollback.sh", "#!/bin/sh\nset -e\n"
          + ("systemctl disable --now " + args.unit + "\n" if args.unit else "")
          + "echo '其余改动按 remote.md 中的回滚命令逐条执行。'\n")
    if os.name == "posix":
        for name in ("reproduce.sh", "rollback.sh"):
            os.chmod(destination / name, 0o700)
    session = create_run(None)
    write(session / "verification.json", far)
    return {"step": "deliver", "directory": str(destination), "counts": counts,
            "session": str(session), "notice": summary}


def dispatch(args):
    return {"check": check, "build": build, "browse": browse,
            "accept": accept, "deliver": deliver}[args.command](args)


def register(sub):
    for name, text in (("check", "看服务器现状，不改任何东西"),
                       ("build", "让命令常驻并对齐时间与语言；默认只出计划"),
                       ("browse", "算出指纹浏览器该填什么"),
                       ("accept", "两端逐项对撞验收"),
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
        if name == "build":
            p.add_argument("--command", help="要长期运行的命令，由用户提供，原样使用")
            p.add_argument("--run-user", default="root")
            p.add_argument("--workdir")
            p.add_argument("--restart", type=int, default=10)
            p.add_argument("--memory-mb", type=int)
            p.add_argument("--cpu-percent", type=int)
            p.add_argument("--apply", action="store_true", help="真正执行；默认只出计划")
        if name == "accept":
            p.add_argument("--language", help="本地浏览器语言")
            p.add_argument("--browser", help="本地浏览器读数 JSON")
