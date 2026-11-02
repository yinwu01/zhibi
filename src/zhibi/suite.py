"""One optional module registry, one local report, no automatic environment mutation."""
import json
import os
from html import escape
from pathlib import Path

from . import diagnostics as d
from .intelligence import FREE_REPUTATION, PROVIDERS, load_keys
from .models import InputError, now, read_json
from .scan import run_scan, scan_plan
from .storage import create_run, write

MODULES = {
    "native": ("系统配置与浏览器对照", "local", [], "不联网；仅当前采集主机的 CPU、系统语言和代理开关"),
    "cli": ("目标客户端安装与版本", "local", [], "可选执行声明客户端的 --version；不登录、不读账号配置"),
    "browser-extras": ("浏览器扩展读数", "import", [], "导入实际浏览器 v4 探针；Canvas/WebGL/离线 Audio/TLS/自建 DNS"),
    "checkcc-model": ("CheckCC 模型对照", "import", [], "固定版本研究模型；不影响知彼结论"),
    "dns": ("终端 DNS / ECS", "network", ["whoami.ds.akahelp.net"], "需要 dig；不能代表浏览器 DNS"),
    "dnsbl": ("DNS 黑名单", "network", list(d.DNSBL.values()), "查询所选 IP；受解析器与名单使用条款限制"),
    "feeds": ("公开 IP 名单本地比对", "network", ["raw.githubusercontent.com", "www.spamhaus.org"], "下载 IPsum / Spamhaus DROP 后本地比对；不把所查 IP 放进查询请求"),
    "services": ("AI 与内容服务连通性", "network", [d.urllib.parse.urlsplit(u).hostname for u in d.SERVICES.values()], "仅公共端点响应；不判断登录资格或流媒体解锁"),
    "smtp": ("邮件端口连通性", "network", list(d.SMTP.values()), "两家 SMTP 服务各 25/465/587；只建立 TCP，不发送邮件"),
    "tls": ("采集主机 TLS / HTTP", "network", ["tls.peet.ws"], "外部观测主机请求；不是浏览器指纹"),
    "route": ("指定代理 / 网卡出口", "network", ["api.ipify.org"], "需本机 route 配置；凭据只经 stdin，避免出现在进程参数"),
    "mmdb": ("离线 IP 数据库", "local", [], "自备合法 MMDB 和可选 maxminddb 包；不自动下载数据库"),
    "expected-egress": ("预期出口核对", "local", [], "需本机 expected_ip 配置；只比较实际所选对象"),
}
STATES = {"ok": "已取得", "review": "需核对", "error": "连接或读取失败", "timeout": "超时", "skipped": "未选择", "unsupported": "当前环境不支持", "configuration_required": "需配置", "invalid_configuration": "配置无效", "missing_dependency": "需安装可选依赖", "not_installed": "未安装", "no_record": "库内未命中", "access_restricted": "查询受限", "invalid_response": "响应格式不符", "unavailable": "工具不可用", "blocked_dependency": "缺少有效观测"}
SERVICE_LABELS = {"chatgpt": "ChatGPT", "tiktok": "TikTok", "disney": "Disney+", "netflix": "Netflix", "youtube": "YouTube", "primevideo": "Prime Video", "reddit": "Reddit"}


def label(key):
    if key in MODULES:
        return MODULES[key][0]
    if key.startswith("service:"):
        return SERVICE_LABELS[key.split(":")[1]] + " · 终端公共端点"
    if key.startswith("smtp:"):
        _, service, port = key.split(":")
        return ("Gmail" if service == "gmail" else "Outlook") + " · 终端 SMTP " + port
    if key.startswith("dnsbl:"):
        return {"spamhaus": "Spamhaus DNS 名单", "spamcop": "SpamCop DNS 名单"}[key.split(":")[1]]
    if key.startswith("feed:"):
        return {"ipsum": "IPsum · 本地名单比对", "spamhaus-drop": "Spamhaus DROP · 本地网段比对"}[key.split(":")[1]]
    from .browser_extras import LABELS
    return LABELS.get(key.partition(":")[2], key)


def catalog():
    return [{"id": k, "label": v[0], "mode": v[1], "recipients": v[2], "scope": v[3], "optional": True, "mutates_environment": False} for k, v in MODULES.items()]


def selection(preset, modules):
    if preset not in {"basic", "all", "custom"} or any(m not in MODULES for m in modules):
        raise InputError("未知检查组合或模块。")
    return list(dict.fromkeys((list(MODULES) if preset == "all" else []) + list(modules)))


