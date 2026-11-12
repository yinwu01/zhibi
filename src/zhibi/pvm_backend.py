"""External PVM CLI adapter. No upstream source or binary is bundled."""
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .models import InputError
from .lifecycle import foreground

VERSION = "v1.1.6"
NAME = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,47}\Z")
REQUIRED = ("vm", "route", "tcp", "udp", "icmp", "dns", "ipv6", "timezone", "locale")


def validate_name(value):
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise InputError("VM 或出口名称只能使用字母、数字、下划线和连字符，最长 48 字符。")
    return value


def environment(data):
    return dict(os.environ, PVM_HOME=data["pvm_home"])


def command(data, *parts):
    return [data["binary"], *parts]


def call(data, *parts, timeout=60):
    try:
        return subprocess.run(command(data, *parts), env=environment(data),
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise InputError("PVM 操作等待超时；先检查实际 VM 状态，不要重复创建。") from exc


def check_version(data):
    result = call(data, "version")
    if result.returncode or result.stdout.strip() != VERSION:
        raise InputError("当前适配器需要 PVM v1.1.6；请安装已校验的对应版本。")


def write_state(folder, data):
    fd, temporary = tempfile.mkstemp(prefix=".state-", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, folder / "vm.private.json")
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load(workspace):
    from .project import private_read
    folder = Path(workspace).expanduser().absolute()
    if folder.is_symlink() or not folder.is_dir():
        raise InputError("VM 工作区必须是已有的普通目录。")
    if os.name == "posix" and (folder.stat().st_uid != os.getuid() or folder.stat().st_mode & 0o077):
        raise InputError("VM 工作区必须由当前用户拥有，权限为 700。")
    data = json.loads(private_read(folder / "vm.private.json"))
    if data.get("version") != 1:
        raise InputError("VM 工作区版本不支持。")
    validate_name(data["name"])
    validate_name(data["exit"])
    if not Path(data["binary"]).is_absolute() or not Path(data["pvm_home"]).is_absolute():
        raise InputError("PVM 程序和状态目录必须是绝对路径。")
    return folder, data


def resources(path):
    system, arch = platform.system(), platform.machine()
    memory = None
    try:
        if system == "Darwin":
            memory = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], timeout=5))
        elif system == "Linux":
            memory = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return {"system": system, "architecture": arch, "cpus": os.cpu_count(),
            "memory_gib": round(memory / 2**30, 1) if memory else None,
            "free_disk_gib": round(shutil.disk_usage(path).free / 2**30, 1),
            "supported_host": (system, arch) in (("Darwin", "arm64"), ("Linux", "x86_64")),
            "notice": "此适配器首版支持 macOS arm64 / Linux amd64；镜像与桌面占用额外磁盘。"}


def prepare(args):
    from .project import project_path
    folder = Path(args.workspace).expanduser().absolute()
    project = project_path(args.project)
    if ":" in str(project):
        raise InputError("PVM 共享路径不能包含冒号。")
    binary = shutil.which(args.pvm_binary)
    if not binary:
        raise InputError("未找到 PVM；按本地 VM 参考安装并验证 v1.1.6。")
    binary = str(Path(binary).resolve())
    data = {"version": 1, "name": validate_name(args.name), "exit": validate_name(args.exit),
            "binary": binary, "pvm_home": str(Path(args.pvm_home).expanduser().absolute()),
            "project": str(project), "guest_workdir": "/workspace", "phase": "prepared",
            "image": args.image, "user": args.user, "cpus": args.cpus, "memory_mb": args.memory,
            "disk_gb": args.disk, "timezone": args.timezone, "locale": args.locale, "completed": []}
    if folder.resolve().is_relative_to(project) or Path(data["pvm_home"]).resolve().is_relative_to(project):
        raise InputError("VM 工作区和 PVM_HOME 必须放在共享项目之外，避免暴露凭据和虚拟磁盘。")
    # macOS Unix sockets permit 103 path bytes. Golden-build names are longer
    # than user VM names, so reject before downloading a large base image.
    if platform.system() == "Darwin" and len(os.fsencode(data["pvm_home"] + "/vms/bake-ubuntu-2404-xxxxxxxxxxxx/qmp.sock")) > 103:
        raise InputError("PVM_HOME 太长，超过 macOS Unix socket 路径限制；请选择较短的私人目录。")
    from .remote import USER, TZONE
    if not USER.fullmatch(args.user) or not TZONE.fullmatch(args.timezone) or not re.fullmatch(r"[A-Za-z0-9_.@-]{1,64}", args.locale):
        raise InputError("用户、时区或 locale 参数无效。")
    if args.image not in ("ubuntu:24.04", "ubuntu:26.04", "debian:12", "debian:13"):
        raise InputError("请选择支持的 Linux 镜像。")
    if not 1 <= args.cpus <= 64 or not 1024 <= args.memory <= 131072 or not 8 <= args.disk <= 512:
        raise InputError("VM 资源配置不在支持范围内。")
    info = resources(project)
    if not info["supported_host"]:
        raise InputError("当前适配器尚未支持该宿主平台。")
    if info["free_disk_gib"] < 8:
        raise InputError("可用磁盘不足 8 GiB，尚未创建 VM。")
    if info["memory_gib"] and args.memory / 1024 + 2 > info["memory_gib"]:
        raise InputError("VM 内存超过可用硬件预算；至少为宿主和网关保留 2 GiB。")
    check_version(data)
    if folder.exists() or folder.is_symlink():
        raise InputError("VM 工作区必须使用新目录。")
    folder.mkdir(mode=0o700, parents=True)
    write_state(folder, data)
    return {"workspace": str(folder), "prepared": True, "created": False, "resources": info,
            "exit": data["exit"], "direct": data["exit"] == "direct", "steps": provision_steps(data)}


