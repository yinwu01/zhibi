"""Optional browser observations: private facts and a fixed-vocabulary Agent summary."""
import re

from .models import InputError, exact, timestamp

LABELS = {"locale": "时区偏移与语言变体", "identity": "浏览器与设备识别", "runtime": "浏览器运行容器",
          "hardware": "浏览器可用 CPU", "fonts": "固定字体探测", "permissions": "本页定位权限"}
STATES = {"ok", "skipped", "unsupported", "error", "timeout"}
FONTS = ["Microsoft YaHei", "Microsoft JhengHei", "PingFang SC", "Hiragino Sans GB", "STHeiti", "STSong", "SimSun", "SimHei", "Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Micro Hei", "PingFang TC", "Heiti TC", "Hiragino Sans CNS", "Noto Sans CJK TC", "Source Han Sans TC", "MingLiU", "PMingLiU", "MiSans", "HarmonyOS Sans", "OPPO Sans", "vivo Sans", "Honor Sans", "Alibaba PuHuiTi", "WPS Fangzheng", "FZLanTingHeiS"]
BROWSER_TOKENS = "micromessenger mqqbrowser qqbrowser quark ucbrowser ucweb baiduboxapp baidubrowser miuibrowser mibrowser huaweibrowser heytapbrowser oppobrowser vivobrowser 360se 360ee qihoobrowser sogoumobilebrowser 2345browser lbbrowser".split()
DEVICE_TOKENS = "harmonyos huawei honor xiaomi redmi oppo vivo realme oneplus miui".split()
ADVICE = {
    "locale": "核对是否符合自己的设置；语言和时区本身不需要改成英文或美国时间。",
    "identity": "这是 UA / Client Hints 自报及推断；版本和 Emoji 系列均不证明真实设备。",
    "runtime": "核对是否为预期的浏览器；没有标记不证明没有自动化或虚拟化。",
    "hardware": "这是浏览器可用逻辑处理器数，可能被隐私设置限制；不是 CPU 型号或真实性检测。",
    "fonts": "只测 26 个固定候选的文字宽度；匹配是迹象，不是完整字体清单，也不说明所在地。",
    "permissions": "只查询当前探针页面的权限，没有请求坐标；目标站点的权限需在该站点设置核对。",
}


def member(value, options):
    if value is not None and type(value) is not str:
        raise InputError("浏览器深入检查的值类型无效。")
    if value not in options:
        raise InputError("浏览器深入检查的值不在允许范围。")


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise InputError("浏览器深入检查的数值无效。")


def validate_details(data):
    exact(data, {"at", "checks"}, {"at", "checks"})
    timestamp(data["at"])
    exact(data["checks"], set(LABELS), set(LABELS))
    for key, item in data["checks"].items():
        exact(item, {"status", "facts"}, {"status", "facts"})
        member(item["status"], STATES)
        f = item["facts"]
        if item["status"] != "ok":
            if f is not None:
                raise InputError("未取得的浏览器检查不能携带读数。")
            continue
        fields = {"locale": {"utcOffsetMinutes", "variants"}, "identity": {"browser", "version", "engine", "os", "device", "browserToken", "deviceToken", "brands", "emojiFamily"},
                  "runtime": {"webdriver", "webview", "headless"}, "hardware": {"logicalProcessors"},
                  "fonts": {"detected", "tested"}, "permissions": {"geolocation"}}[key]
        exact(f, fields, fields)
        if key == "locale":
            integer(f["utcOffsetMinutes"], -840, 840)
            if not isinstance(f["variants"], list) or len(f["variants"]) > 3 or any(type(v) is not str for v in f["variants"]) or sorted(set(f["variants"])) != f["variants"]:
                raise InputError("语言变体列表无效。")
            for v in f["variants"]:
                member(v, {"simplified", "traditional", "unspecified"})
        elif key == "identity":
            for field, values in (("browser", {"Edge", "Opera", "Firefox", "Chrome", "Safari", "unknown"}), ("engine", {"WebKit", "Gecko", "Blink", "unknown"}),
                                  ("os", {"HarmonyOS", "Android", "iOS", "macOS", "Windows", "Linux", "unknown"}), ("device", {"mobile", "tablet", "desktop", "unknown"}),
                                  ("browserToken", [None] + BROWSER_TOKENS), ("deviceToken", [None] + DEVICE_TOKENS), ("emojiFamily", {"Apple", "Android", "Windows", "unknown"})):
                member(f[field], values)
            if f["version"] is not None and (not isinstance(f["version"], str) or not re.fullmatch(r"[0-9.]{1,40}", f["version"])):
                raise InputError("浏览器版本无效。")
            if not isinstance(f["brands"], list) or len(f["brands"]) > 10:
                raise InputError("Client Hints 列表无效。")
            for brand in f["brands"]:
                exact(brand, {"brand", "version"}, {"brand", "version"})
                for k, limit in (("brand", 80), ("version", 40)):
                    if not isinstance(brand[k], str) or len(brand[k]) > limit or any(ord(c) < 32 for c in brand[k]):
                        raise InputError("Client Hints 内容无效。")
        elif key == "runtime":
            if any(type(v) is not bool for v in f.values()):
                raise InputError("运行容器标记无效。")
        elif key == "hardware":
            integer(f["logicalProcessors"], 1, 65536)
        elif key == "fonts":
            if type(f["tested"]) is not int or f["tested"] != len(FONTS) or not isinstance(f["detected"], list) or len(f["detected"]) > len(FONTS) or any(type(v) is not str or v not in FONTS for v in f["detected"]) or len(set(f["detected"])) != len(f["detected"]):
                raise InputError("字体检测超出固定候选范围。")
        else:
            member(f["geolocation"], {"granted", "denied", "prompt"})
    return data


