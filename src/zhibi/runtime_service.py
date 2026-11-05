"""Export an owner-only systemd user service and reversible standalone manager."""
import argparse
import hashlib
import errno
import json
import os
from pathlib import Path
import re
import select
import signal
import socket
import subprocess
import sys
import stat
import tempfile
import time


def private_directory(value):
    path = Path(value).expanduser().absolute()
    if not path.is_dir() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Use an existing directory without symlink ancestors.')
    if path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
        raise ValueError('Directory must belong to the current user and have mode 700.')
    return path


def argument(value):
    if any(c in value for c in '\n\r\0'):
        raise ValueError('Newlines and NUL are not supported in unit arguments.')
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%').replace('$', '$$') + '"'


def export(out, profile, name, program=None):
    if not sys.platform.startswith('linux'):
        raise ValueError('Create the runtime service on its Linux server.')
    if not re.fullmatch(r'zhibi-[a-zA-Z0-9][a-zA-Z0-9_.-]{0,55}', name):
        raise ValueError('Choose a service name starting with zhibi-, using letters, digits, dots or hyphens.')
    root = private_directory(profile)
    data = json.loads((root / 'profile.json').read_text())
    if data.get('network') != 'proxy' or not data.get('proxy'):
        raise ValueError('The workspace must use proxy networking.')
    socket_path = Path(data['proxy']['socket'])
    private_directory(socket_path.parent)
    if not (root / 'run.py').is_file():
        raise ValueError('Workspace runner is missing.')
    directory = Path(out).expanduser().absolute()
    if any(p.is_symlink() for p in directory.parents):
        raise ValueError('Output path cannot contain symlink ancestors.')
    directory.mkdir(mode=0o700, exist_ok=False)
    from importlib.resources import files
    for source, target in [('runtime_service.py', 'manage.py'), ('proxy_gateway.py', 'gateway.py')]:
        (directory / target).write_text(files('zhibi').joinpath(source).read_text(encoding='utf-8'))
        (directory / target).chmod(0o700)
    command = [sys.executable, str(directory / 'manage.py'), 'supervise']
    unit = ('[Unit]\nDescription=Zhibi private application runtime\n'
            '[Service]\nType=notify\nNotifyAccess=main\nExecStart=' + ' '.join(argument(v) for v in command)
            + '\nRestart=on-failure\nRestartSec=3\nTimeoutStartSec=15\nTimeoutStopSec=12\nKillMode=control-group\n'
              'UMask=0077\n[Install]\nWantedBy=default.target\n')
    (directory / (name + '.service')).write_text(unit)
    (directory / (name + '.service')).chmod(0o600)
    config = {'version': 1, 'name': name, 'profile': str(root), 'socket': str(socket_path),
              'python': sys.executable, 'program': list(program or []),
              'unit_sha256': hashlib.sha256(unit.encode()).hexdigest()}
    write_private(directory / 'service.json', config)
    return {'directory': str(directory), 'manager': str(directory / 'manage.py'),
            'name': name, 'installed': False, 'scope': 'systemd-user',
            'commands': {action: [sys.executable, str(directory / 'manage.py'), action]
                         for action in ('install', 'status', 'rollback')}}


def write_private(path, value):
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as output:
        json.dump(value, output, indent=2)


def remember_gateway(root, config):
    path = Path(config['socket'])
    info = path.lstat()
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError('Gateway endpoint is not an owned socket.')
    record = {'socket': str(path), 'device': info.st_dev, 'inode': info.st_ino}
    with tempfile.NamedTemporaryFile(mode='w', dir=root, prefix='.gateway-owner-', delete=False) as handle:
        temporary = Path(handle.name)
        json.dump(record, handle)
    try:
        os.replace(temporary, root / 'gateway-owner.json')
    finally:
        temporary.unlink(missing_ok=True)


def remove_stale_gateway(root, config):
    path = Path(config['socket'])
    if not path.exists() and not path.is_symlink():
        return
    record_path = root / 'gateway-owner.json'
    if not record_path.is_file() or record_path.is_symlink() or record_path.stat().st_mode & 0o077:
        raise ValueError('Existing endpoint has no private ownership receipt; refusing to remove it.')
    record = json.loads(record_path.read_text())
    info = path.lstat()
    expected = (record['device'], record['inode'])
    if (record['socket'] != str(path) or (info.st_dev, info.st_ino) != expected
            or info.st_uid != os.getuid() or not stat.S_ISSOCK(info.st_mode)):
        raise ValueError('Socket identity changed; refusing to remove it.')
    with socket.socket(socket.AF_UNIX) as probe:
        probe.settimeout(1)
        try:
            probe.connect(str(path))
        except OSError as exc:
            if exc.errno not in (errno.ECONNREFUSED, errno.ENOENT):
                raise
        else:
            raise ValueError('Gateway endpoint is still active; refusing to remove it.')
    try:
        current = path.lstat()
        if (current.st_dev, current.st_ino) != expected:
            raise ValueError('Socket changed during cleanup.')
        path.unlink()
    except FileNotFoundError:
        pass


def load(root):
    private_directory(root)
    path = root / 'service.json'
    if path.is_symlink() or path.stat().st_mode & 0o077:
        raise ValueError('Service configuration must be a private regular file.')
    config = json.loads(path.read_text())
    if config.get('version') != 1 or not re.fullmatch(r'zhibi-[a-zA-Z0-9][a-zA-Z0-9_.-]{0,55}', config['name']):
        raise ValueError('Invalid service configuration.')
    return config


