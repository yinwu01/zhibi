"""Explicit, reversible maintenance. Never called by diagnostics or suite --preset all."""
import json
import os
import platform
import re
import shutil
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .diagnostics import command, cli_installation
from .models import InputError, now, read_json
from .storage import create_run, write


def safe(value, pattern, label):
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise InputError(label + "格式无效。")
    return value


def ps(value):
    return "'" + value.replace("'", "''") + "'"


def read_setting(action, scope, runner=command):
    system = platform.system()
    if action == "timezone":
        args = ["systemsetup", "-gettimezone"] if system == "Darwin" else ["timedatectl", "show", "--property=Timezone", "--value"] if system == "Linux" else ["powershell", "-NoProfile", "-Command", "(Get-TimeZone).Id"]
    elif action == "locale":
        if system != "Darwin":
            raise InputError("当前 locale 写入适配器仅支持 macOS；其他平台不冒充已支持。")
        args = ["defaults", "read", "-g", "AppleLocale"]
    elif action == "ipv6":
        safe(scope, r"[^\x00-\x1f]{1,100}", "专用网络服务名称")
        args = ["networksetup", "-getinfo", scope] if system == "Darwin" else ["nmcli", "-g", "ipv6.method", "connection", "show", scope] if system == "Linux" else ["powershell", "-NoProfile", "-Command", "(Get-NetAdapterBinding -Name " + ps(scope) + " -ComponentID ms_tcpip6).Enabled"]
    else:
        raise InputError("未知维护设置。")
    output, state = runner(args)
    if state != "ok" or not output:
        raise InputError("无法读取原设置；未生成可执行修改，需检查权限和系统工具。")
    value = output.strip()
    if action == "timezone" and system == "Darwin":
        value = value.removeprefix("Time Zone: ")
    if action == "ipv6" and system == "Darwin":
        match = re.search(r"^IPv6: (Off|Automatic|Link-local only|Manual)$", value, re.M)
        if not match or match[1] == "Manual":
            raise InputError("当前 IPv6 为手动或未知配置；为保证可恢复，拒绝自动改写。")
        value = {"Off": "off", "Automatic": "auto", "Link-local only": "linklocal"}[match[1]]
    if action == "ipv6" and system == "Windows":
        if value.lower() not in ("true", "false"):
            raise InputError("无法核实网卡 IPv6 开关。")
        value = "auto" if value.lower() == "true" else "off"
    if action == "ipv6" and system == "Linux" and value not in {"auto", "disabled", "ignore", "link-local", "dhcp", "manual", "shared"}:
        raise InputError("无法核实 NetworkManager IPv6 配置。")
    safe(value, r"[A-Za-z0-9_ ./@=+-]{1,120}", "原设置")
    return value


def setting_command(action, scope, value):
    system = platform.system()
    if action == "timezone":
        safe(value, r"[A-Za-z0-9_ /+-]{1,120}", "时区")
        if system != "Windows":
            try:
                ZoneInfo(value)
            except (ZoneInfoNotFoundError, ValueError):
                raise InputError("未知 IANA 时区。") from None
        return ["systemsetup", "-settimezone", value] if system == "Darwin" else ["timedatectl", "set-timezone", value] if system == "Linux" else ["powershell", "-NoProfile", "-Command", "Set-TimeZone -Id " + ps(value)]
    if action == "locale":
        safe(value, r"[A-Za-z]{2,3}[_-][A-Za-z]{2}(?:@calendar=[a-z]+)?", "区域")
        if system != "Darwin":
            raise InputError("locale 修改目前仅支持 macOS。")
        return ["defaults", "write", "-g", "AppleLocale", "-string", value]
    if action != "ipv6":
        raise InputError("未知维护动作。")
    safe(scope, r"[^\x00-\x1f]{1,100}", "专用网络服务名称")
    if system == "Darwin":
        option = {"off": "-setv6off", "auto": "-setv6automatic", "linklocal": "-setv6linklocal"}.get(value)
        if not option:
            raise InputError("不支持恢复该 IPv6 模式。")
        return ["networksetup", option, scope]
    if system == "Linux":
        if value not in {"off", "auto", "disabled", "ignore", "link-local", "dhcp", "manual", "shared"}:
            raise InputError("IPv6 模式无效。")
        return ["nmcli", "connection", "modify", scope, "ipv6.method", "disabled" if value == "off" else value]
    if system == "Windows" and value in {"off", "auto"}:
        return ["powershell", "-NoProfile", "-Command", ("Disable" if value == "off" else "Enable") + "-NetAdapterBinding -Name " + ps(scope) + " -ComponentID ms_tcpip6"]
    raise InputError("此平台没有该维护适配器。")


