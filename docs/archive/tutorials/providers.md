# 配置 IP 情报源

基础测量和情报查询都是在本机脚本中编排。外部服务会看到请求来源 IP 与查询 IP，服务自己的数据政策适用。
默认扫描不联网，只有明确选择的来源会被调用。没有内置共享密钥、网站爬虫或自动购买服务。

## 选择需要的来源

| 来源 | 当前适配能力 | 密钥与覆盖 |
| --- | --- | --- |
| IPWhois | 国家、ASN、组织 | 公共归属接口；免费接口不提供高级安全字段 |
| ProxyCheck v3 | 代理/VPN/Tor/托管标签、风险分、检测置信度、可用活动记录和源更新时间 | **免 Key 每日 100 次**；当前适配器使用此方案 |
| IPQuery | 代理/VPN/Tor/机房标签、0–100 原始风险分、归属 | **免 Key**；官方称免费，仍受限流约束 |
| StopForumSpam | 垃圾信息库命中、频次、可用的最近记录时间 | **免 Key**只读查询；不是全网攻击举报库；本轮未核实当前每日限额 |
| ipapi.is | 归属；代理、VPN、Tor、托管、近期滥用、公司/ASN 滥用比例 | 匿名 30 次/日只有精简归属；**免费 Key 1000 次/日**有完整字段 |
| IPQS | IP-only 欺诈分、代理/VPN/Tor、近期滥用等 | **需要 Key，有免费方案：每月 1000 credits**；高级字段及计费以账户套餐为准 |
| AbuseIPDB | 举报置信度、报告数、独立举报者数和最近举报时间 | **需要 Key，免费个人方案 1000 次 Check/Report/日**；当前查询窗口为 30 天 |

先确认你的服务配额和价格，再启用。知彼不会推测或补全套餐没有返回的字段。

## 不注册账户，直接完成一轮信誉检查

```bash
python3 skills/zhibi/scripts/zhibi.py scan --network --reputation
```

`--reputation` 固定选择 IPWhois、ProxyCheck、IPQuery、StopForumSpam，不读取密钥文件。
检查 AdsPower 等实际浏览器时，先用浏览器探针导出，再执行：

```bash
python3 skills/zhibi/scripts/zhibi.py scan --network --reputation --browser /path/to/zhibi-browser.json --target browser
```

此时查询对象是浏览器出口，查询请求由本机脚本发起。两者可能不同，接收方能看到这两个 IP。
不用 Cookie、登录态、语言、UA 或交易信息查询。报告只代表采样时刻，不自动宣称检测了到 目标服务 的所有路由。

## 可选增强：想取得额外数据时再配置

**IPQS、AbuseIPDB 和 ipapi.is 都是 optional，不是使用门槛。** 默认检测无需注册这三家。
只选择你想增加的数据来源，不必全部申请；不配置不会影响已经取得的免 Key 检测结果。
详细字段或免费额度缺失也不会被写成用户风险。

例如你想增加 IPQS 欺诈分，注册并取得 Key 后，在自己的终端运行：

```bash
python3 skills/zhibi/scripts/zhibi.py configure ipqs
```

其他两家分别用 `configure abuseipdb` 和 `configure ipapi`。想一次配置多家时，可以选用
`configure all` 向导；它保留已经配置的 Key，直接回车可跳过尚未申请的来源。
输入不回显，保存到 `~/.zhibi/providers.json`。不能隐藏输入时会停止，不会退回明文输入。
POSIX 文件权限为 600；已有文件权限过宽时拒绝读取。Windows 的访问控制需按你的用户环境核对。
安装后的 Skill 使用其实际目录中的 `scripts/zhibi.py`。