def ipv6_expression(apply=False):
    from importlib.resources import files
    source = files("zhibi").joinpath("guest_ipv6.py").read_text(encoding="utf-8")
    return ("sudo -n " if apply else "") + "python3 -c " + shlex.quote(source) + (" --apply" if apply else "")


def ipv6_policy(data, apply=False):
    result = call(data, "ssh", "-T", data["name"], ipv6_expression(apply))
    try:
        report = json.loads(result.stdout)
    except (ValueError, TypeError):
        raise InputError("无法核验 VM 的 IPv6 禁用状态；未启动应用或桌面。")
    if result.returncode or not isinstance(report, dict) or report.get("state") != "ok":
        raise InputError("VM IPv6 未成功禁用；未启动应用或桌面。")
    return report


def provision_steps(data):
    return [
        ["create", "--image", data["image"], "--name", data["name"], "--user", data["user"],
         "--cpus", str(data["cpus"]), "--mem", str(data["memory_mb"]), "--disk", str(data["disk_gb"]),
         "--tz", data["timezone"], "--locale", data["locale"], "--share", "none", "--no-start"],
        ["start", data["name"]],
        ["route", data["name"], "--via", data["exit"]],
        ["ssh", "-T", data["name"], ipv6_expression(True)],
        ["mount", data["name"], "--profile", "coherent", data["project"] + ":/workspace"],
    ]


