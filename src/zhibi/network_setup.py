"""Deliver private client configurations from a user's existing proxy; no resource purchases."""
import ipaddress
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from .diagnostics import private_config, route
from .models import InputError
from .storage import create_run, write


def proxy_config(config):
    if set(config) - {"type", "server", "port", "username", "password", "local_port", "expected_ip"}:
        raise InputError("代理交付配置有未知字段。")
    kind, server, port = config.get("type"), config.get("server"), config.get("port")
    if kind not in {"socks5", "http"} or type(port) is not int or not 1 <= port <= 65535:
        raise InputError("支持已有 SOCKS5/HTTP 代理及有效端口。")
    if not isinstance(server, str) or not re.fullmatch(r"[a-zA-Z0-9.:-]{1,253}", server):
        raise InputError("代理地址格式无效。")
    for key in ("username", "password"):
        value = config.get(key)
        if value is not None and (not isinstance(value, str) or len(value) > 4096 or any(ord(c) < 32 for c in value)):
            raise InputError("代理认证字段无效。")
    if bool(config.get("username")) != bool(config.get("password")):
        raise InputError("代理用户名与密码需同时提供或同时省略。")
    local = config.get("local_port", 10818)
    if type(local) is not int or not 1024 <= local <= 65535:
        raise InputError("本地端口需在 1024–65535。")
    return kind, server, port, local


def deliver(config_path, out):
    config = private_config(config_path)
    kind, server, port, local = proxy_config(config)
    if config.get("expected_ip"):
        from .intelligence import public_ip
        public_ip(config["expected_ip"])
    proxy = {"name": "Zhibi", "type": kind, "server": server, "port": port}
    if config.get("username"):
        proxy.update(username=config["username"], password=config["password"])
    # JSON is valid YAML. Use a dedicated Mihomo instance; never overwrite a user's global config.
    mihomo = {"mixed-port": local, "allow-lan": False, "bind-address": "127.0.0.1", "mode": "rule", "ipv6": False,
              "log-level": "warning", "proxies": [proxy], "rules": ["MATCH,Zhibi"],
              "tun": {"enable": False, "auto-route": False, "strict-route": True},
              "dns": {"enable": True, "listen": "127.0.0.1:15353", "ipv6": False, "enhanced-mode": "fake-ip", "fake-ip-range": "198.18.0.1/16", "respect-rules": True,
                      "default-nameserver": ["1.1.1.1"], "proxy-server-nameserver": ["1.1.1.1"], "nameserver": ["https://1.1.1.1/dns-query#Zhibi"]}}
    ads = {"proxy_soft": "other", "proxy_type": kind, "proxy_host": "127.0.0.1", "proxy_port": str(local), "proxy_user": "", "proxy_password": ""}
    directory = create_run(out)
    write(directory / "mihomo.private.json", mihomo)
    write(directory / "adspower-proxy.private.json", ads)
    verify = {"route": {"proxy_url": "socks5h://127.0.0.1:" + str(local)}}
    if config.get("expected_ip"):
        verify["expected_ip"] = config["expected_ip"]
        verify["route"]["expected_ip"] = config["expected_ip"]
    write(directory / "suite.private.json", verify)
    write(directory / "README.txt", "这是专用客户端配置，不是已经生效的网络。\n1. 使用已安装的 Mihomo 在自己的终端运行 mihomo -t -f mihomo.private.json 检查语法。\n2. 确认端口空闲后，单独运行 mihomo -f mihomo.private.json；本配置未开启 TUN、系统代理或局域网访问。\n3. 在专用浏览器设置 SOCKS5 127.0.0.1:" + str(local) + "。\n4. 用知彼 session 在该浏览器重新测 IPv4、IPv6、WebRTC 和可选 DNS。\n回退：恢复浏览器原代理，退出该 Mihomo 实例。不要把包含上游密码的配置上传到网站。\nDNS 引导只用于解析上游代理域名；普通域名使用所选代理中的 DoH。代理服务的 UDP 能力必须另行实测。\n")
    return {"directory": str(directory), "configurations": ["mihomo.private.json", "adspower-proxy.private.json", "suite.private.json"], "credentials_stored_locally": True,
            "deployed": False, "requires": ["existing_proxy", "mihomo"], "cost": "existing_proxy_plan", "system_modified": False}


def ssh_tunnel(config_path, apply=False):
    config = private_config(config_path)
    if set(config) - {"host", "user", "port", "identity_file", "known_hosts", "local_port"}:
        raise InputError("SSH 配置有未知字段。")
    host, user = config.get("host", ""), config.get("user", "")
    if not re.fullmatch(r"[a-zA-Z0-9.:-]{1,253}", host) or not re.fullmatch(r"[a-zA-Z0-9_][a-zA-Z0-9_-]{0,63}", user):
        raise InputError("SSH 主机或用户名无效。")
    port, local = config.get("port", 22), config.get("local_port", 10818)
    if type(port) is not int or not 1 <= port <= 65535 or type(local) is not int or not 1024 <= local <= 65535:
        raise InputError("SSH 端口无效。")
    paths = []
    for key in ("identity_file", "known_hosts"):
        path = Path(config.get(key, "")).expanduser().absolute()
        if path.is_symlink() or not path.is_file():
            raise InputError("需要已有的 SSH 私钥和经过核对的 known_hosts 文件。")
        if key == "identity_file" and os.name == "posix" and path.stat().st_mode & 0o077:
            raise InputError("SSH 私钥权限需为 600。")
        paths.append(str(path))
    args = ["ssh", "-F", "NUL" if os.name == "nt" else "/dev/null", "-N", "-D", "127.0.0.1:" + str(local), "-p", str(port),
            "-i", paths[0], "-o", "UserKnownHostsFile=" + paths[1], "-o", "StrictHostKeyChecking=yes", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
            "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=3", "-o", "ConnectTimeout=8", user + "@" + host]
    if not apply:
        return {"action": "foreground_ssh_socks", "local_port": local, "remote_host": host, "remote_commands": False, "requires_known_host": True, "applied": False}
    # Foreground lifecycle: Ctrl-C closes the tunnel. No shell, remote installation or firewall edits.
    try:
        code = subprocess.call(args)
    except KeyboardInterrupt:
        return {"stopped": True}
    return {"stopped": True, "exit_status": code}


def register(sub):
    p = sub.add_parser("network-setup", help="交付已有代理的专用客户端配置，或启动已有服务器的 SSH SOCKS 隧道")
    p.add_argument("action", choices=("client-config", "ssh-tunnel"))
    p.add_argument("--config", required=True)
    p.add_argument("--out")
    p.add_argument("--apply", action="store_true")
