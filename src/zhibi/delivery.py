"""Optional redacted exports, local comparisons, and reversible Skill updates."""
import hashlib
import json
import os
import secrets
import shutil
import stat
import tempfile
import zipfile
from html import escape
from pathlib import Path

from .models import InputError, read_json
from .storage import create_run, write
from .scan import scan_summary, compare_scans
from .suite import MODULES, STATES
from .diagnostics import SERVICES, SMTP, DNSBL
from .browser_extras import LABELS
from .feeds import SOURCES

ALLOWED = set(MODULES) | {"service:" + key for key in SERVICES} | {"smtp:" + key + ":" + str(port) for key in SMTP for port in (25, 465, 587)} | {"dnsbl:" + key for key in DNSBL} | {"browser:" + key for key in LABELS}
ALLOWED |= {"feed:" + key for key in SOURCES}


def module_states(directory):
    records = read_json(Path(directory) / "modules.private.json")
    if not isinstance(records, dict) or set(records) - ALLOWED:
        raise InputError("未知模块记录。")
    result = {}
    for key, value in records.items():
        if not isinstance(value, dict) or value.get("status") not in STATES or value.get("subject") not in {"collector_host", "selected_browser", "selected_ip", "research_model", "explicit_route"}:
            raise InputError("模块状态无效。")
        result[key] = {"status": value["status"], "subject": value["subject"]}
    return result


def share(directory, out, language="zh"):
    directory = Path(directory)
    core = scan_summary(read_json(directory / "base/report.json"))
    modules = module_states(directory)
    # Construct afresh; never copy user summary JSON or private details into a share artifact.
    data = {"format": "zhibi-share-1", "target": core["target"], "providers": [{"provider": p["provider"], "status": p["status"]} for p in core["providers"]],
            "modules": modules, "private_fields_included": False}
    destination = create_run(out)
    write(destination / "summary.json", data)
    rows = [[p["provider"], p["status"], "Provider coverage only" if language == "en" else "仅分享查询覆盖状态"] for p in data["providers"]]
    rows += [[key, value["status"], "Scope: " + value["subject"]] for key, value in modules.items()]
    headings = ["Check", "Result", "Scope"] if language == "en" else ["检查项", "结果", "范围"]
    title = "Zhibi · Redacted check summary" if language == "en" else "知彼 · 脱敏检查摘要"
    text = "\n".join([title, "", " | ".join(headings), *[" | ".join(row) for row in rows]])
    write(destination / "summary.txt", text)
    table = '<table><thead><tr>' + ''.join('<th>' + escape(h) + '</th>' for h in headings) + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join('<td>' + escape(v) + '</td>' for v in row) + '</tr>' for row in rows) + '</tbody></table>'
    page = '<!doctype html><html lang="' + language + '"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'"><title>' + title + '</title><style>body{font:16px/1.6 system-ui;max-width:1000px;margin:40px auto;padding:20px;color:#173c32;background:#f6f4ec}table{border-collapse:collapse;width:100%}th,td{text-align:left;border-bottom:1px solid #ccd4cc;padding:12px}h1{font-size:30px}</style><h1>' + title + '</h1><p>' + ('Local preview. No IPs, browser attributes, paths, credentials or automatic upload. This summary shows measurement status, not account acceptance.' if language == "en" else '本地预览：不含 IP、浏览器属性、文件路径或凭据；不自动上传。此表仅描述检测状态，不代表账号资格。') + '</p>' + table + '</html>'
    write(destination / "summary.html", page)
    return {"directory": str(destination), "preview": str(destination / "summary.html"), "uploaded": False, "private_fields_included": False}


def compare(before, after, same_context):
    a, b = module_states(before), module_states(after)
    changes = [{"module": k, "before": a.get(k), "after": b.get(k)} for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]
    return {"base": compare_scans(Path(before) / "base", Path(after) / "base", same_context), "module_status_changes": changes,
            "same_context": bool(same_context), "values_compared": False}


