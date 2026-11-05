"""Create a dedicated Chromium workspace with explicit permission minimization."""
import os
from importlib.resources import files
from pathlib import Path
from .models import InputError
from .storage import create_run, write

BLOCKED = ("geolocation", "media_stream_mic", "media_stream_camera", "notifications")


def create(args):
    binary = Path(args.browser_binary).expanduser().absolute()
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise InputError("请选择已安装且可执行的 Chromium 浏览器程序。")
    if not 1024 <= args.local_port <= 65535:
        raise InputError("代理端口需在 1024–65535。")
    directory = create_run(args.out)
    profile = directory / "profile" / "Default"
    profile.mkdir(parents=True, mode=0o700)
    prefs = {"profile": {"default_content_setting_values": {name: 2 for name in BLOCKED}}}
    write(profile / "Preferences", prefs)
    flags = ["--no-first-run", "--disable-extensions", "--disable-sync",
             "--proxy-server=socks5://127.0.0.1:" + str(args.local_port),
             "--force-webrtc-ip-handling-policy=disable_non_proxied_udp"]
    write(directory / "browser.private.json", {"binary": str(binary), "flags": flags})
    helper = files("zhibi").joinpath("lifecycle.py").read_text(encoding="utf-8")
    launcher = '''#!/usr/bin/env python3
import json
import os
from pathlib import Path
''' + helper + '''
base = Path(__file__).resolve().parent
config = base / "browser.private.json"
if config.is_symlink() or (os.name == "posix" and config.stat().st_mode & 0o077):
    raise SystemExit("浏览器配置权限不正确。")
data = json.loads(config.read_text(encoding="utf-8"))
command = [data["binary"], "--user-data-dir=" + str(base / "profile")] + data["flags"] + ["about:blank"]
raise SystemExit(foreground(command))
'''
    write(directory / "start-browser.py", launcher)
    write(directory / "controls.json", {"format": "zhibi-browser-controls-1", "fresh_profile": True,
          "blocked_permissions": list(BLOCKED), "extensions": "disabled", "sync": "disabled",
          "webrtc_policy": "disable_non_proxied_udp", "proxy": "socks5_loopback",
          "runtime_verified": False})
    write(directory / "使用说明.md", """# 专用浏览器环境

先启动对应端口的 VPS 连接，再运行 `python3 start-browser.py`（Windows 用 `py -3`）。
这个目录不复制已有浏览器历史、Cookie、扩展或同步账号。允许正常网页与账号登录，默认关闭位置、摄像头、麦克风和通知权限；关闭扩展和同步，要求 WebRTC 不走非代理 UDP。

使用视频通话、上传录音或定位等功能前，在此专用浏览器的站点设置中按需允许，并重新检查网络路径。不要修改日常浏览器配置。停止时正常关闭这个专用窗口；恢复日常使用只需回到原浏览器。

Chromium 衍生浏览器需要核验启动参数是否被接受。浏览器指纹软件已有专用配置管理器时，优先在其配置界面设置同等控制，不直接写其内部配置文件。

运行后用知彼 session 在此浏览器采集出口和所选检查。controls.json 记录创建时设置，不会把设置成功冒充运行验证。
""")
    if os.name == "posix":
        (directory / "start-browser.py").chmod(0o700)
    return {"directory": str(directory), "launcher": str(directory / "start-browser.py"),
            "controls": list(BLOCKED), "created": True, "runtime_verified": False}


def register(sub):
    p = sub.add_parser("browser-workspace", help="创建专用 Chromium 环境，限制无关权限、扩展与同步")
    p.add_argument("--browser-binary", required=True, help="用户选定的 Chromium 可执行文件")
    p.add_argument("--local-port", type=int, default=10818)
    p.add_argument("--out", required=True, help="新建私人目录，不修改现有浏览器配置")
