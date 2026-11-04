# Skill 整合版验收记录

## 0.2.0a3：可选浏览器检查验收（2026-10-19）

- Python 3.12：113 项测试通过；系统 Python 3.9：113 项运行，其中 1 项可选 jsonschema 检查跳过。
- `node tests/browser-details.cjs`：默认不采集、六模块读数、UA 匹配优先级、语言脚本、权限超时/不支持、字体测量不稳定等用例通过。
- 应用内浏览器实测：默认三个网络项与六个深入项均未选择；勾选六个深入项后均返回 `ok`。实际点击保存，使用系统生成的下载文件完成 Python 导入与 HTML 报告生成；没有联系外部服务。
- 实测对象是应用内浏览器，用于功能验收；不是 AdsPower 复测。没有将此结果当成 目标服务 注册通过证明。
- 本地 HTML 的三列表格直接显示所选属性；详细字体和 UA 读数折叠展示。使用合成数据检查实际渲染，不公开私人实测值。
- 验证未选项不算失败、中文/字体/CPU 不增加 IP 风险项、任意额外字段拒绝导入、HTML 转义、Agent 摘要不含原始属性，v1/v2 导入保持兼容。
- 独立 Skill ZIP 的隔离安装与自带核心验证通过；fresh wheel 安装通过；Skill 验证器与本地链接/契约检查通过。
- 作者中英文序言与上一提交逐字比较保持一致。MIT 通知、固定上游提交与源文件哈希随新模块打包。

