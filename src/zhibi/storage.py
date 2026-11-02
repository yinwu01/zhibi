"""New private directories; refuse overwrites and symlink destinations."""
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .models import InputError


def create_run(destination=None):
    if destination:
        path = Path(destination).expanduser().absolute()
    else:
        base = Path.home() / ".zhibi"
        if base.is_symlink():
            raise InputError("数据目录不能是符号链接。")
        base.mkdir(mode=0o700, exist_ok=True)
        if os.name == "posix":
            base.chmod(0o700)
        tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = base / (tag + "-" + uuid.uuid4().hex[:8])
    try:
        path.mkdir(mode=0o700, parents=False, exist_ok=False)
    except FileExistsError:
        raise InputError("输出目录已存在；请选择新目录，避免覆盖旧报告。") from None
    return path


def write(path, content):
    path = Path(path)
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False, indent=2) + "\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(str(path), flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
