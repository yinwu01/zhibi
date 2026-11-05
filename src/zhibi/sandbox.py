"""Linux process workspace. Pure stdlib so the runner can be exported standalone."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import re
import shlex
import hashlib
import stat
import ipaddress


def checked_directory(value):
    path = Path(value).expanduser().absolute()
    if not path.is_dir() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("目录必须存在且不能经过符号链接。")
    return path


def proxy_files(binary, digest, endpoint):
    executable = Path(binary).expanduser().absolute()
    if (executable.is_symlink() or not executable.is_file()
            or not os.access(executable, os.X_OK)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or hashlib.sha256(executable.read_bytes()).hexdigest() != digest):
        raise ValueError("graftcp 可执行文件或 SHA256 校验不匹配。")
    sock = Path(endpoint).expanduser().absolute()
    parent = checked_directory(sock.parent)
    info = sock.lstat()
    if (not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid()
            or parent.stat().st_uid != os.getuid() or parent.stat().st_mode & 0o077):
        raise ValueError("代理必须是当前用户所有、位于私人目录内的 Unix SOCKS5 socket。")
    return str(executable), str(sock)


def prepare(out, workdir, timezone="Etc/UTC", locale="C.UTF-8", network="isolated", app_dir=None,
            graftcp=None, graftcp_sha256=None, proxy_socket=None, dns_server="1.1.1.1"):
    import re
    workspace = checked_directory(workdir)
    application = checked_directory(app_dir) if app_dir else None
    if not re.fullmatch(r"[A-Za-z0-9_+/-]{1,100}", timezone) or ".." in timezone:
        raise ValueError("时区格式无效。")
    if not re.fullmatch(r"[A-Za-z0-9_.@-]{1,60}", locale):
        raise ValueError("语言环境格式无效。")
    if network not in {"isolated", "host", "proxy"}:
        raise ValueError("网络模式无效。")
    proxy = None
    if network == "proxy":
        if not all((graftcp, graftcp_sha256, proxy_socket)):
            raise ValueError("代理模式需要 graftcp、SHA256 和私人 Unix socket。")
        binary, endpoint = proxy_files(graftcp, graftcp_sha256, proxy_socket)
        dns_server = str(ipaddress.IPv4Address(dns_server))
        proxy = {"binary": binary, "sha256": graftcp_sha256, "socket": endpoint, "dns": dns_server}
    elif any((graftcp, graftcp_sha256, proxy_socket)):
        raise ValueError("代理参数仅用于 proxy 网络模式。")
    directory = Path(out).expanduser().absolute()
    if any(p.is_symlink() for p in directory.parents):
        raise ValueError("输出目录不能经过符号链接。")
    directory.mkdir(mode=0o700, parents=False, exist_ok=False)
    (directory / "home").mkdir(mode=0o700)
    config = {"version": 1, "workdir": str(workspace), "timezone": timezone,
              "locale": locale, "network": network, "app_dir": str(application) if application else None}
    config["proxy"] = proxy
    if proxy:
        (directory / "resolv.conf").write_text("nameserver " + dns_server + "\noptions timeout:2 attempts:2\n")
        # graftcp completes the local connect before the remote proxy handshake.
        # Prefer IPv4 so IPv6-less VPS hosts do not fail later at TLS negotiation.
        (directory / "gai.conf").write_text("precedence ::ffff:0:0/96 100\n")
    path = directory / "profile.json"
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(config, handle, indent=2)
    # Copy our own source, not third-party implementations or user configuration.
    from importlib.resources import files
    runner = directory / "run.py"
    fd = os.open(str(runner), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o700)
    with os.fdopen(fd, "w") as handle:
        handle.write(files("zhibi").joinpath("sandbox.py").read_text(encoding="utf-8"))
    return {"directory": str(directory), "runner": str(runner), "network": network,
            "private_home": True, "environment_allowlist": ["HOME", "PATH", "LANG", "LC_ALL", "TZ", "TERM"]}


def command(directory, program):
    if not sys.platform.startswith("linux"):
        raise ValueError("进程沙箱需在 Linux 服务器运行。")
    bwrap = shutil.which("bwrap")
    if not bwrap:
        raise ValueError("缺少 bubblewrap，请先安装并验证用户命名空间可用。")
    root = checked_directory(directory)
    path = root / "profile.json"
    if path.is_symlink() or path.stat().st_mode & 0o077:
        raise ValueError("沙箱配置权限需为 600。")
    config = json.loads(path.read_text())
    if config.get("version") != 1 or config.get("network") not in {"isolated", "host", "proxy"}:
        raise ValueError("不支持的沙箱配置。")
    if not program or any(not isinstance(v, str) or "\0" in v for v in program):
        raise ValueError("请指定要运行的程序。")
    args = [bwrap, "--unshare-all", "--die-with-parent", "--new-session", "--clearenv", "--cap-drop", "ALL"]
    if config["network"] == "host":
        args += ["--share-net"]
    for name in ("/usr", "/bin", "/sbin", "/lib", "/lib64"):
        if os.path.islink(name):
            args += ["--symlink", os.readlink(name), name]
        elif os.path.isdir(name):
            args += ["--ro-bind", name, name]
    args += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--dir", "/etc"]
    for name in ("/etc/ld.so.cache", "/etc/ssl/certs", "/etc/pki", "/etc/resolv.conf", "/etc/hosts", "/etc/nsswitch.conf"):
        if os.path.exists(name):
            args += ["--ro-bind", os.path.realpath(name), name]
    args += ["--bind", str(checked_directory(root / "home")), "/home/app",
             "--bind", str(checked_directory(config["workdir"])), "/workspace", "--chdir", "/workspace"]
    if config.get("app_dir"):
        args += ["--ro-bind", str(checked_directory(config["app_dir"])), "/opt/app"]
    environment = {"HOME": "/home/app", "PATH": "/opt/app/bin:/opt/app:/usr/local/bin:/usr/bin:/bin",
                   "LANG": config["locale"], "LC_ALL": config["locale"], "TZ": config["timezone"], "TERM": "xterm-256color"}
    for key, value in environment.items():
        args += ["--setenv", key, value]
    if config["network"] == "proxy":
        proxy = config["proxy"]
        binary, endpoint = proxy_files(proxy["binary"], proxy["sha256"], proxy["socket"])
        ip = shutil.which("ip")
        setpriv = shutil.which("setpriv")
        if not ip or not setpriv:
            raise ValueError("代理网络初始化需要 iproute2 与 util-linux setpriv。")
        args += ["--uid", "0", "--gid", "0", "--cap-add", "CAP_NET_ADMIN",
                 "--cap-add", "CAP_SETPCAP", "--dir", "/run/zhibi",
                 "--ro-bind", binary, "/run/zhibi/graftcp",
                 "--ro-bind", endpoint, "/run/zhibi/proxy.sock",
                 "--ro-bind", str(root / "gai.conf"), "/etc/gai.conf",
                 "--ro-bind", str(root / "resolv.conf"), "/etc/resolv.conf"]
        # A route-less interface makes AI_ADDRCONFIG usable. Drop setup capabilities
        # before executing graftcp or any application; there is no external route.
        setup = (shlex.join([ip, "link", "add", "zhibi0", "type", "dummy"]) + "; "
                 + shlex.join([ip, "addr", "add", "192.0.2.1/32", "dev", "zhibi0"]) + "; "
                 + shlex.join([ip, "link", "set", "zhibi0", "up"]) + "; exec "
                 + shlex.join([setpriv, "--bounding-set=-all", "--inh-caps=-all", "--ambient-caps=-all",
                               "--no-new-privs", "/run/zhibi/graftcp", "--config", "/dev/null",
                               "--select_proxy_mode", "only_socks5", "--socks5", "unix:/run/zhibi/proxy.sock",
                               "--enable-dns", "--dns-server", str(ipaddress.IPv4Address(proxy["dns"])) + ":53",
                               "--disable-udp", "--"]) + ' "$@"')
        program = ["/bin/sh", "-ec", setup, "zhibi-proxy", *program]
    return args + ["--", *program]


def install_entry(directory, name, program):
    """Create an independent PATH entry; never replace an application's own files."""
    root = checked_directory(directory)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", name):
        raise ValueError("命令名称只能包含字母、数字、点、下划线和连字符。")
    executable = Path(program)
    if (not executable.is_absolute() or ".." in executable.parts
            or any(c in program for c in "\0\n\r")
            or not any(program.startswith(p) for p in ("/opt/app/", "/usr/", "/bin/", "/sbin/"))):
        raise ValueError("指定沙箱内的绝对程序路径，例如 /opt/app/bin/myapp。")
    runner = root / "run.py"
    if not runner.is_file() or runner.is_symlink():
        raise ValueError("缺少独立沙箱启动器。")
    bindir = root / "bin"
    bindir.mkdir(mode=0o700, exist_ok=True)
    checked_directory(bindir)
    entry = bindir / name
    # Literal argv, no shell evaluation of the application or forwarded arguments.
    source = ("#!/bin/sh\nexec " + shlex.join([sys.executable, str(runner), "--", program])
              + ' "$@"\n')
    fd = os.open(str(entry), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o700)
    with os.fdopen(fd, "w") as handle:
        handle.write(source)
    return {"entry": str(entry), "program": program,
            "activate": "export PATH=" + shlex.quote(str(bindir)) + ':"$PATH"; hash -r',
            "check": "command -v " + shlex.quote(name),
            "expected_entry": str(entry),
            "remove": "rm -- " + shlex.quote(str(entry)),
            "scope": "仅对 PATH 优先选择此入口的 shell 生效；别名、函数和绝对路径需另行核对。"}


def main():
    parser = argparse.ArgumentParser(description="运行专用 Linux 进程环境")
    parser.add_argument("program", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    program = args.program[1:] if args.program[:1] == ["--"] else args.program
    try:
        argv = command(Path(__file__).resolve().parent, program)
        os.execv(argv[0], argv)
    except (ValueError, OSError, KeyError, TypeError):
        print("沙箱启动失败；未回退到直接执行。请检查依赖、配置和目录权限。", file=sys.stderr)
        return 125


if __name__ == "__main__":
    raise SystemExit(main())
