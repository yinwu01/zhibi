"""Optional self-hosted authoritative DNS observer, not an open recursive resolver.

Run behind an HTTPS reverse proxy with a wildcard certificate. Explicit deployment
is required; the CLI never deploys or opens a firewall automatically.
"""
import ipaddress
import json
import re
import secrets
import socketserver
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlsplit, parse_qs

from .models import InputError


class Observer:
    def __init__(self, zone, address):
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,250}[a-z0-9])?", zone) or "." not in zone:
            raise InputError("需要自己的委派 DNS 域名。")
        self.zone = zone.lower().rstrip(".")
        self.address = ipaddress.IPv4Address(address).packed
        self.tickets = {}
        self.lock = threading.Lock()

    def ticket(self):
        with self.lock:
            self.tickets = {k: v for k, v in self.tickets.items() if time.monotonic() - v["created"] < 300}
            if len(self.tickets) >= 128:
                return None
            token = secrets.token_hex(16)
            self.tickets[token] = {"created": time.monotonic(), "resolvers": set(), "ecs": set()}
            return token

    def report(self, token):
        with self.lock:
            v = self.tickets.get(token)
            if not v or time.monotonic() - v["created"] >= 300:
                return None
            return {"token": token, "resolvers": sorted(v["resolvers"]), "ecs": sorted(v["ecs"]), "transport_from_browser": "not_observable", "window_seconds": 300}

    def answer(self, packet, peer):
        if not 17 <= len(packet) <= 4096:
            return None
        ident, flags, qd, an, ns, ar = struct.unpack("!6H", packet[:12])
        if flags & 0x8000 or flags & 0x7800 or qd != 1 or an or ns or ar > 1:
            return None
        pos, parts = 12, []
        try:
            while packet[pos]:
                n = packet[pos]
                if n > 63 or pos + n + 1 >= len(packet):
                    return None
                parts.append(packet[pos + 1:pos + n + 1].decode("ascii").lower())
                pos += n + 1
            pos += 1
            kind, cls = struct.unpack("!HH", packet[pos:pos + 4])
            end = pos + 4
        except (IndexError, UnicodeError, struct.error):
            return None
        name = ".".join(parts)
        token = name[:-(len(self.zone) + 1)] if name.endswith("." + self.zone) else None
        if cls != 1 or name != self.zone and not (token and re.fullmatch("[a-f0-9]{32}", token)):
            return struct.pack("!6H", ident, 0x8005, 1, 0, 0, 0) + packet[12:end]
        ecs = []
        if ar and packet[end:end + 1] == b"\x00":
            try:
                opt, _, _, size = struct.unpack("!HHIH", packet[end + 1:end + 11])
                cursor, limit = end + 11, end + 11 + size
                if opt == 41 and limit <= len(packet):
                    while cursor + 4 <= limit:
                        code, n = struct.unpack("!HH", packet[cursor:cursor + 4])
                        value = packet[cursor + 4:cursor + 4 + n]
                        cursor += 4 + n
                        if code == 8 and len(value) >= 4:
                            family, prefix, scope = struct.unpack("!HBB", value[:4])
                            length = 4 if family == 1 else 16 if family == 2 else 0
                            if length and prefix <= length * 8 and scope <= length * 8 and len(value[4:]) == (prefix + 7) // 8:
                                addr = ipaddress.ip_address(value[4:].ljust(length, b"\x00"))
                                ecs.append(str(ipaddress.ip_network(str(addr) + "/" + str(prefix), strict=False)))
            except (ValueError, struct.error):
                pass
        with self.lock:
            entry = self.tickets.get(token)
            if token and (not entry or time.monotonic() - entry["created"] >= 300):
                return struct.pack("!6H", ident, 0x8403, 1, 0, 0, 0) + packet[12:end]
            if entry and len(entry["resolvers"]) < 16:
                entry["resolvers"].add(str(ipaddress.ip_address(peer)))
                entry["ecs"] = set(sorted(entry["ecs"] | set(ecs[:4]))[:16])
        answer = b"\xc0\x0c" + struct.pack("!HHIH", 1, 1, 0, 4) + self.address if kind == 1 else b""
        return struct.pack("!6H", ident, 0x8400, 1, bool(answer), 0, 0) + packet[12:end] + answer


def serve(zone, address, bind="127.0.0.1", dns_port=5353, http_port=8053):
    observer = Observer(zone, address)
    class DNS(socketserver.BaseRequestHandler):
        def handle(self):
            packet, sock = self.request
            answer = observer.answer(packet, self.client_address[0])
            if answer:
                sock.sendto(answer, self.client_address)
    class TCP(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.settimeout(3)
            try:
                header = self.request.recv(2)
                if len(header) != 2:
                    return
                length = struct.unpack("!H", header)[0]
                if length > 4096:
                    return
                data = b""
                while len(data) < length:
                    part = self.request.recv(length - len(data))
                    if not part:
                        return
                    data += part
                answer = observer.answer(data, self.client_address[0])
                if answer:
                    self.request.sendall(struct.pack("!H", len(answer)) + answer)
            except OSError:
                return
    class HTTP(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            url = urlsplit(self.path)
            if url.path == "/ticket":
                token = observer.ticket()
                data = {"token": token, "zone": zone} if token else None
            elif url.path == "/result":
                data = observer.report(parse_qs(url.query).get("token", [""])[0])
            elif url.path == "/ping":
                data = {"ok": True}
            else:
                data = None
            raw = json.dumps(data).encode()
            self.send_response(200 if data else 404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
    with socketserver.UDPServer((bind, dns_port), DNS) as udp, socketserver.TCPServer((bind, dns_port), TCP) as tcp, HTTPServer((bind, http_port), HTTP) as http:
        threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in (udp, tcp)]
        for thread in threads:
            thread.start()
        try:
            http.serve_forever()
        finally:
            udp.shutdown()
            tcp.shutdown()
