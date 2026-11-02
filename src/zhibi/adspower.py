"""Optional AdsPower Local API adapter. No cookies, profile creation or cloud sharing."""
import json
import re
import time
import urllib.parse
import urllib.request

from .diagnostics import private_config
from .models import InputError, now, read_json
from .storage import create_run, write
from .transport import NoRedirect

FIELDS = {"timezone", "automatic_timezone", "language", "language_switch", "page_language_switch", "webrtc", "location", "hardware_concurrency", "device_memory", "ua"}


def validate_patch(patch):
    if not isinstance(patch, dict) or not patch or set(patch) - FIELDS:
        raise InputError("AdsPower patch 只能包含受支持的明确设置，不接收账号或 Cookie。")
    for key, value in patch.items():
        if key == "language":
            valid = isinstance(value, list) and 0 < len(value) <= 20 and all(isinstance(s, str) and re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", s) for s in value)
        else:
            valid = isinstance(value, str) and 0 < len(value) <= (1000 if key == "ua" else 100) and not any(ord(c) < 32 for c in value)
            if key in {"automatic_timezone", "language_switch", "page_language_switch"}:
                valid = value in ("0", "1")
            elif key == "webrtc":
                valid = value in {"forward", "proxy", "local", "disabled", "disableUDP"}
            elif key == "location":
                valid = value in {"ask", "allow", "block"}
            elif key in {"hardware_concurrency", "device_memory"}:
                valid = value == "default" or isinstance(value, str) and value.isdigit() and 1 <= int(value) <= 128
        if not valid:
            raise InputError("AdsPower 配置值无效。")
    return patch


class Client:
    def __init__(self, config, opener=None):
        if set(config) - {"port", "api_key", "profile_id", "patch"}:
            raise InputError("AdsPower 本机配置有未知字段。")
        port = config.get("port", 50325)
        if type(port) is not int or not 1024 <= port <= 65535:
            raise InputError("AdsPower 端口无效。")
        self.profile_id = config.get("profile_id", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", self.profile_id):
            raise InputError("请在本机配置现有 profile_id。")
        self.key = config.get("api_key")
        if self.key is not None and (not isinstance(self.key, str) or not re.fullmatch(r"[!-~]{1,512}", self.key)):
            raise InputError("AdsPower API Key 格式无效。")
        self.base = "http://127.0.0.1:" + str(port)
        self.opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        self.last = 0

    def request(self, action, patch=None):
        time.sleep(max(0, 1 - (time.monotonic() - self.last)))
        base = "/api/v2/browser-profile/"
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = "Bearer " + self.key
        if action == "active":
            url, payload = self.base + base + "active?" + urllib.parse.urlencode({"profile_id": self.profile_id}), None
        elif action == "list":
            url, payload = self.base + base + "list", {"profile_id": [self.profile_id], "page": 1, "limit": 10}
        elif action == "update":
            url, payload = self.base + base + "update", {"profile_id": self.profile_id, "fingerprint_config": validate_patch(patch)}
        else:
            raise InputError("AdsPower 操作不在允许范围。")
        try:
            self.last = time.monotonic()
            req = urllib.request.Request(url, data=json.dumps(payload).encode() if payload is not None else None, headers=headers)
            with self.opener.open(req, timeout=8) as response:
                raw = response.read(131073)
            if len(raw) > 131072:
                raise ValueError()
            data = json.loads(raw)
            if data.get("code") != 0:
                raise ValueError()
            return data.get("data")
        except (OSError, ValueError, TypeError, AttributeError):
            raise InputError("AdsPower 本机 API 不可用、无权限或响应无效；保留手动打开探针的免 API 路径。") from None

    def inspect(self):
        status = self.request("active")
        active = status.get("status") if isinstance(status, dict) else None
        if active not in ("Active", "Inactive"):
            raise InputError("AdsPower 未返回可验证的运行状态。")
        data = self.request("list")
        entries = data.get("list") if isinstance(data, dict) else data
        if not isinstance(entries, list):
            raise InputError("AdsPower 未返回环境列表。")
        matches = [p for p in entries if isinstance(p, dict) and p.get("profile_id", p.get("user_id")) == self.profile_id]
        if len(matches) != 1:
            raise InputError("无法唯一定位所选现有环境。")
        fingerprint = matches[0].get("fingerprint_config")
        safe = {k: v for k, v in fingerprint.items() if k in FIELDS} if isinstance(fingerprint, dict) else {}
        if safe:
            validate_patch(safe)
        return {"active": active == "Active", "fingerprint": safe, "configuration_readable": bool(safe)}


def run(action, config_path, apply=False, out=None, receipt=None, client=None):
    config = private_config(config_path)
    client = client or Client(config)
    before = client.inspect()
    directory = create_run(out)
    write(directory / "before.private.json", before)
    if action == "inspect":
        return {"directory": str(directory), "active": before["active"], "configuration_readable": before["configuration_readable"], "cookies_read": False}
    if before["active"]:
        raise InputError("请先正常关闭所选环境再修改；不会强制停止正在使用的浏览器。")
    if action == "restore":
        old = read_json(receipt) if receipt else {}
        if old.get("format") != "zhibi-adspower-change-1" or old.get("profile_id") != config.get("profile_id"):
            raise InputError("恢复记录不属于所选环境。")
        patch = old["before"]
        if any(before["fingerprint"].get(k) != v for k, v in old["requested"].items()):
            raise InputError("设置已发生后续变更，拒绝直接覆盖。")
    else:
        patch = validate_patch(config.get("patch"))
    if any(k not in before["fingerprint"] for k in patch):
        raise InputError("API 没有返回待修改项的原值，无法保证恢复；不执行修改。")
    plan = {"format": "zhibi-adspower-change-1", "profile_id": config["profile_id"], "at": now(),
            "before": {k: before["fingerprint"][k] for k in patch}, "requested": patch}
    write(directory / "plan.private.json", plan)
    if not apply:
        return {"directory": str(directory), "applied": False, "changed_fields": sorted(patch)}
    client.request("update", patch)
    after = client.inspect()
    verified = all(after["fingerprint"].get(k) == v for k, v in patch.items())
    write(directory / "receipt.private.json", dict(plan, verified=verified))
    return {"directory": str(directory), "configuration_verified": verified, "browser_effect_verified": False,
            "next_step": "重新打开同一环境运行 session；API 保存成功不等于浏览器已生效。"}


def register(sub):
    p = sub.add_parser("adspower", help="可选本机 API：读取配置、按明确 patch 更新或恢复；可能需付费 API 权限")
    p.add_argument("action", choices=("inspect", "update", "restore"))
    p.add_argument("--config", required=True)
    p.add_argument("--receipt")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--out")
