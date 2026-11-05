"""远端检查、对齐与进程包裹。默认只输出计划，--apply 才修改。"""
import base64
import json
import os
import re
import shutil
import subprocess

from .models import InputError, now
from .storage import create_run, write

HOST = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?\Z")
USER = re.compile(r"[a-z_][a-z0-9_-]{0,31}\Z")
UNIT = re.compile(r"[a-z0-9][a-z0-9-]{0,60}\Z")
TZONE = re.compile(r"[A-Za-z][A-Za-z0-9_+-]{0,40}(?:/[A-Za-z0-9_+-]{1,40}){0,2}\Z")
LOCALE = re.compile(r"[a-z]{2,3}_[A-Z]{2}\.(?:UTF-8|utf8)\Z")

# 远端只读取值，不含任何用户输入。每行 KEY=VALUE，供本机解析。
FACTS = r"""set -e
printf 'os=%s\n' "$( (. /etc/os-release 2>/dev/null && printf '%s' "$PRETTY_NAME") || uname -s )"
printf 'kernel=%s\n' "$(uname -r)"
printf 'arch=%s\n' "$(uname -m)"
printf 'virt=%s\n' "$(systemd-detect-virt 2>/dev/null || echo unknown)"
printf 'systemd=%s\n' "$( [ -d /run/systemd/system ] && echo yes || echo no )"
printf 'tz=%s\n' "$(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null || echo unknown)"
printf 'ntp=%s\n' "$(timedatectl show -p NTPSynchronized --value 2>/dev/null || echo unknown)"
printf 'localtime=%s\n' "$(readlink -f /etc/localtime 2>/dev/null || echo unknown)"
printf 'lang=%s\n' "${LANG:-unset}"
printf 'lc_all=%s\n' "${LC_ALL:-unset}"
printf 'locales=%s\n' "$(locale -a 2>/dev/null | wc -l | tr -d ' ')"
printf 'nameservers=%s\n' "$(awk '/^nameserver/{printf "%s ", $2}' /etc/resolv.conf 2>/dev/null)"
printf 'addresses=%s\n' "$(ip -4 -o addr show scope global 2>/dev/null | awk '{printf "%s ", $4}')"
printf 'nproc=%s\n' "$(nproc 2>/dev/null || echo unknown)"
printf 'mem_mb=%s\n' "$(awk '/MemTotal/{printf "%d", $2/1024}' /proc/meminfo 2>/dev/null || echo unknown)"
printf 'utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
"""

EGRESS = r"""set -e
ip=$(curl -s --max-time 6 https://api.ipify.org 2>/dev/null || wget -qO- --timeout=6 https://api.ipify.org 2>/dev/null || echo '')
printf 'egress_ip=%s\n' "$ip"
org=$(curl -s --max-time 6 https://ipinfo.io/org 2>/dev/null || echo '')
printf 'egress_org=%s\n' "$org"
"""

PUBLIC_DNS = {"8.8.8.8", "8.8.4.4", "1.1.1.1", "1.0.0.1", "9.9.9.9", "208.67.222.222", "208.67.220.220"}


def _check(pattern, value, message):
    if not isinstance(value, str) or not pattern.match(value):
        raise InputError(message)
    return value


def target(host, user="root", port=22, identity=None):
    """Connect parameters. Values are validated, never interpolated into a shell."""
    item = {
        "host": _check(HOST, host, "服务器地址无效。"),
        "user": _check(USER, user, "服务器用户名无效。"),
        "port": int(port),
        "identity": None,
    }
    if not 1 <= item["port"] <= 65535:
        raise InputError("SSH 端口无效。")
    if identity:
        path = os.path.expanduser(str(identity))
        if not os.path.isfile(path):
            raise InputError("身份文件不存在。")
        if os.name == "posix" and (os.stat(path).st_mode & 0o077):
            raise InputError("身份文件权限过宽，请先改为 600。")
        item["identity"] = path
    return item


def ssh_argv(item, script):
    ssh = shutil.which("ssh")
    if not ssh:
        raise InputError("找不到 ssh 客户端。")
    argv = [ssh, "-F", "NUL" if os.name == "nt" else "/dev/null",
            "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ConnectTimeout=10", "-p", str(item["port"])]
    if item["identity"]:
        argv += ["-i", item["identity"]]
    return argv + ["--", item["user"] + "@" + item["host"], script]