def provision(folder, data, apply):
    steps = provision_steps(data)
    if not apply:
        return {"applied": False, "steps": steps, "phase": data["phase"]}
    check_version(data)
    if data["phase"] != "prepared":
        raise InputError("工作区已执行或中断；先检查 VM 与私人日志，不自动重复创建或删除。")
    listing = call(data, "ls")
    if listing.returncode:
        raise InputError("无法读取 PVM 实例列表；未执行创建。")
    if any(line.split()[:1] == [data["name"]] for line in listing.stdout.splitlines()):
        raise InputError("已有同名 VM；未修改。请选择新的名称和工作区。")
    data["phase"] = "provisioning"
    write_state(folder, data)
    for step in steps:
        data["current_step"] = step[0]
        write_state(folder, data)
        print("PVM: " + step[0] + "（进度写入工作区私人日志）", file=sys.stderr, flush=True)
        # Progress belongs on the terminal; persist detailed output privately.
        log = folder / (step[0] + ".private.log")
        try:
            with os.fdopen(os.open(log, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
                done = subprocess.run(command(data, *step), env=environment(data),
                                      stdout=stream, stderr=subprocess.STDOUT, timeout=3600)
            if done.returncode:
                raise InputError("PVM 配置步骤失败；已保存阶段与私人日志，现有实例未删除。")
        except BaseException as exc:
            data["phase"] = "interrupted"
            write_state(folder, data)
            if isinstance(exc, subprocess.TimeoutExpired):
                raise InputError("PVM 配置超时；已保存阶段，先检查现有实例再恢复。") from exc
            raise
        data["completed"].append(step[0])
        write_state(folder, data)
    data["phase"] = "ready"
    data["current_step"] = None
    write_state(folder, data)
    return {"applied": True, "ready": True, "name": data["name"], "exit": data["exit"],
            "network_verified": False, "project": data["project"], "guest_workdir": "/workspace"}


def parse_audit(text, expected_exit):
    checks = {}
    for line in text.splitlines():
        match = re.fullmatch(r"([a-z0-9_]+)=(ok|fail|warn|skipped): (.*)", line)
        if match:
            key, state, detail = match.groups()
            if key in checks:
                raise InputError("PVM audit 返回重复项目，不能确认结果。")
            checks[key] = {"state": state, "detail": detail}
    for key in REQUIRED:
        checks.setdefault(key, {"state": "not_measured", "detail": "PVM 未返回该项"})
    route = checks["route"]
    if route["state"] == "ok" and not re.match(r"via " + re.escape(expected_exit) + r"(?: |$)", route["detail"]):
        route["state"] = "fail"
        route["detail"] = "实际路由与配置出口不符"
    return {"checks": checks, "protocol_checks_passed": all(v["state"] == "ok" for v in checks.values()),
            "complete": False, "remaining": ["browser", "exit IP", "tunnel-loss-and-recovery"],
            "notice": "协议检查不能替代实际浏览器、出口地址和断网恢复验收。"}


def effective_route(text, name):
    default = None
    specific = None
    for line in text.splitlines():
        fields = line.split()
        if len(fields) == 4 and fields[:2] == ["vm", name]:
            specific = fields[3]
        elif len(fields) == 4 and fields[:3] == ["cluster-default", "*", "route"]:
            default = fields[3]
    return specific or default


def guest_command(data, text, interactive=False):
    # PVM joins command argv into a shell expression; pass one explicitly quoted expression.
    return command(data, "ssh", "-t" if interactive else "-T", data["name"],
                   "sh -lc " + shlex.quote(text))


def run_application(workspace, text, interactive, apply):
    _, data = load(workspace)
    info = {"backend": "pvm", "name": data["name"], "exit": data["exit"], "applied": False,
            "guest_workdir": data["guest_workdir"], "shared_project": data["project"]}
    if not apply:
        return info
    if interactive and not os.isatty(0):
        raise InputError("交互式应用需要 PTY。")
    check_version(data)
    if data["phase"] != "ready":
        raise InputError("VM 工作区尚未完成配置。")
    started = call(data, "start", data["name"], timeout=300)
    if started.returncode:
        raise InputError("VM 未能启动；未启动应用。")
    routes = call(data, "route", "ls")
    if routes.returncode or effective_route(routes.stdout, data["name"]) != data["exit"]:
        raise InputError("VM 实际路由与绑定不符或无法确认；未启动应用。")
    ipv6_policy(data, apply=True)
    expression = "cd -- " + shlex.quote(data["guest_workdir"]) + " || exit\n" + text
    status = foreground(guest_command(data, expression, interactive), env=environment(data))
    info.update(applied=True, exit_status=status)
    return info


def reconcile(folder, data, apply):
    """Read back a manually repaired deployment before accepting it as ready."""
    check_version(data)
    listing = call(data, "ls")
    rows = [line.split() for line in listing.stdout.splitlines() if line.split()[:1] == [data["name"]]]
    if listing.returncode or len(rows) != 1 or len(rows[0]) < 8:
        raise InputError("无法确认待恢复 VM 的身份与状态。")
    row = rows[0]
    if row[1] != data["image"] or row[2] != "user" or row[3] != "running" or row[7] != data["user"]:
        raise InputError("VM 镜像、角色、用户或运行状态与计划不符。")
    mounts = call(data, "mount", "ls", data["name"])
    # Split from the right because host project paths may contain spaces.
    mounted = [line.rsplit(None, 3) for line in mounts.stdout.splitlines()[1:] if line.strip()]
    expected = [data["project"], "/workspace", "coherent", "rw"]
    if mounts.returncode or mounted != [expected]:
        raise InputError("共享目录与计划不一致或存在额外挂载，不能确认恢复。")
    routes = call(data, "route", "ls")
    if routes.returncode or effective_route(routes.stdout, data["name"]) != data["exit"]:
        raise InputError("VM 出口与计划不一致，不能确认恢复。")
    check = subprocess.run(guest_command(data, "test -d /workspace && test -r /workspace && test -w /workspace"),
                           env=environment(data), capture_output=True, timeout=30)
    if check.returncode:
        raise InputError("VM 内共享目录不可用。")
    ipv6_policy(data, apply=apply)
    if apply:
        data.update(phase="ready", current_step=None, completed=[step[0] for step in provision_steps(data)])
        write_state(folder, data)
    return {"reconciled": True, "applied": apply, "network_verified": False}


def dispatch(args):
    if args.action == "prepare":
        return prepare(args)
    folder, data = load(args.workspace)
    if args.action == "provision":
        if not args.apply:
            return provision(folder, data, False)
        import fcntl
        fd = os.open(folder / ".provision.lock", os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "w") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise InputError("该工作区正在配置，请观察当前进程与日志。") from exc
            _, data = load(args.workspace)
            return provision(folder, data, True)
    if args.action == "reconcile":
        return reconcile(folder, data, args.apply)
    if args.action == "status":
        result = {"name": data["name"], "phase": data["phase"], "exit": data["exit"],
                  "project": data["project"], "completed": data["completed"],
                  "current_step": data.get("current_step"), "live_checked": False}
        if args.live:
            check_version(data)
            listing = call(data, "ls")
            if listing.returncode:
                raise InputError("PVM 实际状态读取失败。")
            rows = [line for line in listing.stdout.splitlines() if line.split()[:1] == [data["name"]]]
            result.update(live_checked=True, instance=rows[0] if rows else "missing")
        return result
    if args.action == "audit":
        if not args.network:
            return {"attempted": False, "notice": "--network 允许 PVM 从 VM 发起协议探测。"}
        check_version(data)
        audit = call(data, "audit", data["name"], timeout=180)
        report = parse_audit(audit.stdout, data["exit"])
        routes = call(data, "route", "ls")
        report["checks"]["ipv6_upstream"] = report["checks"]["ipv6"]
        try:
            report["checks"]["ipv6"] = ipv6_policy(data)
        except InputError as exc:
            report["checks"]["ipv6"] = {"state": "fail", "detail": str(exc)}
        report["protocol_checks_passed"] = all(report["checks"][key]["state"] == "ok" for key in REQUIRED)
        report.update(upstream_exit_status=audit.returncode, rules=routes.stdout if not routes.returncode else None)
        if audit.returncode or routes.returncode:
            report["protocol_checks_passed"] = False
        return report
    parts = [args.action, data["name"]]
    if args.action == "desktop":
        parts.append("--open")
    if not args.apply:
        return {"applied": False, "command": parts}
    check_version(data)
    if data["phase"] != "ready":
        raise InputError("VM 工作区尚未完成配置。")
    if args.action == "desktop":
        started = call(data, "start", data["name"], timeout=300)
        if started.returncode:
            raise InputError("VM 未能启动；未打开桌面。")
        ipv6_policy(data, apply=True)
        # URL contains a password. PVM opens it locally; do not echo it in JSON.
        result = call(data, *parts, timeout=180)
    else:
        result = call(data, *parts, timeout=300)
    if result.returncode:
        raise InputError("PVM 操作失败，请检查 VM 状态。")
    if args.action == "start":
        ipv6_policy(data, apply=True)
    return {"applied": True, "action": args.action, "name": data["name"]}


def register(sub):
    parser = sub.add_parser("vm", help="PVM 本地 Linux 环境：准备、创建、桌面、启停与协议检查")
    actions = parser.add_subparsers(dest="action", required=True)
    for action in ("prepare", "provision", "reconcile", "status", "start", "stop", "desktop", "audit"):
        p = actions.add_parser(action)
        p.add_argument("--workspace", required=True)
        if action == "prepare":
            p.add_argument("--project", default=".")
            p.add_argument("--name", required=True)
            p.add_argument("--exit", required=True, help="已注册 PVM 出口名称；direct 明确使用宿主出口")
            p.add_argument("--pvm-binary", default="pvm")
            p.add_argument("--pvm-home", default="~/.pvm")
            p.add_argument("--image", default="ubuntu:24.04")
            p.add_argument("--user", default="dev")
            p.add_argument("--cpus", type=int, default=2)
            p.add_argument("--memory", type=int, default=4096)
            p.add_argument("--disk", type=int, default=20)
            p.add_argument("--timezone", default="Etc/UTC")
            p.add_argument("--locale", default="en_US.UTF-8")
        elif action == "status":
            p.add_argument("--live", action="store_true")
        elif action == "audit":
            p.add_argument("--network", action="store_true")
        else:
            p.add_argument("--apply", action="store_true")
