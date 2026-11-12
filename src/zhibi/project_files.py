"""Single-file transfer over SSH, with exclusive destinations and no sync conflicts."""
import base64
import json
import os
import shlex
import stat
import subprocess
from pathlib import Path, PurePosixPath

from . import remote
from .models import InputError


def execute(command, **kwargs):
    try:
        return subprocess.run(command, **kwargs)
    except subprocess.TimeoutExpired as exc:
        raise InputError("文件传输超时；请检查网络后重试。") from exc


# The guest resolves parents and refuses escape through symlinks; no recursive copy.
HELPER = r'''
import base64, hashlib, json, os, pathlib, sys, tempfile
c = json.loads(base64.b64decode(sys.argv[1]))
root = pathlib.Path(c['root']).resolve(strict=True)
p = root / c['relative']
parent = p.parent.resolve(strict=True)
parent.relative_to(root)
p = parent / p.name
if c['action'] == 'download':
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
    import stat
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise RuntimeError('not a regular file')
    with os.fdopen(fd, 'rb') as f:
        while True:
            b = f.read(65536)
            if not b: break
            sys.stdout.buffer.write(b)
else:
    fd, tmp = tempfile.mkstemp(prefix='.zhibi-transfer-', dir=parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            h = hashlib.sha256()
            n = 0
            while True:
                b = sys.stdin.buffer.read(65536)
                if not b: break
                h.update(b); n += len(b); f.write(b)
            f.flush(); os.fsync(f.fileno())
        if n != c['size'] or h.hexdigest() != c['sha256']:
            raise RuntimeError('incomplete transfer')
        os.link(tmp, p)
    finally:
        os.unlink(tmp)
'''


def remote_command(data, action, relative, **metadata):
    path = PurePosixPath(relative)
    if path.is_absolute() or not path.parts or ".." in path.parts or "\0" in relative:
        raise InputError("传输目标必须是项目内的相对文件路径，不允许 ..。")
    config = {"root": data["workdir"], "relative": str(path), "action": action, **metadata}
    encoded = base64.b64encode(json.dumps(config).encode()).decode()
    return "python3 -c " + shlex.quote(HELPER) + " " + shlex.quote(encoded)


def transfer(args, data):
    import hashlib
    local = Path(args.local).expanduser().absolute()
    # Validate before opening a destination or making any connection.
    script = remote_command(data, args.action, args.remote_file)
    result = {"action": args.action, "applied": False, "overwrite": False,
              "remote_relative_path": args.remote_file}
    if not args.apply:
        return result
    item = remote.target(**data["target"])
    if args.action == "upload":
        fd = os.open(local, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise InputError("只能传输普通文件。")
            digest = hashlib.sha256()
            size = 0
            while True:
                block = source.read(65536)
                if not block:
                    break
                digest.update(block)
                size += len(block)
            source.seek(0)
            script = remote_command(data, args.action, args.remote_file, size=size, sha256=digest.hexdigest())
            done = execute(remote.ssh_argv(item, script), stdin=source,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=120)
    else:
        fd = os.open(local, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as destination:
                done = execute(remote.ssh_argv(item, script), stdout=destination,
                                      stderr=subprocess.PIPE, timeout=120)
            if done.returncode:
                local.unlink()
        except BaseException:
            local.unlink(missing_ok=True)
            raise
    if done.returncode:
        raise InputError("文件传输失败。检查 SSH、远端 Python、目录权限及目标是否已存在；未覆盖已有文件。")
    result["applied"] = True
    return result
