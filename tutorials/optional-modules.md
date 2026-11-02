# 可选工具：需要什么，就打开什么

基础流程仍只需要 Python 3.9+，不需要 Key 或 pip。以下命令中的 `zhibi` 可替换为 `python3 <已安装 Skill>/scripts/zhibi.py`，也可用独立核心 `python3 zhibi-core.pyz`。

## 一次查全

```bash
zhibi session --preset all --network
```

在实际使用的 AdsPower/Chrome/Safari 打开终端给出的临时 `http://127.0.0.1:端口/随机路径`。点击“开始观察”，再点“保存到本机并生成报告”。页面把结果交给本机核心，核心生成 `report/report.html`。不需要 AdsPower API 权限，不需要手工传 JSON。服务仅绑定本机，15 分钟过期；不提供目录浏览或私人报告 HTTP 下载。

Agent 只读 `agent-summary.json`。实际 IP、渲染哈希、设备属性、原始解析器及配置留在私人文件；不要把它们粘到聊天或检测网站。

| 需求 | 命令 | 说明 |
| --- | --- | --- |
| 查看全部开关和接收方 | `zhibi modules` | 只读模块目录，不联网 |
| 先看全量请求范围 | `zhibi suite --preset all --network --dry-run` | 不执行请求或修改 |
| 当前终端基础检查 | `zhibi suite --preset basic --network` | 原有四来源免 Key 组合 |
| 只测服务与 DNS | `zhibi suite --preset custom --module services --module dns --network` | 自定义模式不暗加情报提供商 |
| 只增加 DB-IP | `zhibi suite --preset custom --network --provider dbip` | 数据源可重复指定 |
| 导入已保存浏览器结果 | `zhibi suite --preset all --network --target browser --browser /本机路径/zhibi-browser.json` | IP 查询要求观测不超过 15 分钟 |
| 对比两次报告 | `zhibi suite-compare /前次目录 /后次目录 --same-context` | IP 在本地比较；模块对比当前只比较状态 |
| 脱敏分享预览 | `zhibi suite-share /检测目录 --out /新的分享目录` | HTML/TXT/JSON，仅状态，**不上传** |
| English share summary | `zhibi suite-share /run --language en --out /new-directory` | 英文摘要；完整详细报告仍主要中文 |

`all` 是全部已接入的只读模块，并不修改环境、安装依赖、购买服务或伪造未配置项的结果。账户接口没有 Key 就不发请求。浏览器渲染功能可在页面取消；未选择不算失败。

## 数据源与费用

下表是 2026-10-19 核对的产品边界；配额和商用许可以供应商当前账户条款为准。**免费账户不等于所有字段免费。**

