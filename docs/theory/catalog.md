# 主张与特征目录

这是可检验的研究框架，不是还原后的 目标服务 内部模型。

平台目标 → 业务事件与判断对象 → 可见证据/隐藏状态 → 处置 → 用户行动

## 可追溯的主张

### 资格条件与 IP 归属是不同证据

supported · 测量与实现语义

知彼只把 IP 归属作为网络背景，注册条件由真实情况和有效官方政策核对。

不支持的扩展：没有恢复 目标服务 的地区识别实现。

修订条件：若实现用 IP 自动填写真实地区或给出资格通过结论，本项目即违反此主张。

- 知彼：观测、解释与账号结果的边界 — docs/research-method.md
- 上游服务商：Safeguards warnings and appeals — https://support.claude.com/en/articles/8241253-safeguards-warnings-and-appeals
- 上游服务商：Supported Regions Policy（需核对生效时间） — https://www.anthropic.com/legal/supported-regions

### 出口差异首先是路径观测

supported · 测量与实现语义

可比观测可以确认诊断端点的出口是否相同；有意分流不自动成为待修复故障。

不支持的扩展：出口统一能够避免账号限制。

修订条件：若时间、端点或地址族不一致仍输出确定比较，规则应撤回修正。

- 知彼：观测、解释与账号结果的边界 — docs/research-method.md
- ipify IPv4 endpoint documentation — https://www.ipify.org/

### 代理变量只覆盖一种配置入口

supported · 测量与实现语义

可以检查环境变量冲突和工具兼容性，不能由变量缺失断言系统没有代理。

不支持的扩展：某种代理类型对应 目标服务 的账号判定。

修订条件：测试发现导出含代理凭据，或把环境变量当作完整网络路径。

- 知彼：观测、解释与账号结果的边界 — docs/research-method.md

### 语言不是身份结论

supported · 测量与实现语义

浏览器语言与时区仅作为上下文；知彼不由它们自动断定真实地区、国籍或违规。

不支持的扩展：目标服务 不采集这些字段，或从不使用它们。

修订条件：正常多语言样例因语言而被扣分或要求改成特定国家设置。

- 知彼：观测、解释与账号结果的边界 — docs/research-method.md

### 安装存在性与账号状态分开

supported · 测量与实现语义

PATH 中能找到客户端仅能说明当前终端可发现程序。

不支持的扩展：客户端是官方版本、已认证或账号正常。

修订条件：客户端存在性被输出为已登录或账号安全。

- 知彼：观测、解释与账号结果的边界 — docs/research-method.md

### 配置文件不等于有效 DNS 路径

supported · 测量与实现语义

解析器配置数量不能证明浏览器使用哪条 DNS 路径。

不支持的扩展：浏览器 DoH、系统分流和目标服务端看到的实际请求路径。

修订条件：规则只凭 resolv.conf 输出泄漏或无泄漏。

- 知彼：观测、解释与账号结果的边界 — docs/research-method.md

### 供应商标签不是平台决定

supported · 测量与实现语义

第三方国家/ASN 可提供背景；冲突应保留并核对，不转换成平台风险概率。

不支持的扩展：目标服务 使用同一数据库或标签。

修订条件：供应商标签被直接当作 目标服务 违规证据。

- 知彼：观测、解释与账号结果的边界 — docs/research-method.md
- IPWhois IP lookup documentation — https://ipwhois.io/documentation

### 局部图不能补出平台全局图

supported · 测量与实现语义

只连接已有且带来源的观测；共同出口不直接合并账户或人。

不支持的扩展：平台已把用户与某群体关联。

修订条件：缺少身份或时间证据仍建立确定的人际关系边。

- 知彼：观测、解释与账号结果的边界 — docs/research-method.md

### 已披露场景中有行为与关联分析

supported · 官方披露范围

上游服务商 在 API 蒸馏调查中披露了行为模式和关联线索的使用。

不支持的扩展：同一模型用于普通注册，或某个字段的权重和阈值。

修订条件：来源撤回、范围改变，或我们的转述超出所披露 API 活动。

- 上游服务商：Detecting and preventing distillation attacks — https://www.anthropic.com/news/detecting-and-preventing-distillation-attacks