| 来源 | 注册与取 Key | 免费额度 | 补齐内容 |
| --- | --- | --- | --- |
| IPQS | [注册免费账户](https://www.ipqualityscore.com/create-account)，完成邮箱验证，在 Dashboard 的 API Keys 管理中取 Key | 1000 credits/月 | IP 欺诈分、代理标签、近期滥用标记 |
| AbuseIPDB | [注册 Individual](https://www.abuseipdb.com/register?plan=free)，在账户 Dashboard 创建 API Key | 1000 Checks/Reports/日 | 最近 30 天举报数、独立举报者数、最近举报时间、滥用置信分 |
| ipapi.is | [注册免费账户](https://ipapi.is/app/signup)，登录 Dashboard 取 API Key | 1000 次/日 | 代理/VPN/机房等标签、公司与 ASN 网段滥用比例 |

三家当前都不要求信用卡。账户注册和验证由你完成；配置只保存，不代表服务已接受 Key。
之后对实际浏览器出口执行扫描，才能确认认证、额度和返回字段。Key 仅发往对应供应商；
供应商会收到所查 IP 和请求来源 IP，不接收 目标服务 Cookie 或登录材料。

也支持 `ZHIBI_IPAPI_KEY`、`ZHIBI_IPQS_KEY`、`ZHIBI_ABUSEIPDB_KEY` 环境变量。
不要在会被记录或展示的命令行中写入密钥字面量；使用你已有的本地秘密管理方式。
`providers` 命令只展示是否已配置，不打印内容。

## 启用你选中的增强来源

**保存 Key 不会自动启用该来源。** 在原有检测命令后显式添加对应的 `--provider`。
例如只选择 IPQS，并继续检测实际浏览器：

```bash
python3 skills/zhibi/scripts/zhibi.py scan --network --reputation --provider ipqs --browser /path/to/zhibi-browser.json --target browser
```

浏览器导出应来自本次实际使用环境的新测量。只测 Agent 时才省略 `--browser` 和 `--target browser`。
添加 `--dry-run` 可以先查看请求计划：

```bash
python3 skills/zhibi/scripts/zhibi.py scan --network --reputation --provider ipqs --dry-run
```

去掉 `--dry-run` 执行；添加 `--ipv6` 会增加 IPv6 测量及对应地址的情报查询。
每个来源每个目标地址最多请求一次，无自动重试或备用服务跳转。
密钥使用 Header 或 JSON POST 传递，不放进 URL、浏览器页面或报告。

**需要 Key 不等于必须付费。** IPQS、AbuseIPDB 和 ipapi.is 可先申请各自免费账户，在本机 `configure` 后显式添加相应 `--provider`。
ProxyCheck 官方还提供免费 Key 的 1000 次/日额度，但本适配器当前只接免 Key 路线，不接受它的 Key。
付费主要用于扩大额度或获取特定高级数据；当前这套免 Key 检查不要求任何付费服务。

## 怎样读结果

**为什么出现 0/100？** 这是供应商原始风险分，越低表示其评估的风险越低，不是检测完成度。
0 表示接口确实返回 0；缺失、未配置 Key 和请求失败不会补零。0 分及代理标签未命中
不能证明你没有使用代理，也不能证明 目标服务 内部风控会给出同样判断。报告不计算统一总分。

- **已取得**：预期字段已返回，仍须按原始语义解释。
- **部分字段缺失**：例如匿名接口只提供归属；空值不等于 false。
- **未配置密钥 / 配额限制 / 认证受限**：没有该来源的结果，不能写成零分。
- **超时 / 无效响应**：测量没有成功，其他来源独立保留。
- **来源分歧**：展示各自结果，不做多数投票或分数平均。

未选择或未配置的增强来源放在“可选增强”中，不占据首屏评分卡，也不成为必须完成的任务。
若你主动选择的增强来源认证失败、超时或缺字段，报告仍保留真实状态，免 Key 来源结果照常展示。

IPQS 的查询固定为 `strictness=0`、`allow_public_access_points=true`，不发送用户语言、UA、用户 ID 或交易资料。
ipapi 的网段比例描述整个公司或 ASN 网络；AbuseIPDB 的分数描述滥用举报置信度。
查询时间、数据更新时间和最近举报时间分别显示；数据源没有提供的时间会保持未知。

ProxyCheck 固定 v3 `24-June-2026`，`tag=0` 禁止保存到其正向检测日志；这不等于服务端完全无日志。
保留供应商默认活动有效期，不声称统一的 7 天或 30 天窗口。`attack_history=null` 显示未提供，不能填成 0。
其检测置信度与风险分分别展示；风险分已含网络类型基线，不是欺诈概率。
IPQuery 风险分不套用 IPQS 的 75/90 阈值；当前官方文档未给出校准或分段阈值。
StopForumSpam 的频次和最近记录只属于垃圾信息库，不能写成 AbuseIPDB 的举报数量或“近期零滥用”。

## 官方依据

核对日期：2026-10-19。接口和套餐可能变化，使用前以当前服务文档为准。

- [IPWhois 文档](https://ipwhois.io/documentation)
- [ipapi.is 接口和匿名覆盖](https://ipapi.is/developers.html)
- [IPQS 数据提交与 Header 鉴权](https://www.ipqualityscore.com/documentation/about-ipqs-apis/submitting-data-to-ipqs-apis)
- [IPQS 响应字段](https://www.ipqualityscore.com/documentation/proxy-detection-api/response-parameters)
- [AbuseIPDB Check](https://docs.abuseipdb.com/#check-endpoint)
- [ProxyCheck v3、免费额度与活动语义](https://proxycheck.io/api/)
- [IPQuery 公共 API](https://ipquery.io/)
- [StopForumSpam 官方关于查询无需 Key 的说明](https://www.stopforumspam.com/forum/viewtopic.php?id=1079)；当前接口已实测，usage 页面本轮访问受限
- [ipapi.is 免费与付费差别](https://ipapi.is/pricing.html)
- [IPQS 免费账户与 credits](https://www.ipqualityscore.com/create-account)
- [AbuseIPDB 免费个人方案](https://www.abuseipdb.com/pricing)

ProxyCheck、IPQuery、StopForumSpam 和 IPWhois 已在真实 AdsPower 出口上完成查询。
IPQS、AbuseIPDB 及 keyed ipapi 尚无用户自有 Key 的现场验证；相应适配器经过响应契约与故障模拟测试。
