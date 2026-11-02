"""Research-only port of CheckCC scoring.ts and regions/index.ts (MIT).

Copyright (c) 2026 yacuo / CheckCC; see bundled third-party.txt.
Pinned revision: 078e7baa1d2a08df28da3f25dacb90e687f4c79f.
Original scores/thresholds are reproduced, not endorsed as platform rules.
"""
import math
import re

REVISION = "078e7baa1d2a08df28da3f25dacb90e687f4c79f"
PROFILES = {
    "cn": {"countries": ["CN"], "timezones": ["Asia/Shanghai", "Asia/Urumqi", "Asia/Chongqing", "Asia/Harbin", "Asia/Kashgar"], "languages": ["zh-cn", "zh-hans", "zh"], "browsers": ["micromessenger", "qqbrowser", "quark", "ucbrowser", "baidu", "miuibrowser", "huaweibrowser", "360"], "devices": ["huawei", "honor", "xiaomi", "redmi", "oppo", "vivo", "harmonyos", "realme", "oneplus"], "weights": dict(country=34, timezone=24, language=18, browser=8, device=8, locale=8)},
    "ru": {"countries": ["RU"], "timezones": ["Europe/Moscow", "Europe/Samara", "Asia/Yekaterinburg", "Asia/Novosibirsk", "Asia/Vladivostok"], "languages": ["ru"], "browsers": ["yabrowser", "yandex", "mail.ru"], "devices": ["android", "windows"], "weights": dict(country=38, timezone=26, language=22, browser=8, device=2, locale=4)},
    "ir": {"countries": ["IR"], "timezones": ["Asia/Tehran"], "languages": ["fa", "fa-ir"], "browsers": [], "devices": [], "weights": dict(country=46, timezone=28, language=20, browser=2, device=0, locale=4)},
}


def evaluate(environment, country=None, region="auto"):
    from .models import InputError
    if region not in {"auto", *PROFILES}:
        raise InputError("CheckCC 研究模板仅支持 auto/cn/ru/ir。")
    candidates = []
    ua = (environment.get("userAgent") or "").lower()
    for code, p in PROFILES.items():
        if region != "auto" and code != region:
            continue
        def includes(value):
            # Preserve upstream's bidirectional substring comparison for reproducibility.
            return any(value.lower() in lang.lower() or lang.lower() in value.lower() for lang in p["languages"])
        scores = {"country": int(bool(country) and country.upper() in p["countries"]),
                  "timezone": int(environment.get("timezone") in p["timezones"]),
                  "language": int(any(includes(lang) for lang in environment.get("languages", []))),
                  "locale": int(bool(environment.get("locale")) and includes(environment["locale"])),
                  "browser": int(any(token in ua for token in p["browsers"])),
                  "device": 0.7 if any(token in ua for token in p["devices"]) else 0}
        available = {"country": country is not None, "timezone": bool(environment.get("timezone")),
                     "language": bool(environment.get("languages")), "locale": bool(environment.get("locale")),
                     "browser": bool(ua), "device": bool(ua)}
        contributions = [{"feature": key, "value": scores[key] if available[key] else None, "weight": weight,
                          "contribution": math.floor(scores[key] * weight + 0.5) if available[key] else None} for key, weight in p["weights"].items() if weight > 0]
        candidates.append({"region": code, "score": min(100, sum(s["contribution"] or 0 for s in contributions)), "contributions": contributions,
                           "complete": all(s["value"] is not None for s in contributions)})
    best = max(candidates, key=lambda x: x["score"])
    score = best["score"]
    return {"model": "CheckCC evaluateAccess", "revision": REVISION, "region": best["region"] if score else None,
            "score": score, "scale": 100, "upstream_status": "restricted" if score >= 70 else "possibly_supported" if score >= 40 else "unknown",
            "contributions": best["contributions"], "candidates": candidates, "complete": best["complete"],
            "platform_rule": False, "changes_zhibi_verdict": False, "country_input_available": country is not None}


def client_signals(environment, details):
    """Port client-engine.ts default weights separately from evaluateAccess's six weights.

    Preserve unavailable inputs instead of recreating the upstream's missing-as-zero UI.
    This is a contribution sum, not a probability and not necessarily bounded by 100.
    """
    from .browser_details import FONTS, BROWSER_TOKENS, DEVICE_TOKENS
    env, checks = environment, (details or {}).get("checks", {})
    langs, locale, ua = env.get("languages", []), env.get("locale") or "", env.get("userAgent") or ""
    probe = (ua + " " + (env.get("brands") or "")).lower()
    device = next((t for t in DEVICE_TOKENS if t in (ua + " " + (env.get("platform") or "")).lower()), None)
    timezone = env.get("timezone")
    font_data = checks.get("fonts", {}).get("facts")
    offset = checks.get("locale", {}).get("facts")
    detected = set(font_data["detected"]) if font_data else set()
    sc, tc, vendor = (len(detected.intersection(group)) for group in (FONTS[:11], FONTS[11:18], FONTS[18:]))
    scores = {
        "timezone": (26, 1 if timezone in ("Asia/Shanghai", "Asia/Urumqi", "Asia/Chongqing", "Asia/Harbin", "Asia/Kashgar") else .6 if timezone in ("Asia/Hong_Kong", "Asia/Macau", "Asia/Taipei") else 0 if timezone else None),
        "language": (20, 1 if any(re.search(r"^zh-cn|zh-hans|^zh$", x, re.I) for x in langs) else .5 if any(re.search(r"^zh", x, re.I) for x in langs) else 0 if langs else None),
        "languageVariant": (12, int(any(re.search(r"zh-(tw|hk|mo)|zh-hant|zh-cn|zh-sg|zh-hans|zh", x, re.I) for x in langs)) if langs else None),
        "chineseFonts": (16, min(1, .75 + .08 * sc) if sc else .5 if tc else 0 if font_data else None),
        "vendorFonts": (10, 1 if vendor >= 2 else .8 if vendor else 0 if font_data else None),
        "domesticBrowser": (8, int(any(t in probe for t in BROWSER_TOKENS)) if ua else None),
        "domesticDevice": (6, 1 if device == "harmonyos" else .7 if device else 0 if ua else None),
        "locale": (6, 1 if re.search(r"zh-cn|zh-hans|^zh$", locale, re.I) else .5 if re.search(r"^zh", locale, re.I) else 0 if locale else None),
        "timezoneOffset": (4, .7 if offset and offset["utcOffsetMinutes"] == 480 else 0 if offset else None),
        "emojiStyle": (4, .4 if re.search("android|harmonyos|windows", ua, re.I) else .2 if re.search("iphone|ipad|mac os", ua, re.I) else 0 if ua else None),
    }
    contributions = [{"feature": k, "weight": weight, "value": value, "contribution": math.floor(value * weight + .5) if value is not None else None} for k, (weight, value) in scores.items()]
    return {"model": "CheckCC collectBrowserSignals", "revision": REVISION, "contributions": contributions,
            "observed_sum": sum(c["contribution"] or 0 for c in contributions), "complete": all(c["value"] is not None for c in contributions),
            "country_server_contribution": "excluded", "platform_rule": False, "changes_zhibi_verdict": False}
