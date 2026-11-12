#!/usr/bin/env python3
"""Explicit live HTTPS acceptance through the project's private SOCKS gateway."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from urllib.parse import urlsplit

from zhibi.proxy_gateway import Gateway
from zhibi.sandbox import prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--graftcp', required=True)
    parser.add_argument('--url', required=True, help='Explicit HTTPS destination for this live check')
    parser.add_argument('--dns-server', default='1.1.1.1')
    args = parser.parse_args()
    url = urlsplit(args.url)
    if url.scheme != 'https' or not url.hostname or url.username or url.password:
        raise ValueError('Provide an HTTPS URL without embedded credentials.')
    binary = Path(args.graftcp).resolve()
    with tempfile.TemporaryDirectory(prefix='zhibi-live-check-') as tmp:
        root = Path(tmp).resolve()
        work = root / 'work'; work.mkdir()
        with Gateway(root / 'proxy.sock') as gateway:
            thread = threading.Thread(target=gateway.serve_forever, daemon=True)
            thread.start()
            try:
                prepare(root / 'profile', work, network='proxy', graftcp=str(binary),
                        graftcp_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                        proxy_socket=str(root / 'proxy.sock'), dns_server=args.dns_server)
                source = ('import urllib.request,sys,json\n'
                          'with urllib.request.urlopen(sys.argv[1],timeout=15) as r:\n'
                          ' print(json.dumps({"status": r.status, "sample_bytes": len(r.read(4096))}))\n')
                argv = [sys.executable, str(root / 'profile/run.py'), '--', '/usr/bin/python3',
                        '-c', source, args.url]
                success = subprocess.run(argv, capture_output=True, text=True, timeout=30)
                assert success.returncode == 0, (success.returncode, success.stderr)
                observed = json.loads(success.stdout)
                assert observed['status'] == 200 and observed['sample_bytes'] > 0, observed
                gateway.shutdown(); gateway.server_close(); thread.join(timeout=5)
                failure = subprocess.run(argv, capture_output=True, text=True, timeout=30)
                assert failure.returncode != 0, 'gateway stopped but application still reached destination'
                with Gateway(root / 'proxy.sock') as restored:
                    recovery_thread = threading.Thread(target=restored.serve_forever, daemon=True)
                    recovery_thread.start()
                    try:
                        recovery = subprocess.run(argv, capture_output=True, text=True, timeout=30)
                        assert recovery.returncode == 0, (recovery.returncode, recovery.stderr)
                        assert json.loads(recovery.stdout)['status'] == 200
                    finally:
                        restored.shutdown(); recovery_thread.join(timeout=5)
                print(json.dumps({'https': observed, 'gateway_off_fails': True, 'gateway_restoration_succeeds': True}))
            finally:
                gateway.shutdown(); thread.join(timeout=5)


if __name__ == '__main__':
    main()
