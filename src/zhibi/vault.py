"""Optional encrypted local profile archives and reversible cache quarantine.

Only an explicitly chosen, closed directory is processed; never discover or log accounts.
"""
import getpass
import io
import json
import os
import secrets
import shutil
import stat
import warnings
import zipfile
from pathlib import Path

from .models import InputError, now, read_json
from .storage import create_run, write

MAGIC = b"ZHIBI-VAULT-1\x00"
LIMIT = 256 * 1024 * 1024
CACHES = ("Cache", "Code Cache", "GPUCache", "Service Worker/CacheStorage")


def root_path(value, closed):
    path = Path(value).expanduser().absolute()
    if not closed:
        raise InputError("请先关闭此环境，再在自己的终端加 --closed 确认；工具不强制退出浏览器。")
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_dir() or path == Path.home() or path in Path.home().parents or len(path.parts) < 4:
        raise InputError("仅支持明确选择的专用子目录，不能是主目录、系统根目录或符号链接。")
    if any((path / name).exists() or (path / name).is_symlink() for name in ("SingletonLock", "lockfile", "parent.lock", ".parentlock")):
        raise InputError("目录存在运行锁；请正常关闭应用并核实，不自动删除锁。")
    return path


def password(confirm=False):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            value = getpass.getpass("本机备份口令（隐藏输入，不能发给 Agent）：")
            if len(value) < 12:
                raise InputError("备份口令至少 12 个字符。")
            if confirm and getpass.getpass("再次输入口令：") != value:
                raise InputError("两次口令不一致。")
            return value
    except (getpass.GetPassWarning, EOFError):
        raise InputError("必须在自己的交互终端隐藏输入口令；没有保存明文口令。") from None


def crypto():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
        return AESGCM, Scrypt
    except ImportError:
        raise InputError("此可选功能需要 cryptography：在专用 Python 环境安装 zhibi[vault]。") from None


def encrypt(payload, secret):
    AESGCM, Scrypt = crypto()
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    key = Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(secret.encode())
    header = MAGIC + salt + nonce
    return header + AESGCM(key).encrypt(nonce, payload, header)


def decrypt(data, secret):
    AESGCM, Scrypt = crypto()
    if not data.startswith(MAGIC) or len(data) < len(MAGIC) + 44 or len(data) > LIMIT + 1024 * 1024:
        raise InputError("归档格式或大小无效。")
    offset = len(MAGIC)
    salt, nonce = data[offset:offset + 16], data[offset + 16:offset + 28]
    key = Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(secret.encode())
    try:
        return AESGCM(key).decrypt(nonce, data[offset + 28:], data[:offset + 28])
    except Exception:
        raise InputError("口令错误或归档认证失败；未修改目标环境。") from None


def pack(root):
    entries, size = [], 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise InputError("归档包含符号链接或特殊文件，拒绝自动处理。")
        if path.is_file():
            size += path.stat().st_size
            entries.append(path)
        if size > LIMIT or len(entries) > 10000:
            raise InputError("归档超过 256 MiB 或一万个文件；请缩小专用目录范围。")
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as z:
        for path in entries:
            z.write(path, path.relative_to(root).as_posix())
    return stream.getvalue(), len(entries)


def unpack(payload, destination):
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        entries = z.infolist()
        if len(entries) > 10000 or sum(e.file_size for e in entries) > LIMIT:
            raise InputError("归档内容超出限制。")
        seen = set()
        for entry in entries:
            path = Path(entry.filename)
            if path.is_absolute() or not path.parts or any(p in ("..", ".") for p in path.parts) or "\\" in entry.filename or entry.filename in seen or stat.S_ISLNK(entry.external_attr >> 16):
                raise InputError("归档路径无效或包含符号链接。")
            seen.add(entry.filename)
        for entry in entries:
            path = destination / entry.filename
            if entry.is_dir():
                path.mkdir(parents=True, exist_ok=True, mode=0o700)
            else:
                path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, "wb") as f:
                    f.write(z.read(entry))


