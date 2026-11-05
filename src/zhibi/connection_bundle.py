"""Export a private, standalone connection launcher and browser handoff."""
import os
from pathlib import Path
from importlib.resources import files
from .models import InputError
from .storage import create_run, write

LAUNCHER = r'''#!/usr/bin/env python3
"""Private connection launcher; requires Python 3 and the original SSH identity."""
import json
import os
import subprocess
import sys
from pathlib import Path

base = Path(__file__).resolve().parent
config = base / "connection.private.json"
if config.is_symlink() or (os.name == "posix" and config.stat().st_mode & 0o077):
    raise SystemExit("私人连接文件权限不正确。")
data = json.loads(config.read_text(encoding="utf-8"))
if "--check" in sys.argv[1:]:
    # Explicit check only: never query an external service merely by opening the folder.
    command = ["curl", "-q", "--fail", "--silent", "--show-error", "--max-time", "10",
               "--noproxy", "", "--proxy", "socks5h://127.0.0.1:" + str(data["local_port"]),
               "https://api.ipify.org?format=json"]
else:
    if data["interactive"] and not os.isatty(0):
        raise SystemExit("请在终端打开交互进程入口。")
    print("正在建立连接。此窗口需保持打开；请在浏览器复测后确认可用。按 Ctrl-C 停止。", flush=True)
    command = data["argv"]
try:
    raise SystemExit(foreground(command))
except KeyboardInterrupt:
    raise SystemExit(130)
'''


def export(args, command):
    if args.apply:
        raise InputError("导出连接与立即启动需分别执行。")
    directory = create_run(args.export_out)
    write(directory / "connection.private.json", {
        "format": "zhibi-connection-1", "argv": command,
        "local_port": args.local_port, "interactive": args.interactive,
        "identity_copied": False,
    })
    # Embed the tested stdlib helper, keeping the exported launcher self-contained.
    helper = files("zhibi").joinpath("lifecycle.py").read_text(encoding="utf-8")
    write(directory / "start.py", LAUNCHER.replace("base = Path", helper + "\nbase = Path", 1))
    write(directory / "browser.json", {"protocol": "socks5", "host": "127.0.0.1",
          "port": args.local_port, "username": "", "password": "", "remote_dns": True,
          "udp_supported": False, "verified": False})
    write(directory / "使用说明.md", """# 连接使用说明

此文件夹含私人启动命令，请留在本机，不要上传或分享。密钥没有复制，启动时仍需原密钥文件。

1. 在本机终端运行 `python3 start.py`（Windows 使用 `py -3 start.py`）。Agent 可以代为启动并保留终端。
2. 在想使用的浏览器里填写 SOCKS5、127.0.0.1、端口 PORT，用户名密码留空。具体界面按该浏览器版本选择。
3. 启用通过代理解析域名。SSH 不转发 UDP；单独配置并实测 WebRTC。HTTP-only 浏览器不能直接使用这个端口。
4. 在另一个终端运行 `python3 start.py --check`，允许经代理请求 ipify 取得出口；再在实际浏览器运行知彼探针，核对是否符合预期。账号由用户自己登录。
5. 停止前恢复浏览器原代理，再在启动窗口按 Ctrl-C。确认普通联网恢复。

多款支持 SOCKS5 的浏览器可共用这个端口，但必须分别验证。浏览器必须在运行此入口的机器上。
如果此连接同时运行远端命令，命令退出时隧道也会退出。需要浏览器长期独立连接时，请另行导出不带命令的连接。

这是启动入口和参数，不是已经连通的证明；保持终端与实际探针结果作为运行依据。
""".replace("PORT", str(args.local_port)))
    if os.name == "posix":
        (directory / "start.py").chmod(0o700)
    return {"directory": str(directory), "launcher": str(directory / "start.py"),
            "applied": False, "verified": False, "private": True}