def selected_providers(preset, providers=None):
    values = list(PROVIDERS) if preset == "all" else list(FREE_REPUTATION) if preset == "basic" else []
    values = list(dict.fromkeys(values + list(providers or [])))
    if any(p not in PROVIDERS for p in values):
        raise InputError("未知情报来源。")
    return values


def plan(preset="basic", modules=(), network=False, target="agent", providers=None):
    selected = selection(preset, modules)
    return {"preset": preset, "network_enabled": network, "modules": [m for m in catalog() if m["id"] in selected],
            "providers": selected_providers(preset, providers),
            "ip_scan": scan_plan(network, selected_providers(preset, providers) if network else (), network, target),
            "external_requests_without_network": 0, "environment_changes": False,
            "note": "all 包含全部可选只读检查；未配置项给操作提示，不伪造通过。SMTP/服务/TLS 是采集主机路径。"}


def advice(module, state):
    if state == "configuration_required":
        return {"route": "在 suite-config.json 配置 route.proxy_url 或 route.interface，再重跑该模块。", "mmdb": "安装可选 maxminddb 包，并将自己下载的数据库路径填入 mmdb。", "expected-egress": "把自己预期的公网地址填入 expected_ip，再与同一环境复查。", "browser:dns": "可选：按自建 DNS 教程部署权威观测端，在探针填写自己的 HTTPS 观测地址后重测。", "dnsbl:spamhaus": "检测到自定义 dig 配置；请在干净的专用用户环境运行名单检查。", "dnsbl:spamcop": "检测到自定义 dig 配置；请在干净的专用用户环境运行名单检查。"}.get(module, "按可选模块教程补充本机配置后重跑。")
    if state == "blocked_dependency":
        return "在实际使用的浏览器运行高级探针，保存新结果；导入后 15 分钟内查询。"
    if state == "missing_dependency":
        return "此项可选：DNS 检查安装 dig；离线库安装 maxminddb。基础报告仍可使用。"
    if state == "access_restricted":
        return "名单拒绝当前解析器或使用方式；核对其查询政策。不能把错误码当成命中。"
    if module == "checkcc-model":
        return "仅用于复现 CheckCC 的公开权重；分数不是 目标服务 内部规则或封号概率。"
    if module.startswith("service:"):
        return "仅说明采集主机访问公共端点的响应；实际浏览器登录与地区权限仍需在官方产品确认。"
    if module.startswith("smtp:"):
        return "仅测试采集主机 TCP 连通性；未发送邮件，不能代表 IP 邮件信誉。"
    if module.startswith("dnsbl:") or module.startswith("feed:"):
        return "按单个名单解释；PBL 等策略名单不等于恶意。无命中仅限此次查询。"
    if module == "browser:dns":
        return "需自建权威观测端和通配符 HTTPS 证书；看解析器/ECS 是否符合预期，无法由此判断 DoH。"
    if module == "dns":
        return "核对自己的 DNS 服务；这是终端解析链，不能据此断言浏览器没有泄漏。"
    if module in ("tls", "browser:tls"):
        return "TLS 指纹仅对应这个请求和观测端；代理、协议栈与协商均会影响它。"
    if module.startswith("browser:"):
        return "本地渲染或能力观测，不转换为风控分；配置变化后可对照两次结果。"
    if module == "native":
        return "浏览器可限制或改写自报信息；差异需要结合所选配置解释，不等于恶意。"
    if module == "cli":
        return "只使用网页版可跳过；需要 目标客户端 时按官方安装说明安装，再复查版本。" if state == "not_installed" else "确认版本和安装渠道；需要修复时使用维护命令生成操作计划。"
    if module in ("route", "expected-egress"):
        return "与自己预期的出口核对；代理/网卡失败时不回退直连，也不替代浏览器测量。"
    if module == "mmdb":
        return "核对数据库类型和构建日期；地理归属数据库通常不包含欺诈评分。"
    return "按该项具体范围核对，失败不等于存在风险。"