| 来源 / 开关 | 无 Key 能做什么 | Key / 付费边界 | 官方说明 |
| --- | --- | --- | --- |
| `ipwhois` | 国家/ASN/组织 | 不提供欺诈分 | [IPWhois](https://ipwhois.io/documentation) |
| `proxycheck` | 标签、原始风险分、可用活动字段 | 本适配器使用公开额度 | [ProxyCheck](https://proxycheck.io/api/) |
| `ipquery` | 标签及风险分 | 受公共接口限流约束 | [IPQuery](https://ipquery.io/) |
| `stopforumspam` | 库内命中、频次 | 不等于全网滥用历史 | [StopForumSpam](https://www.stopforumspam.com/usage) |
| `ipapi` | 当前匿名接口仅精简归属 | 自备免费 Key 可取得更多标签/网络滥用比例 | [ipapi.is](https://ipapi.is/developers.html) |
| `ipqs` | 不查询 | 自备 Key，免费 credits/付费高级字段 | [IPQS](https://www.ipqualityscore.com/documentation/proxy-detection-api/response-parameters) |
| `abuseipdb` | 不查询 | 自备免费账户 Key；30 天 Check 窗口 | [AbuseIPDB](https://docs.abuseipdb.com/#check-endpoint) |
| `ipinfo` | 不查询 | 免费 Lite Token；只有国家/ASN，无付费代理情报 | [IPinfo Lite](https://ipinfo.io/developers/lite-api) |
| `ipregistry` | 不查询 | 自备 Key；试用额度及后续方案依账户 | [IPregistry](https://ipregistry.co/docs) |
| `ip2location` | 官方免 Key 地理/代理字段，按实际响应 | 免费 Key 提高额度；高级 fraud_score 依套餐，原量表 **0–99** | [IP2Location.io](https://www.ip2location.io/ip2location-documentation) |
| `dbip` | Free API 国家/地区 | Free 接口没有 ASN/欺诈分；IP Geolocation by DB-IP | [DB-IP Free](https://db-ip.com/api/free.php) |
| `scamalytics` / `scamalytics-us` | 不查询 | EU/US 账户绑定节点；按计划计费，自备用户名与 Key | [Scamalytics v3](https://docs.scamalytics.com/ip-fraud-risk-api/v3/) |

自行注册供应商账户并取得 Key 后，在**自己的终端**运行 `zhibi configure ipinfo` 等命令。输入隐藏，配置存于本机 `~/.zhibi/providers.json`。不要把 Key 发给 Agent。`configure all` 仍只引导最初的 IPQS、AbuseIPDB、ipapi.is 三家，避免强迫用户注册所有服务。

Scamalytics 输入格式是 `username:api-key`；EU 使用 `scamalytics`，US 使用 `scamalytics-us`。该服务文档要求在 HTTPS URL 查询串中传 Key；本工具不打印 URL、异常正文或 Key，不跟随重定向。其聚合数据与 IPinfo、MaxMind、IP2Location、DB-IP 有重叠，不当作多份独立证据。

## 各模块如何解释

| 模块 | 真实观测 | 不能推出什么 |
| --- | --- | --- |
| `services` | 10 个固定公共端点的 HTTP 响应，含 目标服务 Web/API/下载与其他产品 | 403/405 不等于封号；200/跳转不等于登录成功、地区解锁或付费资格 |
| `smtp` | Gmail/Outlook 各 25/465/587 的 TCP 连接 | 不发送邮件，不说明邮件投递能力、SMTP 登录或 IP 邮件信誉 |
| `tls` | tls.peet.ws 对**采集主机**请求的 TLS/HTTP 观测 | 不能代表 AdsPower；浏览器 TLS 另在探针页面选 |
| `dns` | dig 默认解析链的解析器/ECS 信息 | 不代表浏览器 DoH、所有分域解析或没有泄漏 |
| `dnsbl` | Spamhaus ZEN/SpamCop；Spamhaus 先查正负控制项 | `127.255.*` 是错误，不是命中；PBL 是发送邮件策略名单，不等于恶意 |
| `feeds` | 下载 IPsum / Spamhaus DROP 后本地比对，记录数据 SHA-256 | 不上传被查 IP；请求源 IP 仍对下载站可见；IPsum 上游数量不是独立证据数 |
| `route` | 通过用户指定代理或网卡测量 IPv4 | 失败不退回直连；不改变系统默认代理；不能替代浏览器测量 |
| `native` | 采集主机 CPU/系统/区域与浏览器自报对照 | UA 改写、隐私限制、虚拟化可以造成正常差异 |
| `cli` | 目标服务 可执行文件、安装方式、`--version` | 不登录，不验证账户套餐或调用权限 |
| `mmdb` | 自备 MMDB 离线查国家/ASN，记录库类型/构建日期 | 没有代理/欺诈字段就不生成这些结论 |
| `checkcc-model` | 固定版本地区模型、客户端权重及每项贡献 | 不代表 上游服务商 规则；不会影响主报告判断；贡献总和不是概率 |

浏览器扩展包括 Canvas 两次渲染比较、本机哈希、WebGL 渲染器、离线 Audio 样本、可选 TLS 和[自建 DNS](self-hosted-dns.md)。Audio 不录音不播放；定位项不申请权限、不读坐标。渲染有差异时只报告差异，不宣判设备真伪。

## 可选配置

用本地编辑器保存 `suite-config.json` 并将权限设为 `600`。只填写需要的字段：

```json
{
  "route": {"proxy_url": "socks5h://127.0.0.1:10818"},
  "mmdb": "/your/path/GeoLite2-ASN.mmdb",
  "region": "auto"
}
```

`route.interface` 可指定网卡；`route.expected_ip` 可核对这条显式路径；顶层 `expected_ip` 用来核对**所选浏览器/终端**的实际 IP。不要把凭据放在命令行：认证代理 URL 留在配置文件，核心通过 curl stdin 传递，不写 argv 或报告。

```bash
zhibi suite --preset all --network --config /本机路径/suite-config.json
```

MMDB 为可选依赖：在专用 Python 环境安装 `maxminddb>=2.6,<4`，用同一 Python 运行 Skill。用户自备有权使用的数据库；本项目不分发商业数据库。`dig`、`curl`、`ssh` 只在对应模块需要时使用。

IPsum 数据源：[项目与许可](https://github.com/stamparm/ipsum)；Spamhaus：[DROP 数据与使用条件](https://www.spamhaus.org/faqs/do-not-route-or-peer-drop/)、[DNSBL 使用条件与控制查询](https://www.spamhaus.org/faqs/dnsbl-usage/)。下载/查询受其政策约束，不能把个人免费额度当作商业批量授权。

## AdsPower 无法打开本机地址时

部分代理环境访问 `127.0.0.1` 会失败。保留原配置，改用：

```bash
zhibi session --file --preset all --network --out my-check
```

在同一浏览器打开命令返回的 `probe.html`，点击「开始观察」。完成后下载 JSON。浏览器使用默认 `~/Downloads` 时，核心只监听本次随机命名的一个下载文件，自动接收；自定义下载目录则把该文件保存或复制到命令显示的 **save_download_as** 路径（`my-check/browser.private.json`）。核心验证后自动生成 `my-check/report/report.html`，不会扫描下载目录或读取其他浏览器资料。这个模式不启动 HTTP 服务。
