"""Task preparation and error routing, without ingesting raw account responses."""
from datetime import datetime, timezone

from .engine import bundle, source_state
from .models import InputError, profile

SIGNALS = ("network_timeout", "dns_error", "tls_error", "http_401", "http_403", "http_429",
           "http_5xx", "verification_requested", "payment_declined", "account_suspended",
           "content_refusal", "unknown")
STAGES = ("registration", "login", "payment", "usage")
CHANNELS = ("web", "code", "api")


def sources_for(ids, at=None):
    at = at or datetime.now(timezone.utc)
    sources = {s["id"]: s for s in bundle("sources")}
    return [{**sources[sid], "review_state": source_state(sources[sid], at)} for sid in ids]


def triage(signal, channel="web", stage="registration", at=None):
    if signal not in SIGNALS or channel not in CHANNELS or stage not in STAGES:
        raise InputError("请选择受支持的错误类型、入口和阶段；不要提交原始认证响应。")
    source_ids = ["method"]
    category, statement = "unknown", "当前描述不足以确定问题类别。"
    actions = ["在官方界面核对具体提示，区分发生阶段；只记录不含身份信息的错误类别。"]
    if signal in ("network_timeout", "dns_error", "tls_error"):
        category = "connectivity"
        statement = "先排查连接、解析或证书层问题，尚未证明请求到达账号判断环节。"
        actions = ["检查同一客户端是否能访问其他预期服务，查看是否有网络或证书错误。",
                   "保留 TLS 验证；遇到企业网络证书问题，联系网络管理员核对。"]
    elif signal in ("http_401", "http_403") and channel == "api":
        category = "authentication" if signal == "http_401" else "permissions"
        statement = "这是 API 认证问题的排查入口。" if signal == "http_401" else "这是 API 资源权限问题的排查入口。"
        actions = ["在官方控制台核对凭据状态或组织/工作区权限，不把 Key 内容交给检查工具。",
                   "若持续失败，通过官方支持渠道提供必要的请求标识；公开案例不包含原始响应。"]
        source_ids.append("api-errors")
    elif signal in ("http_401", "http_403"):
        category = "access_needs_confirmation"
        statement = "网页或客户端的访问被拒绝，单个 HTTP 状态码不足以确认账号暂停。"
        actions = ["核对官方页面是否显示明确的登录、验证或账号限制提示。",
                   "记录发生入口和阶段，必要时联系官方支持；不要把 API Key 排查步骤套到网页登录。"]
    elif signal == "http_429":
        category = "capacity_or_quota"
        statement = "优先核对当前产品的速率、额度或费用上限，不能直接标为账号暂停。"
        actions = ["在实际产品的官方用量/账单界面核对限制和恢复信息。",
                   "遵循界面或响应给出的等待提示，避免反复重试放大问题。"]
        if channel == "api":
            source_ids.append("api-errors")
    elif signal == "http_5xx":
        category = "service_availability"
        statement = "优先核对服务可用性和临时故障，不将其转换成用户风险。"
        actions = ["查看官方服务状态；若持续出现，通过官方支持渠道记录错误类别与时间。"]
        if channel == "api":
            source_ids.append("api-errors")
    elif signal == "verification_requested":
        category = "verification"
        statement = "需要完成官方验证流程；要求验证本身不等于账号已被暂停。"
        actions = ["确认正在官方页面操作，按照该流程提交真实且适用的资料。",
                   "资料仅提交给官方指定流程；知彼不接收验证码、证件或支付材料。"]
    elif signal == "payment_declined":
        category = "payment"
        statement = "这是付款问题的排查入口；当前信息不能区分发卡行、验证或平台侧原因。"
        actions = ["在官方账单页面检查拒绝原因与必要验证；需要时联系发卡行或官方支持。",
                   "不要仅因付款失败切换身份、批量尝试或购买所谓防封环境。"]
    elif signal == "account_suspended":
        category = "reported_account_restriction"
        statement = "按你选择的明确账号限制提示进入官方复核流程；工具未独立验证账号状态。"
        actions = ["使用官方账号界面和申诉渠道，说明必要事实并保留时间记录。",
                   "不要将普通连接错误当作同类证据，也不要把申诉资料发给第三方检查网站。"]
        source_ids.append("appeals")
    elif signal == "content_refusal":
        category = "request_or_content"
        statement = "某次请求被拒绝与整个账号暂停是不同结果。"
        actions = ["核对请求与官方使用要求，必要时说明合法使用背景并走官方反馈渠道。",
                   "只保存不含敏感正文的错误类别；不尝试规避内容保护。"]
        source_ids.append("appeals")
    sources = sources_for(source_ids, at)
    return {"schema_version": "triage-1", "input_kind": "user_selected_signal", "signal": signal,
            "channel": channel, "stage": stage, "category": category, "statement": statement,
            "actions": actions, "sources": sources,
            "review_required": any(s["review_state"] != "current" for s in sources),
            "limitations": ["分类是排查方向，不是平台内部原因判定；没有访问账号或接收原始响应。"]}