### 反滥用处置包含多种动作

supported · 官方披露范围

2026-10 的披露包含内容层约束、请求检测与账号处置等措施，并承认正常用户的取舍。

不支持的扩展：公布的误报指标等于注册误封率。

修订条件：对应措施被撤回或适用范围更新；需按版本修订。

- 上游服务商：Strengthening our defenses against distillation attacks — https://www.anthropic.com/research/distillation-defenses

### 支付风控是另一类决策问题

supported · 跨平台类比

Stripe Radar 的公开设计将付款评估与多种处置连接，适合学习决策对象和成本取舍。

不支持的扩展：目标服务 使用该服务、配置或阈值。

修订条件：引用文档改变对应对象或处置语义。

- Stripe Radar：Transaction risk prevention — https://docs.stripe.com/radar/transaction-risk-prevention

### 机器人分数有自己的目标变量

supported · 跨平台类比

Cloudflare 的 bot score 对应请求自动化判断；未计算状态与安全结论不同。

不支持的扩展：目标服务 的每次请求都采用该引擎或某个得分阈值。

修订条件：我们把该分数解释成账号封禁概率。

- Cloudflare：Bot scores — https://developers.cloudflare.com/bots/concepts/bot-score/

### 关联信号需要上下文

supported · 跨平台类比

Google Account Defender 文档说明关联账户标签可能需要进一步调查，不能自动判为坏账户。

不支持的扩展：目标服务 使用 Google 的账户图。

修订条件：文档改义或我们把关联数量直接等同违规。

- Google：Account defender — https://docs.cloud.google.com/recaptcha/docs/account-defender

### 阶段决定证据和标签应如何解释

proposed · 待检验的平台假设

研究应按注册、登录、付款和使用阶段分层，避免把阶段差异误认为某个特征的因果作用。

不支持的扩展：已估计出各阶段的模型或阈值。

修订条件：带可靠阶段标签的样本显示分层不能改善问题分流，需要修订该研究假设。

- 知彼：观测、解释与账号结果的边界 — docs/research-method.md
- 上游服务商：Safeguards warnings and appeals — https://support.claude.com/en/articles/8241253-safeguards-warnings-and-appeals
- 目标 API：Errors — https://platform.claude.com/docs/en/api/errors

### 明确未知能减少无效操作

proposed · 待检验的产品假设

带依据、反例与未知的指导可能减少不必要的环境修改和采购。

不支持的扩展：已有足够用户实验或防封效果数据。

修订条件：对照用户研究中，理解度、问题解决或无效操作没有改善。

- 知彼：观测、解释与账号结果的边界 — docs/research-method.md

### IPv6 观测受客户端与端点约束

supported · 测量与实现语义

IPv6 专用端点只观测当前请求链路出口，不能单凭结果证明直连、泄漏或浏览器行为。

不支持的扩展：没有建立 IPv6 可用性与 目标账号处置的因果关系。

修订条件：若实现能够验证本机到目标的每段路径，应扩充当前范围；端点接口变化时需重新验证。

- ipify IPv4 endpoint documentation — https://www.ipify.org/
- 知彼：观测、解释与账号结果的边界 — docs/research-method.md

### 公共入口响应与账号判断分离

supported · 测量与实现语义

不携带会话的公共首页 HEAD 请求只能提供连接或 HTTP 状态，不能验证账号登录状态。

不支持的扩展：没有将 200 认作账号通过，也没有将 403 认作封号。

修订条件：若测量开始携带账号会话或调用认证接口，当前实现范围已改变且必须重新审查。

- 知彼：观测、解释与账号结果的边界 — docs/research-method.md

## 特征卡

### eligibility · 真实资格背景

可见范围：user_declared

派生方式：真实场景与有时效的政策逐项对照。

正常反例：IP 定位不等于实际使用地区。

验证方式：人工核对来源、生效时间和目标产品；不采身份材料。

关联主张：policy-not-ip

### route-comparability · 诊断端点路径一致性

可见范围：direct_local

派生方式：比较同端点、地址族和相近时间的观测。

正常反例：有意分流、不同目标、负载均衡、历史样本。

