#!/usr/bin/env python3
"""Linux proxy namespace integration against an isolated Unix SOCKS fixture.

Pass a locally built graftcp binary from the revision in process-wrapper.md.
No public network connections, application credentials or global changes.
"""
import hashlib
import json
import os
from pathlib import Path
import socket
import socketserver
import struct
import subprocess
import sys
import tempfile
import threading

from zhibi.sandbox import prepare


def exact(sock, size):
    data = b''
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise EOFError()
        data += chunk
    return data


class Socks(socketserver.BaseRequestHandler):
    def handle(self):
        sock = self.request
        sock.settimeout(5)
        try:
            version, count = exact(sock, 2)
            assert version == 5 and 0 in exact(sock, count)
            sock.sendall(b'\x05\x00')
            version, cmd, _, kind = exact(sock, 4)
            assert version == 5 and cmd == 1
            if kind == 1:
                host = socket.inet_ntop(socket.AF_INET, exact(sock, 4))
            elif kind == 3:
                host = exact(sock, exact(sock, 1)[0]).decode()
            else:
                host = socket.inet_ntop(socket.AF_INET6, exact(sock, 16))
            port = struct.unpack('!H', exact(sock, 2))[0]
            self.server.destinations.append((host, port))
            assert (host, port) in [('203.0.113.10', 80), ('1.1.1.1', 53)], (host, port)
            sock.sendall(b'\x05\x00\x00\x01\x7f\x00\x00\x01\x00\x00')
            if port == 80:
                request = b''
                while b'\r\n\r\n' not in request:
                    request += exact(sock, 1)
                sock.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 12\r\nConnection: close\r\n\r\nproxy-passed')
            else:
                while True:
                    size = struct.unpack('!H', exact(sock, 2))[0]
                    query = exact(sock, size)
                    end = 12
                    while query[end]:
                        end += query[end] + 1
                    end += 1
                    qtype = struct.unpack('!H', query[end:end + 2])[0]
                    question = query[12:end + 4]
                    answer = (b'\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04'
                              + socket.inet_aton('203.0.113.10')) if qtype == 1 else b''
                    response = query[:2] + struct.pack('!HHHHH', 0x8180, 1, bool(answer), 0, 0) + question + answer
                    sock.sendall(struct.pack('!H', len(response)) + response)
        except (EOFError, ConnectionError, TimeoutError):
            pass
        except Exception as exc:
            self.server.errors.append(repr(exc))


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


def main():
    binary = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix='zhibi-proxy-check-') as tmp:
        root = Path(tmp).resolve()
        work = root / 'work'; work.mkdir()
        endpoint = root / 'proxy.sock'
        server = Server(str(endpoint), Socks)
        server.destinations = []; server.errors = []
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            profile = root / 'profile'
            prepare(profile, work, network='proxy', graftcp=str(binary),
                    graftcp_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(), proxy_socket=str(endpoint))
            test = work / 'test.py'
            test.write_text('''import json, socket, subprocess, urllib.request
assert urllib.request.urlopen('http://203.0.113.10', timeout=5).read() == b'proxy-passed'
assert urllib.request.urlopen('http://zhibi-proxy.test', timeout=5).read() == b'proxy-passed'
child = subprocess.check_output(['/usr/bin/python3', '-c', "import urllib.request; print(urllib.request.urlopen('http://zhibi-proxy.test',timeout=5).read().decode())"], timeout=10)
assert child.strip() == b'proxy-passed'
status = dict(line.split(':', 1) for line in open('/proc/self/status') if ':' in line)
for key in ('CapEff', 'CapPrm', 'CapInh', 'CapBnd', 'CapAmb'):
    assert int(status[key].strip(), 16) == 0, (key, status[key])
assert not any(line.split()[1] == '00000000' for line in open('/proc/net/route').readlines()[1:])
for family, target in [(socket.AF_INET, ('1.1.1.1', 443)), (socket.AF_INET6, ('2606:4700:4700::1111', 443))]:
    with socket.socket(family, socket.SOCK_DGRAM) as s:
        s.settimeout(1)
        try:
            s.sendto(b'blocked', target)
        except OSError:
            pass
        else:
            raise AssertionError('direct UDP escaped')
print(json.dumps({'tcp': True, 'dns': True, 'child': True, 'caps_dropped': True, 'direct_udp_blocked': True}))
''')
            argv = [sys.executable, str(profile / 'run.py'), '--', '/usr/bin/python3', '/workspace/test.py']
            result = subprocess.run(argv, capture_output=True, text=True, timeout=40)
            assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
            assert not server.errors, server.errors
            observations = json.loads(result.stdout)
            assert ('1.1.1.1', 53) in server.destinations, server.destinations
            assert ('203.0.113.10', 80) in server.destinations, server.destinations
            server.shutdown(); server.server_close(); thread.join(timeout=5)
            failed = subprocess.run(argv, capture_output=True, text=True, timeout=20)
            assert failed.returncode != 0, 'proxy stopped but networking still succeeded'
            observations['proxy_off_fails'] = True
            endpoint.unlink()
            server = Server(str(endpoint), Socks)
            server.destinations = []; server.errors = []
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            recovered = subprocess.run(argv, capture_output=True, text=True, timeout=40)
            assert recovered.returncode == 0, (recovered.returncode, recovered.stderr)
            assert not server.errors, server.errors
            observations['proxy_restoration_succeeds'] = True
            print(json.dumps(observations))
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=5)


if __name__ == '__main__':
    main()