def preparation(context=None, at=None):
    context = profile(context)
    steps = [
        {"id": "official-eligibility", "title": "核对真实使用条件",
         "why": "服务范围和注册条件独立于网络是否接通。",
         "precondition": "已明确目标产品和真实使用情况。",
         "action": "打开官方来源，核对当前适用政策、生效时间与必要验证要求。",
         "done_when": "你已逐项确认适用要求；仍不清楚的部分向官方核实。",
         "sources": ["regions", "appeals"]},
        {"id": "private-preparation", "title": "保留账号资料的控制权",
         "why": "检测不需要账号登录材料。",
         "precondition": "准备运行检查或询问第三方。",
         "action": "只提供工具模板允许的非敏感背景；密码、Cookie、验证码和证件只在适用官方流程使用。",
         "done_when": "检查输入和分享摘要中不包含认证或身份材料。",
         "sources": ["method"]},
        {"id": "measure-environment", "title": "观察实际使用入口",
         "why": "新建自动化环境不能替代你的真实浏览器。",
         "precondition": "工具已安装，实际使用的浏览器可打开本地探针。",
         "action": "运行 zhibi check；按需导出实际浏览器结果，联网检查先查看接收方。",
         "done_when": "已读报告中的成功、失败、缺失及适用范围，不把未知当作通过。",
         "sources": ["method", "ipify"]},
    ]
    if context["product"] == "code":
        steps.append({"id": "client-install", "title": "准备官方客户端",
                      "why": "客户端安装和认证是不同步骤。",
                      "precondition": "选择使用 目标客户端。",
                      "action": "按官方文档安装客户端，在新终端确认命令可用，再通过官方流程认证。",
                      "done_when": "客户端能正常启动；账号状态通过官方界面独立确认。",
                      "sources": ["method"]})
    elif context["product"] == "api":
        steps.append({"id": "api-access", "title": "准备 API 访问与预算",
                      "why": "认证、资源权限、额度与账号封禁具有不同语义。",
                      "precondition": "选择使用 API。",
                      "action": "在官方控制台核对组织权限和预算，将凭据仅保存在受保护的本地配置。",
                      "done_when": "你了解凭据保存位置和使用额度；检查工具没有读取 Key。",
                      "sources": ["api-errors"]})
    steps += [
        {"id": "resolve-confirmed-issue", "title": "只处理已定位的问题",
         "why": "有意分流和多语言环境不必自动修改。",
         "precondition": "报告出现与你预期不符的具体配置或能力问题。",
         "action": "保存旧配置，选择最小修改，然后重新运行同类检查。",
         "done_when": "前后可比观测证明具体问题已解决；仍未知的部分单独保留。",
         "sources": ["method"]},
        {"id": "official-next-step", "title": "在官方流程完成下一步",
         "why": "环境观测不决定服务资格或账号结果。",
         "precondition": "已核对适用条件并理解当前检查范围。",
         "action": "自行在官方页面注册、登录或完成必要验证；出现异常时用 zhibi triage 分流。",
         "done_when": "记录官方页面的实际结果和观察时间，不把本工具的事实确认当作账号通过。",
         "sources": ["appeals"]},
    ]
    ids = list(dict.fromkeys(sid for step in steps for sid in step["sources"]))
    return {"schema_version": "preparation-1", "product": context["product"], "stage": context["stage"],
            "completion": "not_recorded", "steps": steps, "sources": sources_for(ids, at),
            "notice": "这是一份待用户完成的准备清单，没有替用户确认资格或实际注册结果。"}


def preparation_markdown(context=None, at=None):
    guide = preparation(context, at)
    lines = ["# 知彼 · 注册与使用准备清单", "", guide["notice"], "",
             "产品：" + guide["product"] + "；场景：" + guide["stage"], ""]
    for step in guide["steps"]:
        lines += ["## " + step["title"], "", "为什么：" + step["why"], "",
                  "前提：" + step["precondition"], "", "操作：" + step["action"], "",
                  "完成标准：" + step["done_when"], ""]
    lines += ["## 参考来源", ""]
    for s in guide["sources"]:
        lines += ["- " + s["title"] + " — " + s["source"] + "（" + s["review_state"] + "）"]
    return "\n".join(lines) + "\n"