def summarize(data):
    if data is None:
        return None
    validate_details(data)
    return {"at": data["at"], "checks": {k: v["status"] for k, v in data["checks"].items()}}


def validate_summary(data):
    if data is None:
        return
    exact(data, {"at", "checks"}, {"at", "checks"})
    timestamp(data["at"])
    exact(data["checks"], set(LABELS), set(LABELS))
    for value in data["checks"].values():
        member(value, STATES)


def rows(summary):
    """Fixed explanations only; optional observations never change the IP verdict."""
    if summary is None:
        return []
    validate_summary(summary)
    states = {"ok": "已观测", "unsupported": "此浏览器不支持", "error": "读取失败", "timeout": "读取超时"}
    return [[LABELS[k], states[v], ADVICE[k] if v == "ok" else "需要此项时，在实际浏览器重新观察；读取失败不计为风险。"]
            for k, v in summary["checks"].items() if v != "skipped"]


def readings(data):
    """Private, human-facing values. HTML renderer escapes these strings."""
    if data is None:
        return []
    result = []
    for k, item in validate_details(data)["checks"].items():
        if item["status"] != "ok":
            continue
        f = item["facts"]
        if k == "locale":
            value = "UTC{:+g}；中文变体：".format(f["utcOffsetMinutes"] / 60) + (" / ".join({"simplified": "简体", "traditional": "繁体", "unspecified": "未指定"}[v] for v in f["variants"]) or "未自报中文")
        elif k == "identity":
            value = f["browser"] + " " + (f["version"] or "") + " / " + f["engine"] + " / " + f["os"] + " / " + f["device"] + "；UA 标记：" + " / ".join(v for v in (f["browserToken"], f["deviceToken"]) if v) + "；Emoji 系列（UA 推断）：" + f["emojiFamily"] + "；Client Hints：" + " / ".join(b["brand"] + " " + b["version"] for b in f["brands"])
        elif k == "runtime":
            value = "；".join(name + ("有标记" if f[field] else "未见标记") for field, name in (("webdriver", "自动化自报"), ("webview", "内嵌浏览器"), ("headless", "无头浏览器")))
        elif k == "hardware":
            value = str(f["logicalProcessors"]) + " 个浏览器可用逻辑处理器"
        elif k == "fonts":
            value = str(len(f["detected"])) + " / 26 个候选有匹配迹象：" + ("、".join(f["detected"]) or "无")
        else:
            value = {"granted": "本页已获授权", "denied": "本页被拒绝定位", "prompt": "本页需询问授权"}[f["geolocation"]]
        result.append([LABELS[k], value, ADVICE[k]])
    return result


def compact_readings(data):
    """Local result cells: give the actual short reading before technical details."""
    values = {}
    if data is None:
        return values
    full = {row[0]: row[1] for row in readings(data)}
    for key, item in validate_details(data)["checks"].items():
        if item["status"] != "ok":
            continue
        f = item["facts"]
        if key == "identity":
            value = f["browser"] + " " + (f["version"] or "版本未知") + " / " + f["os"]
        elif key == "runtime":
            value = "、".join(label for field, label in (("webdriver", "自动化自报"), ("webview", "WebView 标记"), ("headless", "无头标记")) if f[field]) or "未见所测三类标记"
        elif key == "fonts":
            value = str(len(f["detected"])) + " / 26 个候选匹配"
        else:
            value = full[LABELS[key]]
        values[LABELS[key]] = value
    return values
