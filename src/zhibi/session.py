"""Ephemeral loopback probe receiver. No directory listing or private report serving."""
import json
import secrets
import socket
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from .browser import advanced_page, parse_bundle
from .models import InputError
from .storage import create_run, write


def probe_page(preset, network, download_name="zhibi-browser.json"):
    selected = (["ipv4", "ipv6"] if network else []) + (["webrtc", "extra-tls"] if network and preset == "all" else [])
    if preset == "all":
        selected += ["detail-" + k for k in ("locale", "identity", "runtime", "hardware", "fonts", "permissions")]
        selected += ["extra-" + k for k in ("canvas", "webgl", "audio", "dns")]
    defaults = '<script>for(const id of ' + json.dumps(selected) + '){document.getElementById(id).checked=true;}</script>'
    page = advanced_page().replace('</body>', defaults + '</body>')
    page = page.replace('a.download="zhibi-browser.json"', 'a.download=' + json.dumps(download_name))
    if selected:
        page = page.replace('默认不联网。只记录本页浏览器背景和能力。', '已按所选组合勾选检查；可以取消任何一项，点击开始后才执行。')
    if preset == "basic":
        page = page.replace('id="network-options" open', 'id="network-options"')
    return page


def handler(directory, token, state, preset="basic", network=False):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def setup(self):
            super().setup()
            self.connection.settimeout(3)

        def valid_host(self):
            return self.headers.get("Host") == "127.0.0.1:" + str(self.server.server_port)

        def send(self, code, data, mime="application/json"):
            self.send_response(code)
            self.send_header("Content-Type", mime + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if not self.valid_host() or self.path != "/" + token or state.get("received"):
                return self.send(404, b'{}')
            page = probe_page(preset, network).replace("connect-src https:", "connect-src 'self' https:", 1)
            page = page.replace('id="download" class="secondary"', 'id="download" hidden class="secondary"')
            script = '''<script>
const localSave=document.createElement('button');localSave.textContent='保存到本机并生成报告';localSave.className='secondary';document.getElementById('download').after(localSave);
localSave.addEventListener('click',async()=>{if(!output)return;localSave.disabled=true;try{const response=await fetch(location.pathname+'/result',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(output),credentials:'omit'});if(!response.ok)throw new Error();document.getElementById('status').textContent='结果已保存到本机。Agent 正在生成报告。';localSave.textContent='已保存到本机';}catch{localSave.disabled=false;document.getElementById('status').textContent='本机保存失败，请使用下载文件方式重试。';document.getElementById('download').hidden=false;}});
</script>'''
            page = page.replace('</body>', script + '</body>')
            self.send(200, page.encode(), "text/html")

        def do_POST(self):
            expected_origin = "http://127.0.0.1:" + str(self.server.server_port)
            if not self.valid_host() or self.path != "/" + token + "/result" or self.headers.get("Origin") != expected_origin or state.get("received"):
                return self.send(403, b'{}')
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 131072 or self.headers.get("Content-Type") != "application/json" or self.headers.get("Transfer-Encoding"):
                    raise ValueError()
                data = json.loads(self.rfile.read(length))
                parse_bundle(data)
                write(directory / "browser.private.json", data)
                state["received"] = True
                self.send(200, b'{"saved_locally":true}')
            except (InputError, ValueError, OSError, TypeError):
                self.send(400, b'{"saved_locally":false}')
    return Handler


def read_export(path):
    if not path.exists() or path.is_symlink() or not path.is_file():
        return None
    try:
        if path.stat().st_size > 131072:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        parse_bundle(data)
        return data
    except (InputError, ValueError, OSError, TypeError):
        return None


def file_received(directory, download=None):
    if read_export(directory / "browser.private.json") is not None:
        return True
    data = read_export(download) if download is not None else None
    if data is None:
        return False
    write(directory / "browser.private.json", data)
    return True


def run(out, preset="basic", network=False, config=None, wait=900, emit=print, file_mode=False):
    if not 30 <= wait <= 1800:
        raise InputError("等待时间范围为 30–1800 秒。")
    directory = create_run(out)
    token, state = secrets.token_urlsafe(24), {}
    download_name = "zhibi-session-" + secrets.token_hex(16) + ".json"
    download = Path.home() / "Downloads" / download_name
    write(directory / "probe.html", probe_page(preset, network, download_name))
    server = None if file_mode else HTTPServer(("127.0.0.1", 0), handler(directory, token, state, preset, network))
    emit(json.dumps({"open_in_actual_browser": str(directory / "probe.html") if file_mode else "http://127.0.0.1:" + str(server.server_port) + "/" + token,
                    "file_fallback": str(directory / "probe.html"), "save_download_as": str(directory / "browser.private.json"),
                    "automatic_download_file": str(download),
                    "expires_in_seconds": wait, "bind": "none" if file_mode else "loopback_only", "private_report_served": False}, ensure_ascii=False))
    deadline = time.monotonic() + wait
    try:
        if server:
            server.timeout = 1
        while not state.get("received") and time.monotonic() < deadline:
            if file_received(directory, download):
                state["received"] = True
                break
            if server:
                server.handle_request()
            else:
                time.sleep(.5)
    finally:
        if server:
            server.server_close()
    if not state.get("received"):
        return {"status": "timed_out", "directory": str(directory), "collector_external_requests": 0, "browser_observation_received": False}
    from .suite import run as suite
    return suite(preset=preset, network=network, browser=directory / "browser.private.json", target="browser", config_path=config, out=directory / "report", progress=emit)


def register(sub):
    p = sub.add_parser("session", help="在实际浏览器打开一次性本机探针；保存后自动生成报告")
    p.add_argument("--out")
    p.add_argument("--preset", choices=("basic", "all"), default="basic")
    p.add_argument("--network", action="store_true")
    p.add_argument("--config")
    p.add_argument("--wait", type=int, default=900)
    p.add_argument("--file", action="store_true", help="代理环境无法访问回环地址时，用本地 HTML 并监听指定导出文件；不启动 HTTP 服务")