def install(archive, expected_digest, destination, replace=False):
    archive, destination = Path(archive), Path(destination).expanduser().absolute()
    if not isinstance(expected_digest, str) or len(expected_digest) != 64 or any(c not in "0123456789abcdef" for c in expected_digest):
        raise InputError("请提供官方发布包 SHA256SUMS 中的完整 SHA-256。")
    if archive.stat().st_size > 16 * 1024 * 1024 or hashlib.sha256(archive.read_bytes()).hexdigest() != expected_digest:
        raise InputError("发布包摘要不匹配；未安装。")
    if destination.name != "zhibi" or any(p.is_symlink() for p in (destination, *destination.parents)):
        raise InputError("目标必须为 zhibi Skill 目录且不能经过符号链接。")
    if destination.exists() and not replace:
        raise InputError("旧版本存在；需要显式 --replace，旧版本会保留以便回退。")
    destination.parent.mkdir(parents=True, exist_ok=True)
    previous = None
    with tempfile.TemporaryDirectory(prefix=".zhibi-install-", dir=destination.parent) as tmp:
        with zipfile.ZipFile(archive) as z:
            entries = z.infolist()
            if len(entries) > 300 or sum(e.file_size for e in entries) > 32 * 1024 * 1024:
                raise InputError("发布包超出预期大小。")
            seen = set()
            for entry in entries:
                p = Path(entry.filename)
                if p.is_absolute() or not p.parts or p.parts[0] != "zhibi" or ".." in p.parts or "\\" in entry.filename or stat.S_ISLNK(entry.external_attr >> 16) or entry.filename in seen:
                    raise InputError("发布包包含无效路径。")
                seen.add(entry.filename)
            needed = {"zhibi/SKILL.md", "zhibi/assets/zhibi-core.pyz", "zhibi/scripts/zhibi.py"}
            if not needed <= seen:
                raise InputError("发布包缺少 Skill 或内置核心。")
            z.extractall(tmp)
        source = Path(tmp) / "zhibi"
        if destination.exists():
            previous = destination.with_name("zhibi.previous-" + secrets.token_hex(6))
            os.rename(destination, previous)
        try:
            os.rename(source, destination)
        except OSError:
            if previous:
                os.rename(previous, destination)
            raise
    return {"installed": str(destination), "previous_version": str(previous) if previous else None, "digest_verified": True, "code_executed": False}


def rollback(destination, previous):
    destination, previous = Path(destination).expanduser().absolute(), Path(previous).expanduser().absolute()
    if destination.name != "zhibi" or previous.parent != destination.parent or not previous.name.startswith("zhibi.previous-"):
        raise InputError("回退路径不属于同一 Skill 安装目录。")
    for path in (destination, previous):
        if any(p.is_symlink() for p in (path, *path.parents)) or not (path / "SKILL.md").is_file() or not (path / "assets/zhibi-core.pyz").is_file():
            raise InputError("Skill 目录不完整或经过符号链接。")
    saved = destination.with_name("zhibi.previous-" + secrets.token_hex(6))
    os.rename(destination, saved)
    try:
        os.rename(previous, destination)
    except OSError:
        os.rename(saved, destination)
        raise
    return {"restored": str(destination), "previous_version": str(saved)}


def register(sub):
    p = sub.add_parser("suite-share", help="生成不含私人读数的 HTML/TXT/JSON 预览，不上传")
    p.add_argument("run_dir"); p.add_argument("--out"); p.add_argument("--language", choices=("zh", "en"), default="zh")
    p = sub.add_parser("suite-compare", help="对比两次完整检测；私人 IP 只由本地核心比较")
    p.add_argument("before"); p.add_argument("after"); p.add_argument("--same-context", action="store_true")
    p = sub.add_parser("skill-install", help="核验发布 ZIP 摘要后安装；升级时保留旧版本")
    p.add_argument("--archive", required=True); p.add_argument("--sha256", required=True); p.add_argument("--dest", required=True); p.add_argument("--replace", action="store_true")
    p = sub.add_parser("skill-rollback", help="恢复同目录中保留的旧 Skill 版本")
    p.add_argument("--dest", required=True); p.add_argument("--previous", required=True)
