"""Optional public list downloads with local membership checks; no queried IP in URL."""
import hashlib
import ipaddress
import json
import urllib.request

from .diagnostics import result
from .intelligence import public_ip
from .transport import NoRedirect

SOURCES = {
    "ipsum": {"url": "https://raw.githubusercontent.com/stamparm/ipsum/master/ipsum.txt", "host": "raw.githubusercontent.com", "terms": "https://github.com/stamparm/ipsum/blob/master/LICENSE"},
    "spamhaus-drop": {"url": "https://www.spamhaus.org/drop/drop_v4.json", "host": "www.spamhaus.org", "terms": "https://www.spamhaus.org/drop/terms/"},
}


def parse(name, raw, address):
    ip = ipaddress.ip_address(public_ip(address))
    hits, entries, metadata = [], 0, {}
    for line in raw.decode("utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        if name == "ipsum":
            columns = line.split()
            if len(columns) != 2 or not columns[1].isdigit():
                raise ValueError()
            network = ipaddress.ip_network(columns[0])
            evidence = {"overlapping_feed_count": int(columns[1])}
        else:
            data = json.loads(line)
            if not isinstance(data, dict):
                raise ValueError()
            if "cidr" not in data:
                metadata["published_epoch"] = data.get("timestamp") if type(data.get("timestamp")) is int else None
                continue
            network = ipaddress.ip_network(data["cidr"])
            evidence = {"network": str(network)}
        entries += 1
        if ip.version == network.version and ip in network:
            hits.append(evidence)
        if len(hits) > 64 or entries > 500000:
            raise ValueError()
    if not entries:
        raise ValueError()
    return {"listed": bool(hits), "matches": hits, "entries_checked": entries, "download_sha256": hashlib.sha256(raw).hexdigest(),
            "source_metadata": metadata, "source_updated_time_verified": False, "queried_ip_transmitted": False}


def query(name, address, opener=None):
    spec = SOURCES[name]
    url = spec["url"]
    if name == "spamhaus-drop" and ipaddress.ip_address(address).version == 6:
        url = url.replace("drop_v4", "drop_v6")
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Zhibi/0.3 public-list-check"})
        with (opener or urllib.request.build_opener(NoRedirect())).open(request, timeout=10) as response:
            raw = response.read(8 * 1024 * 1024 + 1)
        if len(raw) > 8 * 1024 * 1024:
            raise ValueError()
        facts = parse(name, raw, address)
        return result("review" if facts["listed"] else "ok", facts, [spec["host"]], "selected_ip")
    except (OSError, ValueError, TypeError):
        return result("error", recipients=[spec["host"]], subject="selected_ip")