def ctl(*args, check=True):
    return subprocess.run(['systemctl', '--user', *args], capture_output=True, text=True, check=check)


def target_path(config):
    config_home = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))).expanduser().absolute()
    directory = config_home / 'systemd/user'
    if any(p.is_symlink() for p in (directory, *directory.parents)):
        raise ValueError('User unit directory cannot contain symlinks.')
    return directory / (config['name'] + '.service')


def digest(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError('Expected a regular unit file, not an alias.')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def status(config):
    result = ctl('show', config['name'], '-p', 'ActiveState,SubState,MainPID,FragmentPath', check=False)
    return {'name': config['name'], 'properties': result.stdout.strip(), 'exit_status': result.returncode}


def install(root, config):
    ctl('show-environment')  # Fail before writing when the user manager is unavailable.
    target = target_path(config)
    name = config['name']
    source = root / (name + '.service')
    if digest(source) != config['unit_sha256']:
        raise ValueError('Generated unit changed; export a new bundle for the changed configuration.')
    loaded = ctl('show', name, '-p', 'LoadState', '--value', check=False)
    if target.exists() or target.is_symlink() or loaded.stdout.strip() != 'not-found':
        raise ValueError('Service name already exists; choose a new name. Existing services are not replaced.')
    if (root / 'receipt.json').exists():
        raise ValueError('This bundle already has a deployment receipt; use status or rollback.')
    subprocess.run(['systemd-analyze', '--user', 'verify', str(source)], check=True, capture_output=True, text=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    receipt = {'target': str(target), 'unit_sha256': config['unit_sha256'], 'name': name}
    # Record the exact target before mutation; retries never adopt unrelated units.
    write_private(root / 'receipt.json', receipt)
    created = False
    try:
        fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        created = True
        with os.fdopen(fd, 'wb') as output:
            output.write(source.read_bytes())
        ctl('daemon-reload')
        ctl('enable', '--now', name)
        time.sleep(2)
        ctl('is-active', '--quiet', name)
    except BaseException:
        if created:
            rollback(root, config)
        raise
    return {'installed': True, **status(config), 'receipt': str(root / 'receipt.json')}


def rollback(root, config):
    receipt_path = root / 'receipt.json'
    if receipt_path.is_symlink() or receipt_path.stat().st_mode & 0o077:
        raise ValueError('Receipt permissions are invalid.')
    receipt = json.loads(receipt_path.read_text())
    target = target_path(config)
    if (receipt['target'] != str(target) or receipt['name'] != config['name']
            or receipt['unit_sha256'] != config['unit_sha256']):
        raise ValueError('Receipt does not match this service and user configuration directory.')
    if target.exists() or target.is_symlink():
        if digest(target) != receipt['unit_sha256']:
            raise ValueError('Installed unit changed; refusing to remove it.')
        dropins = ctl('show', config['name'], '-p', 'DropInPaths', '--value').stdout.strip()
        if dropins:
            raise ValueError('Service has new drop-ins; inspect those changes before rollback.')
        ctl('disable', '--now', config['name'])
        target.unlink()
        ctl('daemon-reload')
        ctl('reset-failed', config['name'], check=False)
    return {'removed': True, 'name': config['name'], 'receipt': str(receipt_path)}


def supervise(root, config):
    children = []
    stopping = False
    def stop(signum, frame):
        nonlocal stopping
        stopping = True
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    for sig in previous:
        signal.signal(sig, stop)
    try:
        remove_stale_gateway(root, config)
        gateway = subprocess.Popen([config['python'], str(root / 'gateway.py'), '--socket', config['socket']],
                                   stdout=subprocess.PIPE, text=True)
        children.append(gateway)
        ready, _, _ = select.select([gateway.stdout], [], [], 10)
        announcement = gateway.stdout.readline() if ready else ''
        if not announcement or json.loads(announcement).get('status') != 'ready':
            raise ValueError('Gateway did not become ready; existing socket paths are not removed automatically.')
        gateway.stdout.close()
        remember_gateway(root, config)
        with socket.socket(socket.AF_UNIX) as probe:
            probe.settimeout(2)
            probe.connect(config['socket'])
            probe.sendall(b'\x05\x01\x00')
            response = b''
            while len(response) < 2:
                chunk = probe.recv(2 - len(response))
                if not chunk:
                    raise ValueError('Gateway closed during readiness check.')
                response += chunk
            if response != b'\x05\x00':
                raise ValueError('Gateway failed the SOCKS5 readiness check.')
        if config['program']:
            app = subprocess.Popen([config['python'], str(Path(config['profile']) / 'run.py'), '--', *config['program']])
            children.append(app)
        notify = os.environ.get('NOTIFY_SOCKET')
        if notify:
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as notifier:
                notifier.connect('\0' + notify[1:] if notify.startswith('@') else notify)
                notifier.sendall(b'READY=1')
        while not stopping:
            for child in children:
                code = child.poll()
                if code is not None:
                    return 1 if child is gateway else (code if code >= 0 else 1)
            time.sleep(0.1)
        return 0
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
        for child in reversed(children):
            try:
                child.wait(timeout=4)
            except subprocess.TimeoutExpired:
                child.kill(); child.wait()
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        if children:
            remove_stale_gateway(root, config)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('install', 'status', 'rollback', 'supervise'))
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    config = load(root)
    if args.action == 'supervise':
        return supervise(root, config)
    result = {'install': lambda: install(root, config), 'status': lambda: status(config),
              'rollback': lambda: rollback(root, config)}[args.action]()
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