def reading(key, r):
    f = r.get("facts") or {}
    state = STATES.get(r["status"], "读取失败")
    if key.startswith("service:") and "http_status" in f:
        return "HTTP " + str(f["http_status"]) + (" · 端点有响应" if r["status"] == "ok" else " · 访问受限或端点拒绝")
    if key.startswith("smtp:"):
        return "TCP 可连接" if r["status"] == "ok" else state
    if (key.startswith("dnsbl:") or key.startswith("feed:")) and "listed" in f:
        return "名单命中，需核对类型" if f["listed"] else "本次未命中"
    if key == "checkcc-model" and f:
        return str(f["score"]) + "/100 · 上游研究分" + ("（输入不完整）" if not f.get("complete") else "")
    if key == "native" and f:
        return str(f.get("os")) + " / " + str(f.get("logical_processors")) + " 个逻辑处理器"
    if key == "cli" and f:
        return (f.get("version") or state) + " / " + f.get("method", "unknown")
    if key == "browser:canvas" and f:
        return "两次渲染相同" if f["repeated_equal"] else "两次渲染不同"
    if key == "browser:webgl" and f:
        return f["renderer"]
    if key == "browser:audio" and f:
        return str(f["samples"]) + " 个离线样本"
    if key in ("tls", "browser:tls") and f:
        return " / ".join(str(f[k]) for k in ("http_version", "tls_version") if f.get(k))
    if key == "expected-egress" and f:
        return "符合预期" if f["matches"] else "不符合预期"
    return state


