"""Private, explicit project bindings; never execute configuration from a checkout."""
import hashlib
import json
import os
import shlex
import shutil
import stat
import tempfile
from pathlib import Path
from types import SimpleNamespace

from . import connect, remote
from .models import InputError


def project_path(value):
    path = Path(value).expanduser().resolve(strict=True)
    if not path.is_dir():
        raise InputError("项目必须是已存在的目录。")
    return path


def state_root(value=None):
    root = Path(value).expanduser() if value else Path.home() / ".zhibi" / "projects"
    if root.is_symlink():
        raise InputError("项目状态目录不能是符号链接。")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == "posix" and (root.stat().st_uid != os.getuid() or root.stat().st_mode & 0o077):
        raise InputError("项目状态目录必须由当前用户拥有，权限为 700。")
    return root


def location(args):
    project = project_path(args.project)
    key = hashlib.sha256(os.fsencode(str(project))).hexdigest()
    return project, state_root(args.state_dir) / key


def private_read(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "r", encoding="utf-8") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 131072:
            raise InputError("项目配置必须是小于 128 KiB 的普通文件。")
        if os.name == "posix" and (info.st_uid != os.getuid() or info.st_mode & 0o077):
            raise InputError("项目配置必须由当前用户拥有，权限为 600。")
        return stream.read()


def save(path, text):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as stream:
        stream.write(text)


