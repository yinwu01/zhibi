#!/usr/bin/env python3
"""Real systemd --user deployment, restart, collision and rollback verification.

Uses only randomly named zhibi-* units and temporary directories. Requires an
already running Linux user manager; does not enable linger or alter existing units.
"""
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import uuid

from zhibi.sandbox import prepare
from zhibi.runtime_service import export, install, load, rollback, ctl, target_path


def wait_for(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.2)
    raise AssertionError('Timed out waiting for the service transition')


def main():
    binary = Path(sys.argv[1]).resolve()
    ctl('show-environment')
    with tempfile.TemporaryDirectory(prefix='zhibi-service-check-') as tmp:
        root = Path(tmp).resolve() / 'space $ percent% quote"'
        root.mkdir(mode=0o700)
        work = root / 'work'; work.mkdir()
        endpoint = root / 'gateway.sock'
        # Initial profile validation requires an existing owner-only endpoint.
        with socket.socket(socket.AF_UNIX) as initial:
            initial.bind(str(endpoint))
            prepare(root / 'profile', work, network='proxy', graftcp=str(binary),
                    graftcp_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(), proxy_socket=str(endpoint))
        endpoint.unlink()
        name = 'zhibi-test-' + uuid.uuid4().hex
        bundle = root / 'service'
        export(bundle, root / 'profile', name, ['/usr/bin/python3', '-c', 'import time; time.sleep(600)'])
        config = load(bundle)
        try:
            deployed = install(bundle, config)
            assert deployed['installed'] and endpoint.exists(), deployed
            first_pid = int(ctl('show', name, '-p', 'MainPID', '--value').stdout)
            children = Path('/proc/' + str(first_pid) + '/task/' + str(first_pid) + '/children').read_text().split()
            gateway_pid = next(int(pid) for pid in children
                               if str(bundle / 'gateway.py').encode() in Path('/proc/' + pid + '/cmdline').read_bytes().split(b'\0'))
            os.kill(gateway_pid, signal.SIGKILL)
            def restarted():
                pid = int(ctl('show', name, '-p', 'MainPID', '--value').stdout)
                return pid != 0 and pid != first_pid and endpoint.exists()
            wait_for(restarted)
            assert ctl('is-active', '--quiet', name, check=False).returncode == 0
            assert not Path('/proc/' + str(first_pid)).exists()
            original = target_path(config).read_bytes()
            export(root / 'collision', root / 'profile', name)
            try:
                install(root / 'collision', load(root / 'collision'))
            except ValueError:
                pass
            else:
                raise AssertionError('An existing service was overwritten')
            assert target_path(config).read_bytes() == original
            removed = rollback(bundle, config)
            assert removed['removed'] and not target_path(config).exists()
            wait_for(lambda: not endpoint.exists())
            # A failed application must restore the pre-install absence of the unit.
            failed_bundle = root / 'failed'
            export(failed_bundle, root / 'profile', name + '-fail', ['/bin/false'])
            failed_config = load(failed_bundle)
            try:
                install(failed_bundle, failed_config)
            except subprocess.CalledProcessError:
                pass
            else:
                raise AssertionError('Failed application was accepted as a healthy service')
            assert not target_path(failed_config).exists()
            wait_for(lambda: not endpoint.exists())
            print(json.dumps({'install': True, 'gateway_failure_restarts_runtime': True,
                              'existing_service_preserved': True, 'rollback': True,
                              'failed_start_restored': True}))
        finally:
            for directory in (bundle, root / 'failed'):
                if (directory / 'receipt.json').exists():
                    rollback(directory, load(directory))


if __name__ == '__main__':
    main()