def execute(item, script, timeout=60):
    """Run one fixed script. No user input reaches the remote shell."""
    try:
        done = subprocess.run(ssh_argv(item, script), capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return {"state": "error", "value": ""}
    if done.returncode != 0:
        return {"state": "error", "value": ""}
    return {"state": "ok", "value": done.stdout}


def parse_facts(text):
    facts = {}
    for line in text.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            if re.fullmatch(r"[a-z_]+", key):
                facts[key] = value.strip()
    return facts


def check(item, egress=False):
    """Read remote facts. Egress is opt-in: it makes two outbound requests from the server."""
    outcome = execute(item, FACTS)
    if outcome["state"] != "ok":
        raise InputError("无法读取远端状态；请确认地址、端口、凭据与首次指纹核对。")
    facts = parse_facts(outcome["value"])
    if egress:
        extra = execute(item, EGRESS, timeout=30)
        if extra["state"] == "ok":
            facts.update(parse_facts(extra["value"]))
        else:
            facts["egress_ip"] = ""
    if "tz" not in facts:
        raise InputError("远端返回内容不完整；本机判定为失败，不记为通过。")
    return facts


def findings(facts):
    """Remote consistency findings. Each item carries a state, never a guess."""
    items = []

    def add(key, state, detail):
        items.append({"key": key, "state": state, "detail": detail})

    add("remote.systemd", "ok" if facts.get("systemd") == "yes" else "fail",
        "远端由 systemd 托管，可承载常驻进程。" if facts.get("systemd") == "yes"
        else "没有 systemd，无法保证进程重启后自起。")
    add("remote.clock", "ok" if facts.get("ntp") == "yes" else "changed_unverified",
        "系统时钟已同步。" if facts.get("ntp") == "yes" else "时钟未确认同步；时间戳漂移会与出口地区矛盾。")
    nameservers = [n for n in (facts.get("nameservers") or "").split() if n]
    add("remote.dns", "observed" if nameservers else "not_measured",
        "已读取解析器配置；此读数不证明 DNS 请求实际路径。" if nameservers else "未读到解析器配置。")
    add("remote.locale", "ok" if facts.get("locales", "0").isdigit() and int(facts.get("locales", "0")) > 1 else "changed_unverified",
        "已生成多个 locale。" if facts.get("locales", "0").isdigit() and int(facts.get("locales", "0")) > 1
        else "可用 locale 很少，语言对齐可能不生效。")
    try:
        tzfile = facts.get("localtime", "")
        add("remote.timezone", "ok" if "/zoneinfo/" in tzfile or tzfile.startswith("Etc/") else "changed_unverified",
            "时区来自 zoneinfo：" + tzfile if tzfile else "未读到时区文件。")
    except (TypeError, AttributeError):
        add("remote.timezone", "not_measured", "时区读取失败。")
    return items


def align_plan(facts, timezone=None, locale=None, nameserver=None):
    """Build the change list. Nothing here touches the server."""
    plan = []
    if timezone:
        _check(TZONE, timezone, "时区名称无效。")
        if facts.get("tz") != timezone:
            plan.append({"id": "timezone",
                         "command": "timedatectl set-timezone " + timezone,
                         "before": facts.get("tz"), "after": timezone,
                         "effect": "系统时区与出口地区一致",
                         "rollback": "timedatectl set-timezone " + (facts.get("tz") or "UTC")})
    if locale:
        _check(LOCALE, locale, "locale 名称无效。")
        plan.append({"id": "locale",
                     "command": "localedef -i " + locale.split(".")[0] + " -f UTF-8 " + locale,
                     "before": facts.get("lang"), "after": locale,
                     "effect": "生成目标语言资源；不改变已有登录会话或服务默认语言",
                     "rollback": "保留原值 " + str(facts.get("lang")), "skip_if_present": True})
    if nameserver:
        raise InputError("本项目不代改远端 DNS；请用 resolvconf 或云厂商控制台自行设置，再用 remote verify 复核。")
    return plan


UNIT_TEMPLATE = """[Unit]
Description={description}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User={user}
WorkingDirectory={workdir}
ExecStart={command}
Restart=on-failure
RestartSec={restart}
LimitNOFILE=65535
NoNewPrivileges=yes
PrivateTmp=yes
StandardOutput=journal
StandardError=journal
{limits}
[Install]
WantedBy=multi-user.target
"""


def unit(name, command, user="root", workdir=None, restart=10, memory_mb=None, cpu_percent=None, description=None):
    """Build a systemd unit. The command is the user's own, used verbatim."""
    _check(UNIT, name, "unit 名称只能是小写字母、数字和连字符。")
    if not isinstance(command, str) or not command.strip():
        raise InputError("需要一条要长期运行的命令。")
    if any(ch in command for ch in "\n\r\0"):
        raise InputError("命令不能包含换行或空字符。")
    if len(command) > 4096:
        raise InputError("命令过长。")
    for label, value in (("工作目录", workdir), ("描述", description)):
        if value is not None and (not isinstance(value, str) or any(c in value for c in "\n\r\0%")):
            raise InputError(label + "含无效字符。")
    if workdir and not workdir.startswith("/"):
        raise InputError("工作目录必须为绝对路径。")
    limits = ""
    if memory_mb:
        limits += "MemoryMax=" + str(int(memory_mb)) + "M\n"
    if cpu_percent:
        limits += "CPUQuota=" + str(int(cpu_percent)) + "%\n"
    return UNIT_TEMPLATE.format(
        description=description or ("zhibi wrapped: " + name),
        user=_check(USER, user, "运行用户无效。"),
        workdir=workdir if workdir and workdir.startswith("/") else "/",
        command=command,
        restart=max(1, min(int(restart), 3600)),
        limits=limits,
    )


def wrap_plan(item, name, command, user="root", workdir=None, restart=10,
              memory_mb=None, cpu_percent=None, apply=False):
    body = unit(name, command, user, workdir, restart, memory_mb, cpu_percent)
    from .service import deployment
    transaction = deployment(name, body)
    plan = {"action": "wrap", "unit": name,
            "receipt": transaction["receipt"], "rollback": transaction["rollback"],
            "applied": False, "command_source": "user"}
    if not apply:
        return plan
    outcome = execute(item, transaction["script"], timeout=120)
    plan["applied"] = outcome["state"] == "ok"
    plan["state"] = outcome["state"]
    plan["checked_at"] = now()
    plan["notice"] = "启动失败会尝试恢复原服务；连接中断后需检查回执和实际状态。进程启动不代表应用健康。"
    return plan


def verify(facts, expect_tz=None, expect_locale=None, unit_name=None, unit_state=None):
    """Four-way consistency. Unmeasured stays unmeasured."""
    results = []
    results.append({"key": "timezone", "expected": expect_tz, "measured": facts.get("tz"),
                    "state": "ok" if expect_tz and facts.get("tz") == expect_tz else
                             ("fail" if expect_tz else "not_measured")})
    locale = facts.get("lc_all") if facts.get("lc_all") not in (None, "unset") else facts.get("lang")
    results.append({"key": "locale", "expected": expect_locale, "measured": locale,
                    "state": "ok" if expect_locale and locale == expect_locale else
                             ("fail" if expect_locale else "not_measured")})
    results.append({"key": "clock", "expected": "yes", "measured": facts.get("ntp"),
                    "state": "ok" if facts.get("ntp") == "yes" else "changed_unverified"})
    nameservers = [n for n in (facts.get("nameservers") or "").split() if n]
    results.append({"key": "dns", "expected": "实际解析路径需另测", "measured": nameservers,
                    "state": "observed" if nameservers else "not_measured"})
    if unit_name:
        results.append({"key": "unit", "expected": "active", "measured": unit_state,
                        "state": "ok" if unit_state == "active" else "fail"})
    else:
        results.append({"key": "unit", "expected": None, "measured": None, "state": "not_measured"})
    counts = {}
    for item in results:
        counts[item["state"]] = counts.get(item["state"], 0) + 1
    return {"checks": results, "counts": counts,
            "notice": "状态只描述本次实测项；未测量不等于通过，配置动作不等于生效。"}


def dispatch(args):
    item = target(args.host, args.user, args.port, args.identity)
    if args.action == "check":
        facts = check(item)
        result = {"remote": item["host"], "user": item["user"], "facts": facts,
                  "findings": findings(facts), "checked_at": now()}
    elif args.action == "align":
        facts = check(item)
        plan = align_plan(facts, args.timezone, args.locale)
        result = {"remote": item["host"], "plan": plan, "applied": False}
        if args.apply and plan:
            directory = create_run(args.out)
            write(directory / "before.private.json", facts)
            for step in plan:
                outcome = execute(item, "set -e\n" + step["command"])
                step["applied"] = outcome["state"] == "ok"
            write(directory / "alignment.private.json", result)
            result["directory"] = str(directory)
    elif args.action == "wrap":
        plan = wrap_plan(item, args.unit, args.command, args.run_user, args.workdir,
                         args.restart, args.memory_mb, args.cpu_percent, args.apply)
        result = plan
    elif args.action == "verify":
        facts = check(item)
        unit_state = None
        if args.unit:
            outcome = execute(item, "systemctl is-active " + _check(UNIT, args.unit, "unit 名称无效。"))
            unit_state = outcome["value"].strip() if outcome["state"] == "ok" else None
        result = {"remote": item["host"],
                  "verification": verify(facts, args.timezone, args.locale, args.unit, unit_state),
                  "facts": facts, "checked_at": now()}
    else:
        raise InputError("未知的远端动作。")
    if args.out:
        directory = create_run(args.out)
        write(directory / "remote.json", result)
        result["directory"] = str(directory)
    return result


def register(sub):
    p = sub.add_parser("remote", help="检查、对齐并包裹用户自己服务器上的长驻进程；默认只出计划")
    p.add_argument("action", choices=("check", "align", "wrap", "verify"))
    p.add_argument("--host", required=True, help="服务器地址")
    p.add_argument("--user", default="root", help="SSH 用户")
    p.add_argument("--port", type=int, default=22, help="SSH 端口")
    p.add_argument("--identity", help="私钥文件路径（权限需为 600）")
    p.add_argument("--timezone", help="目标时区，例如 Europe/Berlin")
    p.add_argument("--locale", help="目标 locale，例如 en_US.UTF-8")
    p.add_argument("--unit", help="systemd unit 名称")
    p.add_argument("--command", help="要长期运行的命令，由用户提供，不做改写")
    p.add_argument("--run-user", default="root", help="unit 运行用户")
    p.add_argument("--workdir", help="unit 工作目录")
    p.add_argument("--restart", type=int, default=10, help="重启间隔秒数")
    p.add_argument("--memory-mb", type=int, help="内存上限")
    p.add_argument("--cpu-percent", type=int, help="CPU 配额百分比")
    p.add_argument("--out")
    p.add_argument("--apply", action="store_true", help="真正执行；默认只输出计划")