def run(preset="basic", modules=(), network=False, browser=None, target="agent", config_path=None, out=None, progress=None, providers=None):
    selected = selection(preset, modules)
    config = d.private_config(config_path) if config_path else {}
    if set(config) - {"route", "expected_ip", "mmdb", "region"}:
        raise InputError("可选检测配置有未知字段。")
    if config.get("expected_ip"):
        d.public_ip(config["expected_ip"])
    if "route" in config:
        d.route(config["route"], runner=lambda *args, **kwargs: (None, "skipped"))
    if config.get("region", "auto") not in {"auto", "cn", "ru", "ir"}:
        raise InputError("地区模型模板仅支持 auto/cn/ru/ir。")
    directory = create_run(out)
    progress = progress or (lambda _: None)
    providers = selected_providers(preset, providers)
    base = run_scan(network=network, providers=providers if network else (), ipv6=network, browser_path=browser,
                    target=target, out=directory / "base", progress=progress)
    snapshot = read_json(directory / "base/snapshot.private.json")
    report = read_json(directory / "base/report.json")
    bundle = snapshot.get("browser") or {}
    address = next((s["ip"] for s in snapshot["subjects"] if s["family"] == 4), None)
    records = {}
    for module in selected:
        progress("可选检查：" + MODULES[module][0])
        if MODULES[module][1] == "network" and not network:
            records[module] = d.result("skipped")
            continue
        if module == "native":
            records[module] = d.native()
            identity = ((bundle.get("details") or {}).get("checks", {}).get("identity") or {}).get("facts")
            if identity:
                host_os = {"Darwin": "macOS"}.get(records[module]["facts"]["os"], records[module]["facts"]["os"])
                records[module]["facts"]["browser_os_matches_host"] = identity["os"] == host_os if identity["os"] != "unknown" else None
        elif module == "cli":
            records[module] = d.cli_installation(os.environ.get("ZHIBI_CLIENT", "").strip() or None)
        elif module == "browser-extras":
            from .browser_extras import LABELS
            extras = bundle.get("extras")
            if not extras:
                records[module] = d.result("blocked_dependency", subject="selected_browser")
            else:
                for key, item in extras["checks"].items():
                    if item["status"] != "skipped":
                        records["browser:" + key] = dict(item, at=extras["at"], subject="selected_browser", recipients=["tls.peet.ws"] if key == "tls" else [d.urllib.parse.urlsplit(item["facts"]["observer"]).hostname] if key == "dns" and item.get("facts") else [])
                if all(item["status"] == "skipped" for item in extras["checks"].values()):
                    records[module] = d.result("skipped", subject="selected_browser")
        elif module == "checkcc-model":
            if not bundle.get("environment"):
                records[module] = d.result("blocked_dependency", subject="selected_browser")
            else:
                from .checkcc_model import evaluate, client_signals
                countries = {r["facts"]["country_code"] for r in report["intelligence"] if r["facts"] and r["facts"]["country_code"]}
                country = next(iter(countries)) if target == "browser" and len(countries) == 1 else None
                records[module] = d.result("ok", evaluate(bundle["environment"], country, config.get("region", "auto")), subject="research_model")
                records[module]["facts"]["client_model"] = client_signals(bundle["environment"], bundle.get("details"))
        elif module == "services":
            for name in d.SERVICES:
                progress("公共端点：" + name)
                records["service:" + name] = d.service(name)
        elif module == "smtp":
            for name in d.SMTP:
                for port in (25, 465, 587):
                    records["smtp:" + name + ":" + str(port)] = d.smtp(name, port)
        elif module == "tls":
            records[module] = d.tls_observer()
        elif module == "route":
            records[module] = d.route(config.get("route"))
        elif module == "dns":
            from .dns import measure
            value = measure(True)
            records[module] = d.result(value["status"] if value["status"] in STATES else "error", value["facts"], MODULES[module][2] if value["attempted"] else [])
        elif module in ("dnsbl", "feeds", "mmdb", "expected-egress"):
            if not address:
                records[module] = d.result("blocked_dependency", subject="selected_ip")
            elif module == "dnsbl":
                for name in d.DNSBL:
                    records["dnsbl:" + name] = d.dnsbl(address, name)
            elif module == "feeds":
                from .feeds import SOURCES, query
                for name in SOURCES:
                    records["feed:" + name] = query(name, address)
            elif module == "mmdb":
                records[module] = d.local_database(address, config.get("mmdb"))
            elif not config.get("expected_ip"):
                records[module] = d.result("configuration_required", subject="selected_ip")
            else:
                matches = address == d.public_ip(config["expected_ip"])
                records[module] = d.result("ok" if matches else "review", {"matches": matches}, subject="selected_ip")
    attention = [label(k) for k, r in records.items() if r["status"] == "review"]
    pending = [label(k) for k, r in records.items() if r["status"] not in {"ok", "review", "skipped", "no_record"}]
    summary = {"format": "zhibi-suite-summary-1", "at": now(), "target": target, "base": base["summary"],
               "modules": {key: {"status": r["status"], "subject": r["subject"]} for key, r in records.items()},
               "optional_attention": attention, "optional_pending": pending,
               "recipients": sorted({h for r in records.values() for h in r["recipients"]}), "environment_modified": False}
    write(directory / "modules.private.json", records)
    write(directory / "agent-summary.json", summary)
    write(directory / "plan.json", plan(preset, modules, network, target, providers))
    # Optional tools stay available without turning the baseline into a feature inventory.
    page = (directory / "base/report.html").read_text(encoding="utf-8")
    rows = []
    from .browser_extras import LABELS
    for key, r in records.items():
        rows.append([label(key), reading(key, r), advice(key, r["status"])])
    extra = ''.join('<tr><th scope="row">' + escape(label) + '</th><td>' + escape(value) + '</td><td>' + escape(action) + '</td></tr>' for label, value, action in rows)
    if rows:
        notice = ('<p><strong>需核对：</strong>' + escape('、'.join(attention))
                  + '。这些是所选扩展的独立结果，不改变基础检查结论。</p>') if attention else ''
        detail = ('<details><summary>所选模块的本地依据</summary><pre>'
                  + escape(json.dumps(records, ensure_ascii=False, indent=2)) + '</pre></details>')
        optional = ('<details id="optional-results"><summary>可选检查 · ' + str(len(rows)) + ' 项'
                    + (' · ' + str(len(attention)) + ' 项需核对' if attention else '')
                    + (' · ' + str(len(pending)) + ' 项无有效结果' if pending else '')
                    + '</summary><p class="muted">仅在选择后运行。终端侧结果不代替实际浏览器；未配置、未安装与执行失败不计入基础风险。</p>'
                    + notice + '<div class="table-wrap"><table aria-label="可选检查结果"><thead><tr><th>检查项</th><th>结果</th><th>建议</th></tr></thead><tbody>'
                    + extra + '</tbody></table></div>' + detail + '</details>')
        page = page.replace('<!-- ZHIBI_OPTIONAL_RESULTS -->', optional)
    write(directory / "report.html", page)
    write(directory / "report.md", (directory / "base/report.md").read_text() + (
        '\n\n<details><summary>本次选择的可选检查</summary>\n\n| 检查项 | 结果 | 建议 |\n| --- | --- | --- |\n'
        + '\n'.join('| ' + ' | '.join(v.replace('|', '/') for v in row) + ' |' for row in rows)
        + '\n\n</details>\n' if rows else ''))
    return {"directory": str(directory), "report": str(directory / "report.html"), "summary": summary}


def register(sub):
    sub.add_parser("modules", help="列出全部可选模块、依赖、接收方和操作边界")
    p = sub.add_parser("suite", help="基础/全量/自定义只读检查，生成一张报告表")
    p.add_argument("--preset", choices=("basic", "all", "custom"), default="basic")
    p.add_argument("--module", choices=list(MODULES), action="append", default=[])
    p.add_argument("--network", action="store_true")
    p.add_argument("--provider", choices=list(PROVIDERS), action="append", default=[], help="自定义组合的可选数据源，可重复")
    p.add_argument("--browser")
    p.add_argument("--target", choices=("agent", "browser"), default="agent")
    p.add_argument("--config", help="权限 600 的本机可选配置；不把内容发到聊天")
    p.add_argument("--out")
    p.add_argument("--dry-run", action="store_true")
