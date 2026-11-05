"""Private Unix SOCKS5 gateway using the VPS's existing TCP egress.

No public listener, logging of destinations, authentication store or UDP relay.
"""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import select
import signal
import socket
import socketserver
import struct
import threading


def exact(sock, count):
    value = b''
    while len(value) < count:
        chunk = sock.recv(count - len(value))
        if not chunk:
            raise EOFError()
        value += chunk
    return value


def relay(left, right):
    readers = [left, right]
    while readers:
        ready, _, _ = select.select(readers, [], [], 600)
        if not ready:
            return
        for source in ready:
            target = right if source is left else left
            data = source.recv(65536)
            if data:
                target.sendall(data)
            else:
                readers.remove(source)
                try:
                    target.shutdown(socket.SHUT_WR)
                except OSError:
                    pass


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        client = self.request
        client.settimeout(15)
        replied = False
        try:
            version, count = exact(client, 2)
            if version != 5:
                return
            if 0 not in exact(client, count):
                client.sendall(b'\x05\xff')
                return
            client.sendall(b'\x05\x00')
            version, command, reserved, kind = exact(client, 4)
            if version != 5 or command != 1 or reserved != 0:
                client.sendall(b'\x05\x07\x00\x01' + b'\x00' * 6)
                return
            if kind == 1:
                host = socket.inet_ntop(socket.AF_INET, exact(client, 4))
            elif kind == 4:
                host = socket.inet_ntop(socket.AF_INET6, exact(client, 16))
            elif kind == 3:
                host = exact(client, exact(client, 1)[0]).decode('ascii')
                if not host or '\0' in host:
                    return
            else:
                client.sendall(b'\x05\x08\x00\x01' + b'\x00' * 6)
                return
            port = struct.unpack('!H', exact(client, 2))[0]
            with socket.create_connection((host, port), timeout=15) as target:
                bound, bound_port = target.getsockname()[:2]
                address = ipaddress.ip_address(bound)
                client.sendall(bytes([5, 0, 0, 1 if address.version == 4 else 4])
                               + address.packed + struct.pack('!H', bound_port))
                replied = True
                client.settimeout(30); target.settimeout(30)
                relay(client, target)
        except (OSError, EOFError, ValueError, UnicodeError):
            if not replied:
                try:
                    client.sendall(b'\x05\x01\x00\x01' + b'\x00' * 6)
                except OSError:
                    pass


class Gateway(socketserver.ThreadingMixIn, getattr(socketserver, 'UnixStreamServer', socketserver.TCPServer)):
    daemon_threads = True
    request_queue_size = 32

    def __init__(self, path):
        if not hasattr(os, 'getuid'):
            raise ValueError('Unix gateway requires a POSIX system.')
        self.path = Path(path).expanduser().absolute()
        parent = self.path.parent
        if (not parent.is_dir() or any(p.is_symlink() for p in (parent, *parent.parents))
                or parent.stat().st_uid != os.getuid() or parent.stat().st_mode & 0o077):
            raise ValueError('Socket parent must be an existing owner-only directory without symlink ancestors.')
        if self.path.exists() or self.path.is_symlink():
            raise FileExistsError('Socket path already exists; inspect the old gateway before removing it.')
        self.slots = threading.BoundedSemaphore(64)
        self.inode = None
        super().__init__(str(self.path), Handler)
        self.inode = self.path.stat().st_ino
        self.path.chmod(0o600)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def server_close(self):
        super().server_close()
        if self.inode is not None:
            try:
                if self.path.lstat().st_ino == self.inode:
                    self.path.unlink()
            except FileNotFoundError:
                pass


def serve(path):
    def stop(signum, frame):
        raise SystemExit(0)
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        with Gateway(path) as server:
            for sig in previous:
                signal.signal(sig, stop)
            print(json.dumps({'status': 'ready', 'socket': str(server.path),
                              'egress': 'server-existing-route', 'protocol': 'SOCKS5 CONNECT'}), flush=True)
            server.serve_forever(poll_interval=0.2)
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--socket', required=True)
    serve(parser.parse_args().socket)