验证方式：合成反例、实际浏览器复测；检测失败保留未知。

关联主张：route-not-ban

### proxy-configuration · 代理配置入口

可见范围：direct_local

派生方式：仅提取存在、认证存在、兼容性和冲突布尔量。

正常反例：系统代理、透明网关与浏览器扩展不可由此排除。

验证方式：在子进程或局部字典中注入冲突，再比较修正前后。

关联主张：proxy-scope

### browser-context · 浏览器基础能力

可见范围：direct_local

派生方式：在实际打开的探针页观察 Cookie 启用和存储能力。

正常反例：本地文件权限不等于 目标站点权限；旅行和多语言使用。

验证方式：同浏览器人工复验，自动化浏览器只能验软件。

关联主张：locale-not-identity

### client-readiness · 客户端可发现性

可见范围：direct_local

派生方式：当前 PATH 中程序是否存在。

正常反例：网页版无需该客户端；新终端可有不同 PATH。

验证方式：使用临时 PATH 场景验证，不运行登录命令。

关联主张：client-not-account

### dns-scope · DNS 配置覆盖

可见范围：direct_local

派生方式：统计指定配置文件中的解析器行数。

正常反例：系统分流、DoH、文件截断或无文件。

验证方式：验证解析器数目语义；不判定有效路径。

关联主张：dns-not-leak

### ip-attribution · 第三方归属

可见范围：third_party

派生方式：从显式开启的数据源读取国家/ASN。

正常反例：数据库滞后、共享出口、供应商相互矛盾。

验证方式：保留供应商、时间和冲突；不机械多数投票。

关联主张：metadata-not-policy

### temporal-relations · 事件与关联

可见范围：partially_observable

派生方式：仅连接用户已记录的事件、配置和来源。

正常反例：共同出口、先后发生不等于同一人或因果。

验证方式：限定观察窗、证据边、失访和未知身份。

关联主张：graph-boundary, account-graph-analogy

### platform-behavior · 平台行为特征

可见范围：platform_hidden

派生方式：仅整理官方披露的研究维度，不计算个人隐藏风险分。

正常反例：正常高频用途与总体规模不同；没有全平台视角。

验证方式：用公开资料审查范围，不能从本机复现平台标签。

关联主张：behavior-relations

### outcome-separation · 结果标签与处置

可见范围：user_declared

派生方式：将技术错误、验证、额度、支付、内容拒绝和账号限制分开。

正常反例：HTTP 错误与账号状态、API 与网页错误不同。

验证方式：以明确的阶段和枚举错误运行 triage，不导入原始认证响应。

关联主张：multiple-actions, bot-target-analogy, stage-specific-decision

### payment-context · 付款阶段

可见范围：user_declared

派生方式：只记录是否出现付款问题，不采集卡号或身份材料。

正常反例：发卡行拒付、验证和平台限制不是同一问题。

验证方式：引导在官方账单流程核对，禁止用本地环境分代替付款证据。

关联主张：payment-action-analogy

### action-value · 建议价值

可见范围：research_only

派生方式：关注理解度、正确分流、具体问题解决及无效变更。

正常反例：幸存者偏差、选择偏差、回访缺失。

验证方式：自愿用户实验与明确观察窗，不能用三个成功案例估计效果。

关联主张：uncertainty-helps-preparation

### address-family · 地址族与端点覆盖

可见范围：direct_local

派生方式：只接受 IPv6 专用端点返回的有效公网 IPv6 地址。

正常反例：HTTP 代理可以代替本机访问 IPv6 目标。

验证方式：覆盖无 IPv6、代理出口、错误地址族与超时输入。

关联主张：ipv6-scope

### public-connectivity · 连接错误所在层与 HTTP 结果

可见范围：direct_local

派生方式：固定公共首页 HEAD；分类解析、TLS、超时、传输错误或 HTTP 状态。

正常反例：代理隐藏错误层次；HEAD 拒绝与浏览器 GET 可以不同。

验证方式：模拟各类连接失败、403、重定向、正常响应；不读取正文。

关联主张：http-not-account


---
由 scripts/build_knowledge_docs.py 从 src/zhibi/data 生成；请修改源数据后重新生成。
