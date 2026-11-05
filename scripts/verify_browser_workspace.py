"""Check permission behavior in real Chromium, with isolated profiles and local pages."""
import json
import os
import signal
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace
from zhibi.browser_workspace import create

HTML = b'''<!doctype html><html><body><pre id="result">pending</pre><script>
Promise.all(['geolocation','camera','microphone','notifications'].map(async name => {
  try { return [name,(await navigator.permissions.query({name})).state]; }
  catch(e) { return [name,'unsupported']; }
})).then(entries => fetch('/result',{method:'POST',body:JSON.stringify(Object.fromEntries(entries))}));
</script></body></html>'''

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def do_POST(self):
        self.server.observation = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.send_response(200)
        self.end_headers()
        self.server.received.set()
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.send_header('Content-Length', str(len(HTML)))
        self.end_headers()
        self.wfile.write(HTML)


def inspect(binary, profile, url, flags):
    server.received.clear()
    server.observation = None
    process = subprocess.Popen([binary, '--headless=new', '--disable-gpu', '--no-first-run',
        '--disable-background-networking', '--disable-component-update', '--remote-debugging-port=0',
        '--user-data-dir=' + str(profile), *flags, url],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        assert server.received.wait(15), "browser did not report permission state"
        return server.observation
    finally:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=5)


binary = os.environ['CHROME_PATH']
with tempfile.TemporaryDirectory(prefix='zhibi-controls-') as tmp:
    root = Path(tmp)
    server = HTTPServer(('127.0.0.1', 0), Handler)
    server.received = threading.Event()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = 'http://127.0.0.1:%d/' % server.server_port
        baseline = inspect(binary, root / 'baseline', url, [])
        output = root / 'workspace'
        create(SimpleNamespace(browser_binary=binary, local_port=10818, out=str(output)))
        flags = json.loads((output / 'browser.private.json').read_text())['flags']
        controlled = inspect(binary, output / 'profile', url, flags)
        assert baseline['geolocation'] == 'prompt', baseline
        assert all(state == 'denied' for state in controlled.values()), controlled
        print(json.dumps({'baseline': baseline, 'workspace': controlled,
                          'result': 'passed', 'scope': 'page permission queries; no coordinate/media acquisition'}))
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
