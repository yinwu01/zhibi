"""Real OpenSSH/SOCKS integration against a disposable loopback Paramiko server.
Run: PYTHONPATH=src uv run --no-project --with paramiko python scripts/verify_ssh_integration.py
No VPS, account, public network request, or persistent SSH config is used.
"""
import json
import errno
import os
import select
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace
import paramiko
from zhibi.connect import argv
from zhibi.connection_bundle import export
from zhibi.browser_workspace import create as create_browser_workspace


def listener():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    sock.settimeout(.2)
    return sock


with tempfile.TemporaryDirectory(prefix="zhibi-ssh-") as tmp:
    root = Path(tmp)
    identity = paramiko.RSAKey.generate(2048)
    key = root / "identity"
    identity.write_private_key_file(str(key))
    key.chmod(0o600)
    host_key = paramiko.RSAKey.generate(2048)
    ssh_listener, http_listener = listener(), listener()
    stop = threading.Event()
    errors, transports, destinations, workers = [], [], [], []

    def spawn(fn, *args):
        def guarded():
            try:
                fn(*args)
            except Exception as exc:
                if not stop.is_set():
                    errors.append(repr(exc))
        thread = threading.Thread(target=guarded, daemon=True)
        workers.append(thread)
        thread.start()

    class Server(paramiko.ServerInterface):
        def __init__(self):
            self.terminals = set()
        def check_channel_pty_request(self, channel, term, width, height, pixelwidth, pixelheight, modes):
            self.terminals.add(channel.get_id())
            return True

        def get_allowed_auths(self, username):
            return "publickey"
        def check_auth_publickey(self, username, supplied):
            return paramiko.AUTH_SUCCESSFUL if supplied == identity else paramiko.AUTH_FAILED
        def check_channel_request(self, kind, chanid):
            return paramiko.OPEN_SUCCEEDED if kind == "session" else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED
        def check_channel_direct_tcpip_request(self, chanid, origin, destination):
            if destination not in (("127.0.0.1", http_listener.getsockname()[1]), ("zhibi-proxy.test", http_listener.getsockname()[1])):
                return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED
            destinations.append(destination)
            return paramiko.OPEN_SUCCEEDED
        def check_channel_exec_request(self, channel, command):
            def execute():
                if channel.get_id() in self.terminals:
                    master, slave = os.openpty()
                    try:
                        child = subprocess.Popen(["sh", "-c", command.decode()], stdin=slave, stdout=slave, stderr=slave)
                        os.close(slave)
                        slave = None
                        while True:
                            try:
                                data = os.read(master, 4096)
                            except OSError as exc:
                                if exc.errno == errno.EIO:
                                    break
                                raise
                            if not data:
                                break
                            channel.sendall(data)
                        channel.send_exit_status(child.wait(timeout=5))
                    finally:
                        if slave is not None:
                            os.close(slave)
                        os.close(master)
                else:
                    done = subprocess.run(["sh", "-c", command.decode()], capture_output=True, timeout=5)
                    if done.stdout:
                        channel.sendall(done.stdout)
                    if done.stderr:
                        channel.sendall_stderr(done.stderr)
                    channel.send_exit_status(done.returncode)
                channel.close()
            spawn(execute)
            return True

    def serve_http():
        while not stop.is_set():
            try:
                connection, _ = http_listener.accept()
            except socket.timeout:
                continue
            with connection:
                connection.settimeout(3)
                connection.recv(8192)
                connection.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 12\r\nConnection: close\r\n\r\nthrough-ssh!")

    def relay(channel):
        with socket.create_connection(http_listener.getsockname(), timeout=3) as upstream:
            try:
                while not stop.is_set():
                    ready, _, _ = select.select([channel, upstream], [], [], .2)
                    for source in ready:
                        data = source.recv(32768)
                        if not data:
                            return
                        (upstream if source is channel else channel).sendall(data)
            finally:
                channel.close()

    # Track channel kind explicitly rather than infer it from socket metadata.
    forwarded = set()
    original_forward = Server.check_channel_direct_tcpip_request
    def forward(self, chanid, origin, destination):
        result = original_forward(self, chanid, origin, destination)
        if result == paramiko.OPEN_SUCCEEDED:
            forwarded.add((id(self), chanid))
        return result
    Server.check_channel_direct_tcpip_request = forward

    def serve_connection(connection):
        transport = paramiko.Transport(connection)
        transports.append(transport)
        transport.add_server_key(host_key)
        server = Server()
        transport.start_server(server=server)
        while transport.is_active() and not stop.is_set():
            channel = transport.accept(.2)
            if channel and (id(server), channel.get_id()) in forwarded:
                spawn(relay, channel)

    def serve_ssh():
        while not stop.is_set():
            try:
                connection, _ = ssh_listener.accept()
            except socket.timeout:
                continue
            spawn(serve_connection, connection)

    known = root / "known_hosts"
    known.write_text("[127.0.0.1]:%d %s %s\n" % (ssh_listener.getsockname()[1], host_key.get_name(), host_key.get_base64()))
    spawn(serve_http)
    spawn(serve_ssh)
    port_socket = listener()
    local_port = port_socket.getsockname()[1]
    port_socket.close()
    args = SimpleNamespace(host="127.0.0.1", user="tester", port=ssh_listener.getsockname()[1],
                           identity=str(key), local_port=local_port, command_file=None, workdir=None, interactive=False)
    def command():
        result = argv(args)
        # Test-only host trust is pinned to the generated key; never edit user's known_hosts.
        result[1:1] = ["-o", "UserKnownHostsFile=" + str(known), "-o", "StrictHostKeyChecking=yes", "-o", "IdentitiesOnly=yes"]
        return result
    args.apply = False
    args.export_out = str(root / "bundle")
    delivered = export(args, command())
    tunnel = subprocess.Popen([sys.executable, "-I", delivered["launcher"]], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              start_new_session=True)
    try:
        for _ in range(50):
            if tunnel.poll() is not None:
                raise AssertionError(tunnel.communicate()[1].decode())
            try:
                with socket.create_connection(("127.0.0.1", local_port), timeout=.1):
                    break
            except OSError:
                time.sleep(.1)
        response = subprocess.run(["curl", "-q", "--silent", "--show-error", "--max-time", "5", "--noproxy", "", "--proxy",
                                   "socks5h://127.0.0.1:%d" % local_port,
                                   "http://127.0.0.1:%d/" % http_listener.getsockname()[1]], capture_output=True)
        assert response.returncode == 0, response.stderr
        assert response.stdout == b"through-ssh!", response.stdout
        assert destinations
        browser_state = "not_exercised"
        chrome = os.environ.get("CHROME_PATH")
        if chrome:
            workspace = root / "browser-workspace"
            create_browser_workspace(SimpleNamespace(browser_binary=chrome, local_port=local_port, out=str(workspace)))
            flags = json.loads((workspace / "browser.private.json").read_text())["flags"]
            browser = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--no-first-run",
                "--disable-background-networking", "--disable-component-update", "--disable-sync",
                "--user-data-dir=" + str(workspace / "profile"), *flags,
                "--dump-dom", "http://zhibi-proxy.test:%d/" % http_listener.getsockname()[1]],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            try:
                dom, stderr = browser.communicate(timeout=12)
            except subprocess.TimeoutExpired:
                # Some desktop Chrome builds keep helper pipes open after dumping the DOM.
                os.killpg(browser.pid, signal.SIGTERM)
                try:
                    dom, stderr = browser.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(browser.pid, signal.SIGKILL)
                    dom, stderr = browser.communicate(timeout=5)
            assert b"through-ssh!" in dom, (dom[-2000:], stderr[-1000:], destinations)
            assert ("zhibi-proxy.test", http_listener.getsockname()[1]) in destinations
            browser_state = "passed"
        tunnel.terminate()
        tunnel.wait(timeout=8)
        with socket.socket() as probe:
            assert probe.connect_ex(("127.0.0.1", local_port)) != 0, "orphaned SSH listener"
        script = root / "command"
        script.write_text("printf remote-ok; exit 7\n")
        script.chmod(0o600)
        args.command_file = str(script)
        result = subprocess.run(command(), capture_output=True, timeout=10)
        assert result.stdout == b"remote-ok", result.stdout
        assert result.returncode == 7, result.stderr
        script.write_text("test -t 0 && test -t 1 && printf terminal-ok\n")
        args.interactive = True
        result = subprocess.run(command(), capture_output=True, timeout=10)
        assert result.returncode == 0 and b"terminal-ok" in result.stdout, (result.returncode, result.stderr)
        occupied = listener()
        try:
            args.local_port = occupied.getsockname()[1]
            args.command_file = None
            args.interactive = False
            result = subprocess.run(command(), capture_output=True, timeout=10)
            assert result.returncode != 0, "occupied port incorrectly succeeded"
        finally:
            occupied.close()
        assert not errors, errors
        print(json.dumps({"ssh_auth": "passed", "socks_http": "passed", "remote_command": "passed", "remote_pty": "passed", "port_conflict": "passed", "exit_status": "passed", "standalone_launcher": "passed", "parent_termination_closes_proxy": "passed", "chromium_socks_navigation": browser_state, "scope": "loopback protocol test; not user browser or Linux VPS acceptance"}))
    finally:
        if tunnel.poll() is None:
            tunnel.terminate()
            tunnel.wait(timeout=5)
        stop.set()
        for transport in transports:
            transport.close()
        ssh_listener.close()
        http_listener.close()
        for worker in workers:
            worker.join(timeout=1)
