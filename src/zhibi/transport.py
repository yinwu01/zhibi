"""One bounded, opt-in HTTP boundary. No redirects, cookies, retries or arbitrary URLs."""
from __future__ import annotations

import ipaddress
import json
import socket
import ssl
import urllib.error
import urllib.request

from .models import ENDPOINT, IPV6_ENDPOINT


class NetworkError(Exception):
    def __init__(self, status="error"):
        self.status = status
        super().__init__("外部测量未完成；原始异常未写入报告。")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Transport:
    def __init__(self, enabled=False, metadata=False, timeout=8, ipv6=False, connectivity=False, target=None):
        self.enabled = enabled
        self.metadata = metadata
        self.ipv6 = ipv6
        self.connectivity = bool(connectivity and target)
        self.target = target
        self.timeout = timeout
        self.remaining = 1 + int(metadata) + int(ipv6) + int(connectivity)
        self.attempted = set()
        self.flows = []

    def get(self, service, ip=None):
        if not self.enabled or self.remaining <= 0 or service in self.attempted:
            raise NetworkError()
        if service == "ipify":
            url = ENDPOINT
            recipient = "api.ipify.org"
            fields = ["request_source_ip", "network_metadata"]
        elif service == "ipify6" and self.ipv6:
            url, recipient = IPV6_ENDPOINT, "api6.ipify.org"
            fields = ["request_source_ip", "network_metadata"]
        elif service == "ipwhois" and self.metadata:
            try:
                address = ipaddress.ip_address(ip)
            except (ValueError, TypeError):
                raise NetworkError() from None
            if not address.is_global:
                raise NetworkError()
            url = "https://ipwho.is/" + str(address)
            recipient = "ipwho.is"
            fields = ["request_source_ip", "queried_ip", "network_metadata"]
        else:
            raise NetworkError()
        self.remaining -= 1
        self.attempted.add(service)
        # sent means attempted: a failure does not establish that no bytes left the host.
        self.flows.append({"purpose": service + " observation attempt", "recipient": recipient,
                           "fields": fields, "sent": True})
        try:
            opener = urllib.request.build_opener(NoRedirect())
            req = urllib.request.Request(url, headers={"User-Agent": "Zhibi/0.1", "Accept": "application/json"})
            with opener.open(req, timeout=self.timeout) as response:
                raw = response.read(16385)
            if len(raw) > 16384:
                raise NetworkError()
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise NetworkError()
            return result
        except (TimeoutError, socket.timeout):
            raise NetworkError("timeout") from None
        except urllib.error.HTTPError as exc:
            if exc.fp is not None:
                exc.close()
            raise NetworkError() from None
        except urllib.error.URLError as exc:
            state = "timeout" if isinstance(exc.reason, (TimeoutError, socket.timeout)) else "error"
            raise NetworkError(state) from None
        except (OSError, ValueError, UnicodeError):
            raise NetworkError() from None

    def probe_target(self):
        """One unauthenticated HEAD to the declared target, preserving the error layer."""
        if not self.enabled or not self.connectivity or not self.target or self.remaining <= 0 or "target-public" in self.attempted:
            raise NetworkError()
        self.remaining -= 1
        self.attempted.add("target-public")
        endpoint = "https://" + self.target + "/"
        self.flows.append({"purpose": "public homepage HEAD attempt", "recipient": self.target,
                           "fields": ["request_source_ip", "network_metadata"], "sent": True})
        facts = {"endpoint": endpoint, "http_status": None, "outcome": "transport_error"}
        try:
            opener = urllib.request.build_opener(NoRedirect())
            req = urllib.request.Request(endpoint, method="HEAD", headers={"User-Agent": "Zhibi/0.1"})
            with opener.open(req, timeout=self.timeout) as response:
                facts.update(http_status=response.status, outcome="http_response")
        except urllib.error.HTTPError as exc:
            facts.update(http_status=exc.code, outcome="http_response")
            if exc.fp is not None:
                exc.close()
        except (OSError, ValueError) as exc:
            reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
            if isinstance(reason, socket.gaierror):
                facts["outcome"] = "dns_error"
            elif isinstance(reason, ssl.SSLError):
                facts["outcome"] = "tls_error"
            elif isinstance(reason, (TimeoutError, socket.timeout)):
                facts["outcome"] = "timeout"
        return facts
