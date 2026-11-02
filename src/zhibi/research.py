"""Maintained research claims and an offline learning layer."""
from __future__ import annotations

from html import escape
from importlib.resources import files

from .engine import bundle, evaluate
from .models import InputError, timestamp

SCOPE_NAMES = {
    "measurement_semantics": "测量与实现语义",
    "official_disclosure": "官方披露范围",
    "cross_platform_analogy": "跨平台类比",
    "platform_hypothesis": "待检验的平台假设",
    "product_hypothesis": "待检验的产品假设",
}


def validate_knowledge(claims=None, features=None, rules=None, sources=None, lessons=None):
    claims = bundle("claims") if claims is None else claims
    features = bundle("features") if features is None else features
    rules = bundle("rules") if rules is None else rules
    sources = bundle("sources") if sources is None else sources
    lessons = bundle("lessons") if lessons is None else lessons
    def indexed(items):
        ids = [item["id"] for item in items]
        if len(ids) != len(set(ids)):
            raise InputError("知识库 ID 重复。")
        return {i["id"]: i for i in items}
    c, f, r, s = map(indexed, (claims, features, rules, sources))
    indexed(lessons)
    for claim in claims:
        if claim["status"] not in ("proposed", "supported", "contradicted", "retired") or claim["scope_kind"] not in SCOPE_NAMES:
            raise InputError("知识主张状态或范围无效。")
        if not claim["sources"] or not set(claim["sources"]) <= s.keys() or not set(claim["features"]) <= f.keys():
            raise InputError("知识主张引用缺失。")
        if not claim["falsifier"] or not claim["not_established"]:
            raise InputError("知识主张必须保留可反驳条件和证据边界。")
    for feature in features:
        if not set(feature["claim_ids"]) <= c.keys():
            raise InputError("特征引用缺失。")
    for rule in rules:
        if rule["claim"] not in c or not set(rule["sources"]) <= s.keys():
            raise InputError("规则主张或来源不存在。")
    for lesson in lessons:
        if not set(lesson["claims"]) <= c.keys():
            raise InputError("课程引用缺失。")
    return {"sources": len(s), "claims": len(c), "features": len(f), "rules": len(r), "lessons": len(lessons)}


def theory():
    validate_knowledge()
    claims, features, sources, rules = (bundle(n) for n in ("claims", "features", "sources", "rules"))
    nodes = ([{"id": "source:" + x["id"], "kind": "source", "label": x["title"]} for x in sources] +
             [{"id": "claim:" + x["id"], "kind": "claim", "label": x["title"], "status": x["status"],
               "scope_kind": x["scope_kind"]} for x in claims] +
             [{"id": "feature:" + x["id"], "kind": "feature", "label": x["title"]} for x in features] +
             [{"id": "rule:" + x["id"], "kind": "rule", "label": x["title"]} for x in rules])
    edges = []
    for claim in claims:
        edges.extend({"from": "source:" + sid, "to": "claim:" + claim["id"], "relation": "supports_within_scope"}
                     for sid in claim["sources"])
        edges.extend({"from": "feature:" + fid, "to": "claim:" + claim["id"], "relation": "describes_observability"}
                     for fid in claim["features"])
    edges.extend({"from": "claim:" + r["claim"], "to": "rule:" + r["id"], "relation": "constrains"}
                 for r in rules)
    return {"framework": "知彼：平台目标、事件、证据与行动", "version": "0.1",
            "status": "research_framework", "claims": claims, "features": features,
            "sources": sources, "nodes": nodes, "edges": edges,
            "boundary": "这是可检验的研究框架，不是还原后的 上游内部模型。"}


def render_theory_markdown():
    data = theory()
    lines = ["# " + data["framework"], "", data["boundary"], "",
             "平台目标 → 业务事件与判断对象 → 可见证据/隐藏状态 → 处置 → 用户行动", "",
             "## 可追溯的主张", ""]
    sources = {s["id"]: s for s in data["sources"]}
    for c in data["claims"]:
        lines.extend(["### " + c["title"], "",
                      c["status"] + " · " + SCOPE_NAMES[c["scope_kind"]], "", c["statement"], "",
                      "不支持的扩展：" + c["not_established"], "",
                      "修订条件：" + c["falsifier"], ""])
        lines += ["- " + sources[s]["title"] + " — " + sources[s]["source"] for s in c["sources"]]
        lines.append("")
    return "\n".join(lines)


def lesson(topic=None):
    lessons = bundle("lessons")
    if topic is None:
        return lessons
    for item in lessons:
        if item["id"] == topic:
            return [item]
    raise InputError("未找到课程；运行 zhibi learn 查看可用主题。")


