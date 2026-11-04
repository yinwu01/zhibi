"""Local-only rendering. User-supplied strings are escaped; no remote assets."""
from collections import Counter
from html import escape
from importlib.resources import files
from urllib.parse import urlsplit

from .engine import bundle, validate_report

NAMES = {"needs_action": "需要处理", "needs_confirmation": "需要确认", "verified": "事实已确认",
         "unknown": "尚未确定", "not_applicable": "不适用"}
RADAR = """<svg viewBox="0 0 280 240" fill="none" aria-label="从观测到证据再到行动的关系图" role="img">
<circle cx="140" cy="120" r="95" stroke="#d0d9cd"/><circle cx="140" cy="120" r="62" stroke="#d0d9cd"/>
<circle cx="140" cy="120" r="29" stroke="#d0d9cd"/><path d="M45 120H235M140 25V215" stroke="#d0d9cd"/>
<path d="M78 152L140 69L203 145L140 120Z" fill="#dce6d8" stroke="#266a51"/>
<circle cx="78" cy="152" r="5" fill="#bb4b2f"/><circle cx="140" cy="69" r="5" fill="#183c34"/>
<circle cx="203" cy="145" r="5" fill="#183c34"/><circle cx="140" cy="120" r="4" fill="#183c34"/>
<g font-family="monospace" font-size="10" fill="#65776e"><text x="117" y="15">EVIDENCE</text>
<text x="9" y="178">OBSERVE</text><text x="217" y="171">ACT</text></g></svg>"""


def markdown(report):
    validate_report(report)
    def md(value):
        return str(value).replace("\\", "\\\\").replace("<", "&lt;").replace(">", "&gt;").replace("[", "\\[").replace("]", "\\]")
    lines = ["# 知彼 · 环境准备报告", "",
             "**合成示例：不是实际账号检测结果。**" if report["sample"] else "**本地检查；测量结果不代表账号安全。**",
             "", "覆盖状态：" + report["coverage"], ""]
    for finding in report["findings"]:
        lines += ["## " + md(NAMES[finding["assessment"]] + " · " + finding["rule_id"]), "",
                  md(finding["statement"]), ""]
        if finding["next_step"]:
            lines += ["下一步：" + md(finding["next_step"]), ""]
        if finding["recheck"]:
            lines += ["复查：" + md(finding["recheck"]), ""]
        lines += ["边界：" + md(" ".join(finding["limitations"])), "",
                  "依据：" + ", ".join(finding["evidence_refs"]), ""]
    lines += ["## 来源", ""]
    for source in report["evidence"]:
        lines += ["- " + md(source["title"]) + " — " + md(source["source"])]
    return "\n".join(lines) + "\n"