def backup(root, out, closed=False, secret=None):
    source = root_path(root, closed)
    directory = create_run(out)
    if source in directory.parents:
        raise InputError("归档输出必须在源目录之外。")
    payload, count = pack(source)
    secret = secret or password(True)
    encrypted = encrypt(payload, secret)
    if decrypt(encrypted, secret) != payload:
        raise InputError("加密往返核验失败。")
    fd = os.open(directory / "profile.enc", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(encrypted)
    write(directory / "receipt.json", {"format": "zhibi-vault-1", "at": now(), "files": count, "encrypted": True, "roundtrip_verified": True})
    return {"directory": str(directory), "files": count, "encrypted": True, "roundtrip_verified": True}


def restore(archive, root, closed=False, apply=False, empty=False, secret=None):
    target = root_path(root, closed)
    if not apply:
        return {"action": "empty_workspace" if empty else "restore_archive", "target": str(target), "requires_closed": True, "old_directory_preserved": True, "applied": False}
    payload = None
    if not empty:
        path = Path(archive)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > LIMIT + 1024 * 1024:
            raise InputError("归档路径无效。")
        payload = decrypt(path.read_bytes(), secret or password())
    staging = target.with_name(target.name + ".zhibi-staging-" + secrets.token_hex(6))
    previous = target.with_name(target.name + ".zhibi-previous-" + secrets.token_hex(6))
    staging.mkdir(mode=0o700)
    try:
        if payload is not None:
            unpack(payload, staging)
        os.rename(target, previous)
        try:
            os.rename(staging, target)
        except OSError:
            os.rename(previous, target)
            raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    previous.chmod(0o700)
    # Previous data remains intact for recovery. Never upload archives or directory contents.
    receipt = {"format": "zhibi-workspace-swap-1", "at": now(), "target": str(target), "previous": str(previous), "applied": True}
    write(previous.with_name(previous.name + ".receipt.json"), receipt)
    return {"applied": True, "previous_directory": str(previous), "target": str(target), "previous_data_preserved": True}


def cache(root, closed=False, apply=False, out=None):
    target = root_path(root, closed)
    found = []
    for name in CACHES:
        path = target / name
        if path.exists():
            if any(p.is_symlink() for p in (path, *path.parents)):
                raise InputError("缓存路径经过符号链接，拒绝处理。")
            found.append(name)
    if not apply:
        return {"cache_directories": found, "account_storage_selected": False, "applied": False}
    destination = create_run(out)
    if target == destination or target in destination.parents:
        raise InputError("缓存隔离目录必须在浏览器目录之外。")
    moved = []
    try:
        for name in found:
            saved = destination / name
            saved.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.rename(target / name, saved)
            moved.append(name)
    except OSError:
        for name in reversed(moved):
            os.rename(destination / name, target / name)
        raise InputError("隔离失败，已尝试还原已移动的缓存。") from None
    write(destination / "receipt.private.json", {"format": "zhibi-cache-1", "root": str(target), "moved": moved})
    return {"directory": str(destination), "cache_directories": moved, "account_storage_selected": False, "applied": True}


def cache_restore(directory, closed=False, apply=False):
    directory = Path(directory).absolute()
    record = read_json(directory / "receipt.private.json")
    if record.get("format") != "zhibi-cache-1" or not isinstance(record.get("moved"), list) or any(n not in CACHES for n in record["moved"]):
        raise InputError("缓存恢复记录无效。")
    target = root_path(record["root"], closed)
    for name in record["moved"]:
        if (target / name).exists() or (target / name).is_symlink() or not (directory / name).is_dir() or (directory / name).is_symlink():
            raise InputError("缓存路径已经变化，拒绝覆盖；关闭后选择手工保留哪份缓存。")
    if apply:
        for name in record["moved"]:
            os.rename(directory / name, target / name)
    return {"restored": bool(apply), "cache_count": len(record["moved"])}


def register(sub):
    p = sub.add_parser("workspace", help="可选本地目录归档、恢复、空工作区及缓存隔离；不发现账号")
    p.add_argument("action", choices=("backup", "restore", "empty", "cache", "cache-restore"))
    p.add_argument("--root")
    p.add_argument("--archive")
    p.add_argument("--closed", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--out")


def dispatch(args):
    if args.action == "cache-restore":
        if not args.archive:
            raise InputError("需要 --archive 指定隔离目录。")
        return cache_restore(args.archive, args.closed, args.apply)
    if not args.root:
        raise InputError("需要 --root 指定专用目录。")
    if args.action == "backup":
        return backup(args.root, args.out, args.closed)
    if args.action == "cache":
        return cache(args.root, args.closed, args.apply, args.out)
    if args.action == "restore" and not args.archive:
        raise InputError("需要 --archive 指定加密归档。")
    return restore(args.archive, args.root, args.closed, args.apply, args.action == "empty")
