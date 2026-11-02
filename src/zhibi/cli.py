"""Command line entrypoints; no account authentication is required."""
from __future__ import annotations

import argparse
import json
import sys
from importlib.resources import files
from pathlib import Path

from . import __version__, reports
from .checks import collect
from .demo import SCENARIOS, fixture
from .engine import bundle, evaluate, explain, validate_report
from .models import InputError, browser_input, exact, now, profile, read_json, timestamp
from .privacy import agent_summary, compare_reports
from .storage import create_run, write
from .transport import Transport
from .guidance import CHANNELS, SIGNALS, STAGES, preparation, preparation_markdown, triage
from .research import render_learning_html, render_lessons, render_theory_markdown, run_lab, theory
from .history import timeline
from .intelligence import PROVIDERS, catalog, configure, configure_all, load_keys
from .scan import run_scan, scan_plan, scan_summary, render_scan, scan_markdown, compare_scans


def emit(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))


def plan(network=False, metadata=False, ipv6=False, connectivity=False, target=None):
    if (metadata or ipv6 or connectivity) and not network:
        raise InputError("联网扩展必须与 --network 一起启用。")
    if connectivity and not target:
        raise InputError("--connectivity 需要同时用 --target-domain 声明目标站点。")
    return {
        "version": __version__, "default": "offline",
        "local_checks": ["Python/OS", "proxy variable flags only", "resolv.conf nameserver count",
                         "declared client executable presence; never execute it"],
        "browser": "manual JSON import; never read existing browser profiles",
        "external_services": [
            {"recipient": "api.ipify.org", "enabled": network, "max_requests": 1,
             "fields": ["request_source_ip", "network_metadata"], "credentials": False},
            {"recipient": "ipwho.is", "enabled": metadata, "max_requests": 1,
             "fields": ["queried_ip", "request_source_ip", "network_metadata"], "credentials": False},
            {"recipient": "api6.ipify.org", "enabled": ipv6, "max_requests": 1,
             "fields": ["request_source_ip", "network_metadata"], "credentials": False},
            {"recipient": target, "enabled": bool(connectivity and target), "method": "HEAD", "max_requests": 1,
             "fields": ["request_source_ip", "network_metadata"], "credentials": False}],
        "socket_timeout_seconds": 8, "dns_timeout": "operating-system controlled", "retries": 0, "redirects": False,
        "paid_services": False, "telemetry": False, "account_requests": False,
        "note": "实际路由遵循当前进程/系统的 HTTP 代理设置；浏览器路径可能不同。"
    }


def save_run(report, snapshot, destination=None):
    directory = create_run(destination)
    write(directory / "snapshot.private.json", snapshot)
    write(directory / "report.json", report)
    write(directory / "report.md", reports.markdown(report))
    write(directory / "report.html", reports.html(report))
    summary = agent_summary(report)
    write(directory / "agent-summary.json", summary)
    write(directory / "preparation.md", preparation_markdown(snapshot.get("profile"), timestamp(report["generated_at"])))
    emit({"directory": str(directory), "report": str(directory / "report.html"), "summary": summary})