def html(report):
    validate_report(report)
    esc = lambda v: escape(str(v), quote=True)
    rules = {r["id"]: r for r in bundle("rules")}
    sources = {s["id"]: s for s in report["evidence"]}
    count = Counter(f["assessment"] for f in report["findings"])
    cards = []
    order = {"needs_action": 0, "needs_confirmation": 1, "unknown": 2, "verified": 3, "not_applicable": 4}
    for f in sorted(report["findings"], key=lambda f: order[f["assessment"]]):
        refs = []
        for sid in f["evidence_refs"]:
            s = sources[sid]
            label = esc(s["title"])
            url = urlsplit(s["source"])
            if url.scheme == "https" and url.hostname and not url.username and not url.password:
                label = '<a href="' + esc(s["source"]) + '" rel="noreferrer noopener">' + label + "</a>"
            refs.append("<li>" + label + " — " + esc(s["scope"]) + "</li>")
        title = rules.get(f["rule_id"], {}).get("title", f["rule_id"])
        action = ('<p class="next"><strong>下一步</strong>' + esc(f["next_step"]) + "</p>") if f["next_step"] else ""
        recheck = ('<p class="next"><strong>复查</strong>' + esc(f["recheck"]) + "</p>") if f["recheck"] else ""
        cards.append(f'<article class="finding"><header><h3>{esc(title)}</h3>'
                     f'<span class="tag {f["assessment"]}">{NAMES[f["assessment"]]}</span></header>'
                     f'<p class="statement">{esc(f["statement"])}</p>{action}{recheck}'
                     '<details><summary>查看依据与正常反例</summary>'
                     f'<p>{esc(" ".join(f["limitations"]))}</p>'
                     f'<p class="mono">{esc(f["rule_id"])} ← {esc(", ".join(f["observation_ids"]))}</p>'
                     f'<ul class="source-list">{"".join(refs)}</ul></details></article>')
    rows = "".join(f'<tr><td>{esc(o["check_id"])}</td><td>{esc(o["summary"])}</td>'
                   f'<td>{esc(o["measurement_status"])}</td></tr>' for o in report["observations"])
    attempted = [f for f in report["data_flows"] if f["sent"]]
    flow_text = ("本次已尝试联系：" + "、".join(f["recipient"] for f in attempted)) if attempted else "本次报告未记录外部测量请求。"
    css = files("zhibi").joinpath("assets").joinpath("report.css").read_text(encoding="utf-8")
    sample = "合成示例 / SYNTHETIC DEMO" if report["sample"] else "本地报告 / LOCAL REPORT"
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<meta name="referrer" content="no-referrer"><title>知彼 · 注册准备报告</title><style>{css}</style></head>
<body><main class="shell"><nav class="topline"><div class="brand">知彼 <small>ZHIBI / FIELD NOTES</small></div>
<div class="mono">ENVIRONMENT PREPARATION<br>{esc(report["generated_at"])}</div></nav>
<section class="hero"><div><div class="eyebrow">OBSERVE · UNDERSTAND · PREPARE</div>
<h1>看懂风控。<br>再做准备。</h1><p class="intro">把当前观测、公开证据和下一步放在一起。先处理能确认的问题，让未知保持可见。</p>
<span class="stamp">{sample}</span></div><div class="diagram">{RADAR}</div></section>
<section class="stats" aria-label="报告统计">
<div class="stat action"><b class="num">{count["needs_action"] + count["needs_confirmation"]:02}</b><span>准备与确认事项</span></div>
<div class="stat"><b class="num">{count["verified"]:02}</b><span>已确认的具体事实</span></div>
<div class="stat"><b class="num">{count["unknown"]:02}</b><span>仍需更多观测</span></div></section>
<div class="columns"><section id="actions"><h2 class="section-label">01 / 你的下一步</h2>{"".join(cards)}</section>
<aside><section><h2>报告怎样得到结论</h2>
<div class="flow-step"><b>01</b><div>观测<span>具体对象 · 时间 · 范围</span></div></div>
<div class="flow-step"><b>02</b><div>证据<span>来源 · 时效 · 正常反例</span></div></div>
<div class="flow-step"><b>03</b><div>行动<span>适用前提 · 下一步 · 复查</span></div></div></section>
<section><h2>数据留在哪里</h2><p>报告在本机生成，页面不加载外部脚本、字体或统计服务。</p>
<p>{esc(flow_text)}</p><p>点击官方来源链接，会由浏览器打开对应网站。</p></section>
<section><h2>这份报告的边界</h2><p>检查覆盖：<span class="pill">{esc(report["coverage"])}</span></p>
<p>“事实已确认”仅指某项观测成立。平台内部评分、隐藏关联和账号未来结果仍不可见。</p>
<p>没有综合封号概率，也没有“绿色即安全”的结论。</p></section></aside></div>
<section class="observations"><h2 class="section-label">02 / 观测记录</h2>
<table><thead><tr><th>CHECK</th><th>结果</th><th>测量状态</th></tr></thead><tbody>{rows}</tbody></table></section>
<footer><span>知彼 Zhibi · 独立社区项目</span><span>公开证据 / 本地检查 / 可复查的指导</span></footer>
</main></body></html>"""
