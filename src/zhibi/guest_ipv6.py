"""Standalone IPv6 policy, executed only inside a managed Linux guest."""
import errno
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

BOOT_CONFIG = 'GRUB_CMDLINE_LINUX="${GRUB_CMDLINE_LINUX} ipv6.disable=1"\n'
CONFIG = "net.ipv6.conf.default.disable_ipv6 = 1\nnet.ipv6.conf.all.disable_ipv6 = 1\n"


def inspect():
    root = Path('/proc/sys/net/ipv6/conf')
    values = {p.parent.name: p.read_text().strip() for p in root.glob('*/disable_ipv6')}
    addresses = Path('/proc/net/if_inet6')
    empty = not addresses.exists() or not addresses.read_text().strip()
    blocked = False
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_DGRAM) as sock:
            sock.connect(('2001:db8::1', 9))  # No packet is sent by UDP connect.
    except OSError as exc:
        blocked = exc.errno in (errno.EAFNOSUPPORT, errno.EPROTONOSUPPORT, errno.ENETUNREACH, errno.EADDRNOTAVAIL)
    boot_disabled = 'ipv6.disable=1' in Path('/proc/cmdline').read_text().split() and not values
    disabled = boot_disabled or bool(values) and {'all', 'default', 'lo'} <= values.keys() and all(v == '1' for v in values.values())
    return {'state': 'ok' if disabled and empty and blocked else 'fail',
            'detail': 'guest IPv6 disabled' if disabled and empty and blocked else 'guest IPv6 policy not confirmed',
            'interfaces': values, 'kernel_boot_disabled': boot_disabled, 'no_ipv6_addresses': empty, 'ipv6_route_blocked': blocked}


def apply():
    if sys.platform != 'linux' or os.geteuid() != 0:
        raise RuntimeError('IPv6 guest configuration requires Linux guest root')
    boot = Path('/etc/default/grub.d/99-zhibi-disable-ipv6.cfg')
    if not boot.parent.is_dir():
        raise RuntimeError('Guest GRUB configuration unavailable; cannot persist IPv6 policy')
    if boot.is_symlink() or (boot.exists() and boot.read_text() != BOOT_CONFIG):
        raise RuntimeError('Existing guest boot policy differs; inspect it before continuing')
    if not boot.exists():
        fd = os.open(boot, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, 'w') as stream:
            stream.write(BOOT_CONFIG)
    # Regenerate on every apply so an earlier failed update cannot be mistaken for success.
    subprocess.run(['update-grub'], check=True, stdout=sys.stderr, stderr=sys.stderr, timeout=60)
    target = Path('/etc/sysctl.d/99-zhibi-disable-ipv6.conf')
    if target.is_symlink() or (target.exists() and target.read_text() != CONFIG):
        raise RuntimeError('Existing IPv6 policy file differs; inspect it before continuing')
    if not target.exists():
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, 'w') as stream:
            stream.write(CONFIG)
    root = Path('/proc/sys/net/ipv6/conf')
    if not root.exists() and 'ipv6.disable=1' in Path('/proc/cmdline').read_text().split():
        return
    for name in ('default', 'all'):
        (root / name / 'disable_ipv6').write_text('1\n')
    for path in root.glob('*/disable_ipv6'):
        path.write_text('1\n')


if __name__ == '__main__':
    if '--apply' in sys.argv:
        apply()
    result = inspect()
    print(json.dumps(result))
    raise SystemExit(0 if result['state'] == 'ok' else 1)