新增模块的浏览器 API 依据：[Permissions.query](https://developer.mozilla.org/en-US/docs/Web/API/Permissions/query)、[hardwareConcurrency](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/hardwareConcurrency)、[NavigatorUAData](https://developer.mozilla.org/en-US/docs/Web/API/NavigatorUAData)。定位权限仅指当前页面，逻辑 CPU 数是浏览器暴露的值，不等同物理 CPU 型号。

本轮仍未验收 Windows/Linux 实机、目标客户端 宿主和需要用户 Key 的现场查询；没有成功云端 CI 证据。其余未交付范围以[能力覆盖清单](capability-coverage.md)为准。

## 既有 0.2.0a2 验收记录


日期：2026-10-19。版本：0.2.0a2。本地 macOS 验收；已在私有 GitHub 分发，无 PyPI 发布或成功云端 CI 结果。

本轮完整链路见[GitHub 下载与免 Key 实测](../archive/onboarding-validation.md)。

## 当前交付与证据

| 检查 | 结果与范围 |
| --- | --- |
| Python 行为 | 最新 Python 3.12：109 项全部通过；Python 3.9 的旧版本验收记录见下方历史 |
| 上游复用 | CCBaga/CheckCC 固定提交与源文件哈希、实际 JS 适配、MIT 通知与迁移用例；不代表上游整套产品验收 |
| 多源情报 | 正常、缺字段、缺 Key、超额、认证错误、超时、错误主体、重复键、异常数值与超大响应均有测试 |
| 真实免费查询 | 2026-10-19 04:03 UTC：经授权的 AdsPower 浏览器新采集 IPv4 经 IPWhois、ProxyCheck v3、IPQuery、StopForumSpam 查询均 ok；两家风险分均 0，四项代理/托管标签均 false，垃圾信息库频次 0；不是账号结果 |
| DNS 真实执行 | dig 诊断查询成功，收到解析器记录与 ECS；修复了 macOS dig 不支持 -r 的兼容问题；不证明浏览器 DNS 或缓存新鲜度 |
| 浏览器页面 | 实际 Chrome 测试单文件、默认离线、模拟双栈端点、失败清除旧值、无自动重试、真实下载与 Python 导入、390px 布局 |
| IPv6 默认策略 | 未确认显示专用环境操作步骤；已核对配置可记录为通过。新用例验证证据绑定、陈旧确认拒绝、成功 IPv6 不可确认关闭、失败请求不当成禁用 |
| WebRTC | ICE 解析/失败清理测试；本次 AdsPower 实测超时、0 候选，保留为未取得可比路径 |
| 报告 | 基础和增强 HTML 打开不加载网络资源；来源可展开，先显示需核对事项；桌面/移动无横向溢出 |
| 主动风控解释 | 动机、范围、正常反例、来源与行动；Graph 边闭合；伪造解释和未知字段不能进入摘要 |
| 复查 | 不同对象、查询覆盖、时序与上下文分别处理；私人 IP 在核心内比较 |
| 演示隔离 | 三个 scan-demo 使用纯合成数据，不联网、不采集开发机器配置 |
| 隐私 | Key 不进 URL/报告/摘要，IPWhois 不读取密钥库；浏览器原始属性与 DNS 子网留在私人文件 |
| Skill 独立包 | 仓库外解压、Python 3.9 隔离执行、无 pip；离线扫描、三种情报演示、导出、高级探针、DNS 离线与计划、许可证和相对链接验证 |
| wheel 安装 | 临时新虚拟环境、本地 wheel 离线安装、离开源码目录运行；包含增强命令与资源 |
| 独立 Agent 行为 | 仅凭交付 Skill 完成“离线检查+多源示例”和“按三步准备流程协助”两个请求；正确区分未知/合成/真实，无账号操作 |
| 作者文字 | README 当前序言按保存的 SHA256 对照保持原文 |

独立 Agent 测试发现的服务说明歧义已经修正：IPWhois 的 dry-run 不再列出密钥字段，实际查询也不读取密钥库。
此测试是给定 Skill 的行为验收，不等于各宿主的自动发现、安装 UI 或完整用户研究。

## 尚未验证的效果与环境

- IPQS、AbuseIPDB 及 keyed ipapi 的真实 Key/套餐现场结果：目前为官方契约与合成响应验证。
- 账号注册、支付、长期使用、封禁与误报率：未做实验，也不把供应商评分当作账号结果。
- 浏览器真实 DNS、唯一随机子域与权威日志关联、TLS/HTTP 服务端指纹、完整网络实体关系图：没有假装已经测得。
- Windows/Linux 实机、Windows ACL、目标客户端 宿主发现及自然语言调用：仍未验证。Codex CLI 0.159.2 已通过真实 skills/list 识别；GitHub Actions 因账号账单/支出限额未能启动。
- 作者三个账号的具体过程与观察窗口：待作者补充，已提供写作区和模板。

## 可复现验收

```bash
python -m unittest discover -s tests -v
python scripts/build_examples.py
python scripts/build_start.py
python scripts/render_readme.py
python scripts/check_repository.py
python scripts/verify_skill.py
node tests/browser.cjs
python -m zhibi browser --advanced --out new-probe.html
node tests/browser-network.cjs
python -m build
python scripts/verify_distribution.py
python scripts/package_release.py
```

高级浏览器 UI 测试从 `.preview/network.html` 读取页面；运行前应使用高级探针命令导出到该路径。
开发依赖、Playwright 与本机浏览器选择见 [贡献指南](../../CONTRIBUTING.md)。
默认验收不执行外部 API 或 DNS 请求；真实请求单独运行并记录，不进入公开示例。

## 历史：0.1 基础版

以下保留原验收记录，当前交付以本页上半部分为准。

### 本地 alpha 验收记录

日期：2026-10-18。版本：0.1.0a1。环境：macOS，Python 3.12；另用系统 Python 3.9 执行核心测试。

## 已完成

| 验证 | 结果与范围 |
| --- | --- |
| Python 核心测试 | 49 项通过；Python 3.12 包含 JSON Schema 校验 |
| Python 3.9 核心行为 | 48 项通过、1 项因未安装可选 jsonschema 跳过；修复了 HTTPError 无响应体时的兼容问题 |
| Skill 结构 | 官方 skill-creator 的 quick_validate 通过 |
| 浏览器 UI | 实际 Chrome 自动化，桌面 1280/1440 与手机 390 宽度无页面横向溢出 |
| 无安装入口 | 将 start.html 复制到独立临时目录，直接打开完成检查，不依赖源码目录、Python 或其他资源 |
| 页面直接给结果 | 四项浏览器/出口读数、下一步事项、本地文本保存；JSON 导出位于可选折叠区 |
| IP 查询失败 | 503 模拟显示“未测成”，不重试，清掉前次成功 IP；不产生账号风险结论 |
| 离线边界 | 打开报告、打开探针、执行默认探针均未产生 HTTP 请求 |
| 浏览器联网与导出 | 一次显式启用的模拟端点请求，JSON 下载与预览一致；保留自动化标记 |
| 本地真实检查 | 成功生成报告，未读 目标服务 凭据或执行 目标服务 |
| 实际外部服务 | 本次 CLI 的 ipify IPv4 与 IPWhois 国家/ASN 均返回可用结果；原始 IP 未入库 |
| 来源时间 | 生效日、复核期限、未来核对时间及带时区时间比较均有行为测试 |
| 隐私与输入 | 代理凭据不进入观测；摘要重建；未知字段、超大输入、重复键拒绝 |
| 报告安全 | HTML 转义与 CSP，文件不覆盖，POSIX 权限检查 |
| 终端输出 | 即使重定向环境默认 ASCII，CLI 也输出有效 UTF-8 |
| 本地文档 | 相对链接、报告 Schema、规则引用检查通过 |
| 理论准入 | proposed/contradicted/retired 和跨平台类比不能生成确定结论；主张引用的过期来源同样阻止判断 |
| 知识库与学习 | 11 来源、17 主张、14 特征、10 规则、6 章节的引用完整性；手册离线、练习答案可展开 |
| 准备与分流 | 按产品生成待完成清单；区分 API 与 Web 的 403、额度与用户报告的账号限制 |
| 本地事件图 | 图边闭合，默认不比较上下文；不输出原始 IP，不合并真实与模拟记录 |
| 新增网络真实验证 | 本次 IPv4 成功；IPv6 端点测量失败并保留 unknown；公共首页 HEAD 返回 302，未跟随重定向 |

## 安装包验证

wheel 与源码包均由本地构建产生。scripts/verify_distribution.py 在临时新虚拟环境中，
从本地 wheel 离线安装，离开源码目录调用 CLI，验证规则数据、来源、报告 CSS 和浏览器 HTML 随包存在。
本轮已通过全新虚拟环境验证；新增 theory、learn、lab、guide、triage 同样从安装包运行。
运行 scripts/package_release.py 生成含 Skill、文档与 CI 的源码 ZIP，摘要位于 dist/SHA256SUMS。

## 结果不能证明什么

- 浏览器自动化验证的是软件行为，不能替代用户实际注册浏览器的测量。
- 没有执行真实账号注册、登录、身份验证、支付或封禁实验。
- 还未验证各 Agent 宿主自动发现与自然语言交互。
- GitHub Actions 配置已添加，但远端尚未创建，不能宣称云端 CI 通过。
- Windows/Linux 实机运行、Windows ACL 与更多代理/DNS 组合仍待验收。
- 测量成功不构成平台资格判断、风险概率或防封效果证据。

## 可复现命令

```bash
python -m unittest discover -s tests -v
python scripts/check_repository.py
python scripts/build_examples.py
python scripts/build_knowledge_docs.py
python scripts/render_readme.py
node tests/browser.cjs
python -m build
python scripts/verify_distribution.py
python scripts/package_release.py
```

浏览器验收需要开发环境中的 Playwright 与浏览器，详见 [贡献指南](../../CONTRIBUTING.md)。
外部真实请求不是自动化测试的默认步骤。

## 对当前交付的核对

| 用户要求 | 已落地的交付 | 验证与边界 |
| --- | --- | --- |
| 用户能够用 | 默认打开 start.html 做基础自检；深入检查保留 CLI 和 Skill | 单文件使用及全新环境安装验证；宿主自动发现仍待实机验证 |
| 用户能够学 | 六章离线手册、三个实验、用户与开发者教程 | 浏览器操作和无网络边界通过；可用性研究待进行 |
| 自己的风控理论 | 平台目标→事件/对象→特征/关系/时间→处置框架，主张库和证据图 | 可追溯与准入逻辑已测试；未声称还原内部规则或验证预测效果 |
| 给作者 tutorial 留位置 | 独立目录、八篇主题、第一人称模板与作者序言草稿 | 已记录作者自述的三个 20x Max 账号稳定使用经历；具体实操与使用时长待补，不属于软件测试结论 |
| 用户看懂 README | 开头明确工具形态与用途，三步开始，实际界面截图；研究内容下沉 | 根据用户反馈简化；本地桌面/移动预览验证，未发布 GitHub |

项目原始方案中的可回退系统修复、完整政策变更库和社区案例规模化收集仍为后续工作。
当前程序不暴露系统自动修改能力。软件 alpha 的完成与长期研究成效是不同验收对象。