def settings(action, scope, value, apply=False, out=None, runner=command):
    before = read_setting(action, scope, runner)
    args = setting_command(action, scope, value)
    rollback = setting_command(action, scope, before)
    plan = {"format": "zhibi-setting-1", "at": now(), "platform": platform.system(), "action": action,
            "scope": scope, "before": before, "requested": value, "command": args, "rollback": rollback,
            "impact": "指定网络服务；可能影响使用该服务的其他程序" if action == "ipv6" else "当前用户或整台主机设置；不是只修改浏览器",
            "applied": False}
    if not apply:
        return plan
    directory = create_run(out)
    write(directory / "before.private.json", plan)
    _, state = runner(args, timeout=15)
    # Settings can be changed even if a command returns a failure; always re-observe.
    try:
        after = read_setting(action, scope, runner)
    except InputError:
        after = None
    expected = "disabled" if platform.system() == "Linux" and action == "ipv6" and value == "off" else value
    receipt = {**plan, "command_state": state, "after": after, "applied": after == expected,
               "effective_network_verified": False,
               "next_step": "Linux 配置需用户选择时重连连接；所有平台都需在同一浏览器重新测量 IPv6。"}
    write(directory / "receipt.private.json", receipt)
    return {"directory": str(directory), "applied": receipt["applied"], "effective_network_verified": False,
            "restore_command": "maintain restore " + str(directory / "receipt.private.json") + " --apply"}


def restore(path, apply=False, out=None, runner=command):
    data = read_json(path)
    if not isinstance(data, dict) or data.get("format") != "zhibi-setting-1" or data.get("platform") != platform.system() or data.get("action") not in {"timezone", "locale", "ipv6"}:
        raise InputError("恢复记录无效或来自其他平台。")
    # Never execute commands from an imported receipt. Rebuild from validated settings.
    current = read_setting(data["action"], data["scope"], runner)
    if current != data.get("after"):
        raise InputError("当前设置已变化，拒绝覆盖其他人的后续修改。")
    return settings(data["action"], data["scope"], data["before"], apply, out, runner)


def repair(version, apply=False, out=None, runner=command):
    safe(version, r"\d+\.\d+\.\d+", "固定版本")
    client = os.environ.get("ZHIBI_CLIENT", "").strip()
    package = os.environ.get("ZHIBI_CLIENT_PACKAGE", "").strip()
    info = cli_installation(client, runner)
    method = (info.get("facts") or {}).get("method")
    if method in ("npm", "bun") and not package:
        raise InputError("自动修复需要声明 ZHIBI_CLIENT_PACKAGE；本项目不内置任何客户端包名。")
    if method == "npm":
        args = ["npm", "install", "-g", package + "@" + version]
    elif method == "bun":
        args = ["bun", "add", "-g", package + "@" + version]
    elif method == "native":
        args = [shutil.which(client), "install", version]
    else:
        raise InputError("自动修复仅支持检测到的 npm/bun/native 安装；不覆盖未知或系统包管理器安装。")
    plan = {"command": args, "before_version": (info.get("facts") or {}).get("version"), "requested_version": version, "account_files_modified": False}
    if not apply:
        return plan
    directory = create_run(out)
    write(directory / "before.private.json", plan)
    _, state = runner(args, timeout=120)
    after = cli_installation(client, runner)
    passed = (after.get("facts") or {}).get("version") == version
    write(directory / "receipt.private.json", dict(plan, command_state=state, after=after, version_verified=passed))
    return {"directory": str(directory), "version_verified": passed, "rollback_version": plan["before_version"]}


def register(sub):
    p = sub.add_parser("maintain", help="可选维护：默认只显示计划；--apply 才修改，并记录恢复信息")
    p.add_argument("action", choices=("ipv6", "timezone", "locale", "cli-repair", "restore"))
    p.add_argument("value", help="目标值；ipv6 使用 off；restore 使用本机 receipt 路径")
    p.add_argument("--scope", default="", help="IPv6 必须指定专用网络服务/网卡/NetworkManager 连接名")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--out")


def dispatch(args):
    if args.action == "restore":
        return restore(args.value, args.apply, args.out)
    if args.action == "cli-repair":
        return repair(args.value, args.apply, args.out)
    return settings(args.action, args.scope, args.value, args.apply, args.out)