def bind(args):
    project, folder = location(args)
    if folder.exists() or folder.is_symlink():
        raise InputError("项目已有绑定；先检查 status，需要更换时显式 unbind。")
    backend = getattr(args, "backend", "remote")
    extra = {}
    if backend == "pvm":
        from . import pvm_backend
        vm_folder, vm_data = pvm_backend.load(args.vm_workspace)
        if Path(vm_data["project"]).resolve() != project:
            raise InputError("VM 共享项目与本次绑定项目不一致。")
        extra["vm_workspace"] = str(vm_folder)
        item, workdir = None, vm_data["guest_workdir"]
    else:
        item = remote.target(args.host, args.user, args.port, args.identity, getattr(args, "ssh_config", None))
        if item["identity"]:
            item["identity"] = str(Path(item["identity"]).resolve())
        if not args.workdir or not args.workdir.startswith("/") or "\0" in args.workdir:
            raise InputError("远端工作目录必须是绝对路径。")
        workdir = args.workdir
    if not 1024 <= args.local_port <= 65535:
        raise InputError("本机端口需在 1024–65535。")
    scripts = {"start": connect.command_text(args.command_file)}
    if args.resume_file:
        scripts["resume"] = connect.command_text(args.resume_file)
    probe_prefix = []
    if getattr(args, "probe_prefix_file", None):
        probe_prefix = json.loads(private_read(Path(args.probe_prefix_file).expanduser()))
        if not isinstance(probe_prefix, list) or not probe_prefix or len(probe_prefix) > 32 or any(not isinstance(x, str) or not x or "\0" in x for x in probe_prefix):
            raise InputError("探针入口必须是非空 argv JSON 数组，不是 shell 字符串。")
    data = {"version": 1, "backend": backend, "project": str(project), **extra,
            "target": item, "workdir": workdir, "local_port": args.local_port,
            "interactive": args.interactive,
            "probe_prefix": probe_prefix,
            "scripts": {name: hashlib.sha256(text.encode()).hexdigest() for name, text in scripts.items()}}
    staging = Path(tempfile.mkdtemp(prefix=".bind-", dir=folder.parent))
    claimed = False
    try:
        for name, text in scripts.items():
            save(staging / (name + ".sh"), text)
        save(staging / "binding.private.json", json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        # mkdir acts as an exclusive claim; do not overwrite a concurrent binding.
        folder.mkdir(mode=0o700)
        claimed = True
        for path in staging.iterdir():
            path.rename(folder / path.name)
    except BaseException:
        if claimed:
            shutil.rmtree(folder)
        raise
    finally:
        shutil.rmtree(staging)
    return {"action": "bind", "backend": backend, "project": str(project), "saved": True}


def load(args):
    project, folder = location(args)
    if folder.is_symlink():
        raise InputError("项目绑定目录不能是符号链接。")
    if os.name == "posix" and (folder.stat().st_uid != os.getuid() or folder.stat().st_mode & 0o077):
        raise InputError("项目绑定目录必须由当前用户拥有，权限为 700。")
    data = json.loads(private_read(folder / "binding.private.json"))
    if data.get("version") != 1 or data.get("project") != str(project) or data.get("backend") not in ("remote", "pvm"):
        raise InputError("项目绑定版本或路径不匹配。")
    for name, digest in data["scripts"].items():
        if name not in ("start", "resume"):
            raise InputError("项目启动类型无效。")
        if hashlib.sha256(private_read(folder / (name + ".sh")).encode()).hexdigest() != digest:
            raise InputError("保存的启动脚本已改变，请核对后重新绑定。")
    if "start" not in data["scripts"]:
        raise InputError("项目缺少启动脚本。")
    return data, folder


def run(args):
    if args.action == "bind":
        return bind(args)
    data, folder = load(args)
    if args.action == "audit":
        from .project_audit import audit
        return audit(args, data)
    if args.action in ("upload", "download"):
        if data["backend"] == "pvm":
            raise InputError("本地 VM 共享当前项目，无需传输。请将文件保存到项目中，VM 内路径为 /workspace。")
        from .project_files import transfer
        return transfer(args, data)
    info = {"backend": data["backend"], "project": data["project"],
            "host": data["target"]["host"] if data["target"] else "local-vm", "workdir": data["workdir"],
            "resume_configured": "resume" in data["scripts"],
            "live_checked": False, "browser_proxy_port": data["local_port"] if data["target"] else None}
    if args.action == "status":
        if args.network and not args.live:
            raise InputError("--network 需要同时指定 --live。")
        if args.live:
            if data["backend"] == "pvm":
                from . import pvm_backend
                info["facts"] = pvm_backend.dispatch(SimpleNamespace(action="status", workspace=data["vm_workspace"], live=True))
                if args.network:
                    info["audit"] = pvm_backend.dispatch(SimpleNamespace(action="audit", workspace=data["vm_workspace"], network=True))
            else:
                info["facts"] = remote.check(remote.target(**data["target"]), egress=args.network)
            info["live_checked"] = True
        return info
    if args.action == "unbind":
        if args.apply:
            # Only remove known owned files. Unexpected files cause failure, not deletion.
            expected = {"binding.private.json"} | {name + ".sh" for name in data["scripts"]}
            if {p.name for p in folder.iterdir()} != expected:
                raise InputError("绑定目录包含额外文件，请先检查；未删除。")
            for name in expected:
                (folder / name).unlink()
            folder.rmdir()
        return {"action": "unbind", "applied": args.apply, "remote_unchanged": True}
    name = "resume" if args.action == "resume" else "start"
    if name not in data["scripts"]:
        raise InputError("该项目未配置应用恢复命令；恢复会话不等于后台任务继续运行。")
    if data["backend"] == "pvm":
        from . import pvm_backend
        return pvm_backend.run_application(data["vm_workspace"], private_read(folder / (name + ".sh")),
                                           data["interactive"], args.apply)
    options = SimpleNamespace(**data["target"], local_port=data["local_port"],
                              command_file=str(folder / (name + ".sh")),
                              workdir=data["workdir"], interactive=data["interactive"],
                              apply=args.apply, export_out=None)
    if args.apply:
        # Fail before launching the application if its project is missing or unreadable.
        script = "test -d " + shlex.quote(data["workdir"]) + " && test -r " + shlex.quote(data["workdir"])
        if remote.execute(remote.target(**data["target"]), script)["state"] != "ok":
            raise InputError("远端项目目录不可访问；未启动应用。")
    result = connect.run(options)
    result["project"] = info
    return result


def register(sub):
    p = sub.add_parser("project", help="保存私人项目绑定，启动/恢复远端应用并检查状态")
    actions = p.add_subparsers(dest="action", required=True)
    for action in ("bind", "start", "resume", "status", "unbind", "upload", "download", "audit"):
        child = actions.add_parser(action)
        child.add_argument("--project", default=".")
        child.add_argument("--state-dir", help="私人状态目录；默认 ~/.zhibi/projects")
        if action == "bind":
            child.add_argument("--backend", choices=("remote", "pvm"), default="remote")
            child.add_argument("--vm-workspace")
            child.add_argument("--host")
            child.add_argument("--user", default="root")
            child.add_argument("--port", type=int, default=22)
            child.add_argument("--identity")
            child.add_argument("--ssh-config", help="显式私人 SSH 配置；支持用户指定的跳板/代理")
            child.add_argument("--workdir")
            child.add_argument("--command-file", required=True)
            child.add_argument("--resume-file")
            child.add_argument("--probe-prefix-file", help="私人 JSON argv 数组，指定应用探针运行入口，如 bwrap run.py --")
            child.add_argument("--local-port", type=int, default=10818)
            child.add_argument("--interactive", action="store_true")
        elif action == "audit":
            child.add_argument("--network", action="store_true")
            child.add_argument("--expected-ip")
            child.add_argument("--browser", help="实际浏览器探针 JSON")
            child.add_argument("--disconnect-file", help="私人本机控制脚本：仅断开本次测试出口")
            child.add_argument("--reconnect-file", help="私人本机恢复脚本：finally 中执行")
            child.add_argument("--out", help="新的私人 JSON 报告文件")
        elif action == "status":
            child.add_argument("--live", action="store_true")
            child.add_argument("--network", action="store_true", help="配合 --live 测远端出口")
        else:
            child.add_argument("--apply", action="store_true")
            if action in ("upload", "download"):
                child.add_argument("--local", required=True, help="本机单个文件；下载目标必须不存在")
                child.add_argument("--remote-file", required=True, help="远端项目内相对路径；上传目标必须不存在")