def render_lessons(topic=None):
    lines = ["# 知彼学习手册", "", "离线阅读；实验使用合成输入，不注册账号、不修改系统。", ""]
    claims = {c["id"]: c for c in bundle("claims")}
    sources = {s["id"]: s for s in bundle("sources")}
    for item in lesson(topic):
        lines.extend(["## " + item["title"], "", item["summary"], ""])
        for section in item["sections"]:
            lines.extend(["### " + section["title"], "", section["body"], ""])
        ex = item["exercise"]
        lines.extend(["练习：" + ex["question"], "", "运行：" + ex["command"], "",
                      "参考答案：" + ex["answer"], "", "主张：" + ", ".join(item["claims"]), ""])
        used = set()
        for cid in item["claims"]:
            for sid in claims[cid]["sources"]:
                if sid not in used:
                    used.add(sid)
                    lines.append("- " + sources[sid]["title"] + " — " + sources[sid]["source"])
        lines.append("")
    return "\n".join(lines)


def render_learning_html(topic=None):
    esc = lambda x: escape(str(x), quote=True)
    claims = {c["id"]: c for c in bundle("claims")}
    sources = {s["id"]: s for s in bundle("sources")}
    contents = []
    for item in lesson(topic):
        sections = "".join("<h3>" + esc(s["title"]) + "</h3><p>" + esc(s["body"]) + "</p>" for s in item["sections"])
        references = []
        for cid in item["claims"]:
            c = claims[cid]
            refs = []
            for sid in c["sources"]:
                source = sources[sid]
                label = esc(source["title"])
                if source["source"].startswith("https://"):
                    label = '<a href="' + esc(source["source"]) + '" rel="noreferrer noopener">' + label + "</a>"
                refs.append(label)
            references.append("<li><strong>" + esc(c["title"]) + "</strong> · " +
                              esc(c["status"] + " / " + SCOPE_NAMES[c["scope_kind"]]) +
                              "<p>" + esc(c["not_established"]) + "</p>" + " / ".join(refs) + "</li>")
        ex = item["exercise"]
        contents.append('<section class="chapter" id="' + esc(item["id"]) + '"><div class="eyebrow">' +
                        esc(item["id"]) + "</div><h2>" + esc(item["title"]) + "</h2><p>" +
                        esc(item["summary"]) + "</p>" + sections + '<div class="exercise"><b>动手验证</b><p>' +
                        esc(ex["question"]) + "</p><pre>" + esc(ex["command"]) + "</pre><details><summary>看参考答案</summary><p>" +
                        esc(ex["answer"]) + "</p></details></div><details><summary>追溯本章主张与来源</summary><ul>" +
                        "".join(references) + "</ul></details></section>")
    links = "".join('<a href="#' + esc(x["id"]) + '">' + esc(x["title"]) + "</a>" for x in lesson(topic))
    css = files("zhibi").joinpath("assets").joinpath("report.css").read_text(encoding="utf-8")
    return """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<meta name="referrer" content="no-referrer"><title>知彼 · 学习手册</title><style>""" + css + """
.book{max-width:900px}.chapter{padding:35px 0;border-top:1px solid var(--line)}.chapter h2{font-size:28px}.chapter p{max-width:750px}.chapter h3{margin-top:24px;font-size:17px}
.toc{display:flex;flex-wrap:wrap;gap:12px 24px;margin:28px 0}.toc a{font-size:13px}.exercise{padding:22px;background:#e5ebdf;margin:24px 0}.exercise pre{white-space:pre-wrap;overflow-wrap:anywhere}.chapter details{font-size:13px;margin-top:18px}.chapter li{margin:16px 0}
</style></head><body><main class="shell book"><div class="topline"><b class="brand">知彼 Zhibi</b><span class="mono">LEARN BY CHECKING</span></div>
<p class="eyebrow" style="margin-top:40px">THEORY · EVIDENCE · PRACTICE</p><h1>学会判断，<br>再运行检查。</h1>
<p class="intro">六个短章节，一组可复现的离线实验。把平台事实、研究类比和未验证假设分开。</p><nav class="toc">""" + links + "</nav>" + "".join(contents) + """
<footer>离线手册 · 点击外部来源链接时浏览器会访问对应网站。作者个人教程另行维护。</footer></main></body></html>"""


def run_lab(name):
    from .demo import fixture
    from .privacy import agent_summary
    cases = {"routing": ["route-mismatch", "intentional-routing"],
             "failure": ["measurement-failure"], "repair": ["proxy-conflict", "proxy-corrected"]}
    if name not in cases:
        raise InputError("实验应为 routing、failure 或 repair。")
    results = []
    for scenario in cases[name]:
        data = fixture(scenario)
        report = evaluate(data["observations"], data["profile"], sample=True, at=timestamp(data["evaluated_at"]))
        results.append({"scenario": scenario, "summary": agent_summary(report)})
    return {"lab": name, "sample": True, "external_requests": 0, "system_changes": 0,
            "runs": results, "lesson": {"routing": "routes", "failure": "unknown", "repair": "repair"}[name]}