def main(argv=None):
    # JSON and Chinese text must remain usable in redirected pipes on all platforms.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="zhibi", description="知彼：本地检查、公开证据与 环境准备。")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("capabilities", help="查看真实能力与实现边界")
    sub.add_parser("doctor", help="检查工具运行条件，不读取账号文件")
    sub.add_parser("providers", help="查看情报来源、覆盖与密钥配置状态，不显示密钥")
    p = sub.add_parser("dns", help="独立观察 dig 默认解析器，不代替浏览器 DNS 检测")
    p.add_argument("--network", action="store_true", help="允许一次固定 Akamai 诊断名称的 TXT 查询")
    p.add_argument("--dry-run", action="store_true", help="查看 DNS 查询范围，不运行 dig")
    p.add_argument("--out", help="新建报告目录")
    p = sub.add_parser("configure", help="在本机交互输入供应商密钥，不经过模型")
    p.add_argument("provider", choices=[key for key, value in PROVIDERS.items() if value["key"]] + ["all"])
    p = sub.add_parser("scan", help="Skill 完整检查：本地环境、多源 IP 情报和主动风控解释")
    p.add_argument("--network", action="store_true", help="启用明确选择的外部测量")
    p.add_argument("--provider", choices=list(PROVIDERS), action="append", default=[], help="情报来源，可重复指定")
    p.add_argument("--reputation", action="store_true", help="免 Key 信誉组合：IPWhois、ProxyCheck、IPQuery、StopForumSpam；需 --network")
    p.add_argument("--progress", action="store_true", help="在标准错误显示检测进度，标准输出仍为 JSON；不显示 IP 或密钥")
    p.add_argument("--ipv6", action="store_true", help="同时测量 IPv6；来源最多查询两个地址")
    p.add_argument("--browser", help="实际浏览器导出的本地 JSON")
    p.add_argument("--target", choices=("agent", "browser"), default="agent", help="情报查询对象；不会用 Agent 出口代替浏览器")
    p.add_argument("--profile", help="本地非敏感场景 JSON")
    p.add_argument("--out", help="新建报告目录")
    p.add_argument("--dry-run", action="store_true", help="只查看接收方、字段与请求预算，不联网")
    p = sub.add_parser("confirm-ipv6", help="记录已核对的专用环境 IPv6 禁用配置，生成新报告；不修改网络")
    p.add_argument("run_dir", help="十五分钟内生成的检测目录")
    p.add_argument("--evidence", required=True, help="已核对的本地配置文件或设置截图；仅保存摘要与本地引用")
    p.add_argument("--configuration", required=True, choices=("disabled", "blocked"))
    p.add_argument("--method", required=True, choices=("settings_ui", "local_config"))
    p.add_argument("--reviewed", action="store_true", help="确认已核对同一专用环境的生效配置")
    p.add_argument("--out", required=True, help="保存确认结果的新目录")
    p = sub.add_parser("scan-demo", help="离线演示多源冲突、缺失或服务故障，始终标记合成")
    p.add_argument("--scenario", choices=("conflicting-sources", "missing-coverage", "provider-outage"), default="conflicting-sources")
    p.add_argument("--out")
    p = sub.add_parser("scan-compare", help="比较两次扫描目录；IP 仅在本地核心中比对")
    p.add_argument("before")
    p.add_argument("after")
    p.add_argument("--same-context", action="store_true", help="声明同一设备/使用场景；否则只返回不可比")
    for command in ("plan", "check"):
        p = sub.add_parser(command, help="显示数据流" if command == "plan" else "执行只读检查并生成报告")
        p.add_argument("--network", action="store_true", help="允许一次 ipify 出口请求")
        p.add_argument("--ip-metadata", action="store_true", help="额外允许一次 IPWhois 归属查询")
        p.add_argument("--ipv6", action="store_true", help="额外允许一次 IPv6 专用端点查询")
        p.add_argument("--connectivity", action="store_true", help="额外允许一次目标站点首页 HEAD，不登录；需配合 --target-domain")
        p.add_argument("--target-domain", help="声明目标站点域名，如 example.com；未声明时不做任何站点探测")
        if command == "check":
            p.add_argument("--profile", help="非敏感场景 JSON")
            p.add_argument("--browser", help="实际浏览器探针 JSON")
            p.add_argument("--out", help="新建的输出目录，默认 ~/.zhibi/<run>")
    p = sub.add_parser("demo", help="运行可复现的合成场景，不联网")
    p.add_argument("--scenario", choices=SCENARIOS, default="route-mismatch")
    p.add_argument("--out")
    p = sub.add_parser("evaluate", help="离线评估合成输入，始终标注 sample")
    p.add_argument("input")
    p.add_argument("--out")
    p = sub.add_parser("browser", help="导出可离线打开的浏览器检查页")
    p.add_argument("--out", required=True)
    p.add_argument("--advanced", action="store_true", help="导出双栈、WebRTC 和成熟上游采集器")
    p = sub.add_parser("explain", help="追溯规则、观测、来源与正常反例")
    p.add_argument("rule_id")
    sub.add_parser("knowledge", help="输出版本化研究来源与规则目录")
    p = sub.add_parser("report", help="从报告 JSON 重新渲染")
    p.add_argument("input")
    p.add_argument("--snapshot", help="配对的私人快照，仅供本机 HTML 显示 IP 与浏览器观测，不联网")
    p.add_argument("--format", choices=["html", "markdown"], default="html")
    p.add_argument("--out", required=True)
    p = sub.add_parser("export", help="重建可预览的最小摘要，无上传")
    p.add_argument("input")
    p.add_argument("--out")
    p = sub.add_parser("compare", help="比较两次报告的规则状态")
    p.add_argument("before")
    p.add_argument("after")
    p = sub.add_parser("triage", help="按错误类型与发生阶段分流；不接收原始认证响应")
    p.add_argument("--signal", choices=SIGNALS, required=True)
    p.add_argument("--channel", choices=CHANNELS, default="web")
    p.add_argument("--stage", choices=STAGES, default="registration")
    p.add_argument("--out")
    p = sub.add_parser("guide", help="生成按产品选择的准备清单")
    p.add_argument("--profile")
    p.add_argument("--format", choices=("markdown", "json"), default="markdown")
    p.add_argument("--out")
    p = sub.add_parser("theory", help="查看研究主张、特征与证据图")
    p.add_argument("--format", choices=("markdown", "json"), default="markdown")
    p.add_argument("--out")
    p = sub.add_parser("learn", help="离线学习手册与可复现练习")
    p.add_argument("topic", nargs="?", help="platform/evidence/routes/graph/unknown/repair；省略查看全部")
    p.add_argument("--format", choices=("markdown", "html"), default="markdown")
    p.add_argument("--out")
    p = sub.add_parser("lab", help="运行离线学习实验，不修改系统")
    p.add_argument("name", choices=("routing", "failure", "repair"))
    p.add_argument("--out")
    p = sub.add_parser("timeline", help="组织本地快照的事件图；默认不假定可比")
    p.add_argument("snapshots", nargs="+")
    p.add_argument("--same-context", action="store_true", help="声明这些快照来自同一使用上下文")
    p.add_argument("--out", required=True, help="新建私人 JSON 文件")
    from . import suite
    suite.register(sub)
    from . import maintenance
    maintenance.register(sub)
    from . import vault
    vault.register(sub)
    from . import session
    session.register(sub)
    from . import network_setup
    network_setup.register(sub)
    from . import adspower
    adspower.register(sub)
    from . import delivery
    delivery.register(sub)
    p = sub.add_parser("dns-observer", help="Explicit self-hosted authoritative DNS observer; see tutorial")
    p.add_argument("--zone", required=True)
    p.add_argument("--address", required=True)
    p.add_argument("--bind", default="127.0.0.1")
    p.add_argument("--dns-port", type=int, default=5353)
    p.add_argument("--http-port", type=int, default=8053)
    args = parser.parse_args(argv)
    try:
        if args.command == "suite-share":
            emit(delivery.share(args.run_dir, args.out, args.language))
        elif args.command == "suite-compare":
            emit(delivery.compare(args.before, args.after, args.same_context))
        elif args.command == "skill-install":
            emit(delivery.install(args.archive, args.sha256, args.dest, args.replace))
        elif args.command == "skill-rollback":
            emit(delivery.rollback(args.dest, args.previous))
        elif args.command == "adspower":
            emit(adspower.run(args.action, args.config, args.apply, args.out, args.receipt))
        elif args.command == "dns-observer":
            from .dns_observer import serve
            serve(args.zone, args.address, args.bind, args.dns_port, args.http_port)
        elif args.command == "network-setup":
            emit(network_setup.deliver(args.config, args.out) if args.action == "client-config" else network_setup.ssh_tunnel(args.config, args.apply))
        elif args.command == "session":
            emit(session.run(args.out, args.preset, args.network, args.config, args.wait, emit=lambda message: print(message, file=sys.stderr, flush=True), file_mode=args.file))
        elif args.command == "workspace":
            emit(vault.dispatch(args))
        elif args.command == "maintain":
            emit(maintenance.dispatch(args))
        elif args.command == "modules":
            emit(suite.catalog())
        elif args.command == "suite":
            emit(suite.plan(args.preset, args.module, args.network, args.target, args.provider) if args.dry_run else suite.run(args.preset, args.module, args.network, args.browser, args.target, args.config, args.out, progress=lambda message: print(message, file=sys.stderr, flush=True), providers=args.provider))
        elif args.command == "capabilities":
            emit({"name": "zhibi", "version": __version__, "report_schema": "0.1",
                  "commands": list(sub.choices),
                  "implemented": ["offline reports", "local read-only checks", "browser JSON import",
                                  "optional IPv4/IPv6 endpoint egress", "optional public HEAD diagnostics", "optional IP country/ASN", "source expiry",
                                  "rule provenance", "minimal export", "report comparison",
                                  "research claims graph", "offline learning labs",
                                  "keyless reputation preset (ipwhois/proxycheck/ipquery/stopforumspam)",
                                  "optional keyed intelligence (ipapi/ipqs/abuseipdb)",
                                  "provider coverage and conflict analysis", "intelligence evidence graph",
                                  "browser dual-stack and WebRTC observations", "optional dig resolver observation",
                                  "optional local browser details (locale, UA/device, runtime, CPU, 26 fonts, permission state)",
                                  "optional IPinfo/IPregistry/IP2Location/DB-IP/Scamalytics APIs",
                                  "optional DNSBL, downloaded public feeds and licensed local MMDB",
                                  "one-time local browser session and unified optional suite",
                                  "Canvas/WebGL/offline Audio/TLS and self-hosted authoritative DNS observer",
                                  "pinned CheckCC research models (separate from main verdict)",
                                  "public HTTP/SMTP, explicit proxy/interface checks and native inventory",
                                  "explicit reversible settings, AdsPower API and CLI maintenance",
                                  "optional encrypted directory backup and cache quarantine",
                                  "Mihomo client config and strict-known-host SSH tunnel plans",
                                  "redacted suite sharing, comparison and verified Skill upgrade/rollback",
                                  "preparation checklist", "error triage", "local snapshot event graph"],
                  "optional_modules": suite.catalog(),
                  "not_implemented": ["ban probability", "account eligibility decision", "unattended automatic repair",
                                      "complete streaming-region unlock tests", "full CCBaga VPS deployment",
                                      "every proxy-client TUN/control adapter", "payment/KYC verification",
                                      "platform internal account graph"],
                  "live_validation_required": ["keyed APIs with user credentials", "self-hosted DNS delegation",
                                               "licensed MMDB data", "Windows/Linux settings", "actual browser session"]})
        elif args.command == "doctor":
            emit({"python_supported": sys.version_info >= (3, 9), "version": __version__,
                  "account_login_required": False, "runtime_dependencies": []})
        elif args.command == "providers":
            emit({"providers": catalog(load_keys())})
        elif args.command == "dns":
            from .dns import plan as dns_plan, run_dns
            emit(dns_plan() if args.dry_run else run_dns(args.network, args.out))
        elif args.command == "configure":
            emit(configure_all() if args.provider == "all" else configure(args.provider))
        elif args.command == "confirm-ipv6":
            from .ipv6_policy import confirm_run
            emit(confirm_run(args.run_dir, args.evidence, args.configuration, args.method, args.reviewed, args.out))
        elif args.command == "scan":
            if args.reputation:
                from .intelligence import FREE_REPUTATION
                args.provider = list(dict.fromkeys([*FREE_REPUTATION, *args.provider]))
            if args.dry_run:
                emit(scan_plan(args.network, args.provider, args.ipv6, args.target))
            else:
                emit(run_scan(network=args.network, providers=args.provider, ipv6=args.ipv6,
                              browser_path=args.browser, target=args.target, out=args.out, profile_path=args.profile,
                              progress=(lambda message: print(message, file=sys.stderr, flush=True)) if args.progress else None))
        elif args.command == "scan-demo":
            from .scan_demo import run_demo
            emit(run_demo(args.scenario, args.out))
        elif args.command == "scan-compare":
            emit(compare_scans(args.before, args.after, args.same_context))
        elif args.command == "plan":
            emit(plan(args.network, args.ip_metadata, args.ipv6, args.connectivity, args.target_domain))
        elif args.command == "check":
            plan(args.network, args.ip_metadata, args.ipv6, args.connectivity, args.target_domain)
            context = profile(read_json(args.profile) if args.profile else None)
            browser = browser_input(read_json(args.browser)) if args.browser else None
            # Validate destination before any optional outbound request.
            if args.out and (Path(args.out).expanduser().exists() or Path(args.out).expanduser().is_symlink()):
                raise InputError("输出目录已存在；请选择新目录。")
            transport = Transport(args.network, args.ip_metadata, ipv6=args.ipv6, connectivity=args.connectivity,
                                  target=args.target_domain)
            items = collect(transport, browser)
            flows = list(transport.flows)
            if browser:
                egress = next(i for i in browser if i["check_id"] == "browser.egress")
                if egress["status"] != "skipped":
                    flows.append({"purpose": "imported browser observation attempt", "recipient": "api.ipify.org",
                                  "fields": ["request_source_ip", "network_metadata"], "sent": True})
            report = evaluate(items, context, flows)
            save_run(report, {"profile": context, "observations": items, "generated_at": now()}, args.out)
        elif args.command in ("demo", "evaluate"):
            data = fixture(args.scenario) if args.command == "demo" else read_json(args.input)
            exact(data, {"schema_version", "sample", "profile", "observations", "evaluated_at"},
                  {"schema_version", "sample", "profile", "observations", "evaluated_at"})
            if data["sample"] is not True or data["schema_version"] != "1":
                raise InputError("离线输入仅接受显式标注 sample: true 的合成数据。")
            report = evaluate(data["observations"], data["profile"], sample=True, at=timestamp(data["evaluated_at"]))
            save_run(report, data, args.out)
        elif args.command == "browser":
            from .browser import advanced_page
            write(args.out, advanced_page() if args.advanced else files("zhibi").joinpath("assets").joinpath("browser.html").read_text(encoding="utf-8"))
            emit({"browser_page": str(Path(args.out).absolute()), "external_requests_on_open": 0})
        elif args.command == "explain":
            emit(explain(args.rule_id))
        elif args.command == "knowledge":
            emit({"sources": bundle("sources"), "rules": bundle("rules"),
                  "claims": bundle("claims"), "features": bundle("features")})
        elif args.command == "report":
            data = read_json(args.input)
            snapshot = read_json(args.snapshot) if args.snapshot else None
            if snapshot is not None and (args.format != "html" or not isinstance(data, dict) or data.get("format") != "zhibi-scan-1"):
                raise InputError("私人快照只用于扫描报告的本机 HTML。")
            if isinstance(data, dict) and data.get("format") == "zhibi-scan-1":
                content = render_scan(data, snapshot) if args.format == "html" else scan_markdown(data)
            else:
                content = reports.html(data) if args.format == "html" else reports.markdown(data)
            write(args.out, content)
            emit({"output": str(Path(args.out).absolute())})
        elif args.command == "export":
            data = read_json(args.input)
            summary = scan_summary(data) if isinstance(data, dict) and data.get("format") == "zhibi-scan-1" else agent_summary(data)
            if args.out:
                write(args.out, summary)
            emit(summary)
        elif args.command == "compare":
            emit(compare_reports(read_json(args.before), read_json(args.after)))
        elif args.command == "timeline":
            write(args.out, timeline([read_json(p) for p in args.snapshots], args.same_context))
            emit({"output": str(Path(args.out).absolute()), "private": True})
        elif args.command in ("triage", "guide", "theory", "learn", "lab"):
            if args.command == "triage":
                content = triage(args.signal, args.channel, args.stage)
            elif args.command == "guide":
                context = profile(read_json(args.profile) if args.profile else None)
                content = preparation(context) if args.format == "json" else preparation_markdown(context)
            elif args.command == "theory":
                content = theory() if args.format == "json" else render_theory_markdown()
            elif args.command == "learn":
                content = render_learning_html(args.topic) if args.format == "html" else render_lessons(args.topic)
            else:
                content = run_lab(args.name)
            if args.out:
                write(args.out, content)
                emit({"output": str(Path(args.out).absolute())})
            elif isinstance(content, str):
                print(content)
            else:
                emit(content)
    except InputError as exc:
        # InputError messages are maintained fixed strings, never input values.
        print("知彼：" + str(exc), file=sys.stderr)
        return 2
    except (FileExistsError, FileNotFoundError, PermissionError, KeyError, TypeError, ValueError, OSError, AttributeError):
        # Never echo untrusted data, proxy URLs, upstream response bodies or credentials.
        print("知彼：输入或输出条件不满足。检查文件格式、字段、权限及输出路径（应为新路径）。用 --help 查看用法。", file=sys.stderr)
        return 2
    return 0
