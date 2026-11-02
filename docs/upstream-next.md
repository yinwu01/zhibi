# 再看上游：值得吸收什么，下一步做什么

复核日期：2026-10-19。读取了三个仓库当前 HEAD 的 README、相关源码和许可证；提交与之前固定的版本一致。本轮没有运行上游的部署脚本或把其聚合 API 接入知彼。

## 源码告诉我们的差别

| 项目与固定版本 | 具体优点 | 知彼的取舍 |
| --- | --- | --- |
| [CCBaga `30a171f`](https://github.com/liseami/CCBaga/tree/30a171f5191fbb65dc24e4b1a0392d998f7c5719) | [逐项核验](https://github.com/liseami/CCBaga/blob/30a171f5191fbb65dc24e4b1a0392d998f7c5719/src/browser-verification.ts)把实际值、预期值、未知分开；[Network Skill](https://github.com/liseami/CCBaga/blob/30a171f5191fbb65dc24e4b1a0392d998f7c5719/skills/ccbaga-network/SKILL.md)将准备、检查、变更、真实复验与恢复串成流程 | 已适配出口请求和 IP 校验。继续学习“配置不等于生效”，让每条建议有复查条件。时区语言目标、指纹轮换、VPS 部署不直接变成知彼的默认注册要求 |
| [CheckCC `078e7ba`](https://github.com/yacuo/check-cc/tree/078e7baa1d2a08df28da3f25dacb90e687f4c79f) | [runner](https://github.com/yacuo/check-cc/blob/078e7baa1d2a08df28da3f25dacb90e687f4c79f/src/detection/runner.ts)一次采集上下文、按插件运行、按来源与信号 ID 去重；网页使用门槛低 | 已适配浏览器环境采集。后续扩展检测模块时保留单次采样和去重；任何并行化都要单独隔离模块失败，不能直接照搬会因一个 rejection 中断的 `Promise.all` |
| [IPQuality `87397e2`](https://github.com/xykt/IPQuality/tree/87397e2c3196ec796f5477c83343c2354df601ea) | [脚本](https://github.com/xykt/IPQuality/blob/87397e2c3196ec796f5477c83343c2354df601ea/ip.sh)提供分来源结果、阶段进度、JSON/文本输出和隐私选项 | 学习分项展示与可见进度。v0.2.0a2 独立实现 `scan --progress`；没有复制其 AGPL 代码，也没有引入它的第三方聚合查询或报告上传 |

CCBaga 和 CheckCC 的项目代码为 MIT，第三方组件仍需分别审查；已有适配的文件、哈希和通知见[复用记录](upstream-reuse.md)。IPQuality 标注 AGPL-3.0，不能因为代码可下载就直接并入 MIT 项目而不处理其许可义务。

## “为什么别的工具不用我填 Key，也能显示 IPQS？”

IPQuality 此版本的 `db_ipapi`、`db_abuseipdb`、`db_ipqs` 分别请求 `ipinfo.check.place/<IP>?db=...`，由聚合服务提供数据。客户端没有要求用户输入供应商 Key，不等于每个人都能直接匿名调用供应商的相同产品，也不证明聚合服务授权、套餐、字段和更新时间与直连相同。[相关源码](https://github.com/xykt/IPQuality/blob/87397e2c3196ec796f5477c83343c2354df601ea/ip.sh#L921)

同一脚本默认 `mode_privacy=0`；在非 Lite、非隐私模式下会向 `upload.check.place` POST JSON 和报告文本，以生成分享链接。`-p` 可以关闭报告链接流程。这里批判的是**数据流和默认值**，没有证据证明它出售数据。[上传条件](https://github.com/xykt/IPQuality/blob/87397e2c3196ec796f5477c83343c2354df601ea/ip.sh#L2600)

CheckCC 的公开 [`services.ts`](https://github.com/yacuo/check-cc/blob/078e7baa1d2a08df28da3f25dacb90e687f4c79f/src/detection/config/services.ts)中，`ipIntel` 默认 `enabled: false`，只配置 `/api/ip-intel` 地址。因此不能把这个前端配置称为已经拿到可直接复用的 IPQS/AbuseIPDB 后端；线上站点是否另有私有实现也不能由仓库推断。

知彼现在的选择：四个免 Key 来源直连，IPQS、AbuseIPDB、ipapi.is 自备 Key 按需启用。需要接聚合服务时，应先验证使用许可、实际字段、时间窗口与服务条款，明确新增接收方，再让用户选择；不悄悄增加一个中转站。

## 本轮已经落实

- 从 GitHub 下载发布 ZIP，在独立目录安装，用系统 Python、不配置 Key，实际跑到报告。
- 核对 Codex 的当前安装目录，实际调用宿主 `skills/list` 确认识别；分别写清 Codex 与 目标客户端 的调用方式。
- 快速开始以完整 ZIP 为主入口；指出源码 Skill 子目录不能单独搬走、private 404、旧版本处理与报告位置。
- 新增查询进度：显示正在查询哪一家和返回状态；标准输出继续保持 JSON，进度不含原始 IP、密钥或服务返回文本。
- 免费查询与 optional Key 分开；不把查询失败、没有报告字段、超时或未配置可选来源填成 0。

## 完整范围与交付顺序

更新后的硬目标是[能力覆盖清单](capability-coverage.md)：补齐已识别的检测、情报和环境管理能力，所有深入模块供用户按需启用。下述三项是体验改进的交付顺序，不是项目能力范围的上限。额外数据源、浏览器细项、环境维护、网络搭建和上游研究模型都有覆盖条目，不因“非默认”而被排除。

## 三项体验改进

### 1. 把实际浏览器检测收成一次完整流程

当前最大的使用断点是手动打开探针、保存 JSON、再把路径交给 Agent。下一步应让用户选择“当前终端 / 实际浏览器”，进入浏览器测量后直接回到同一份报告。

可评估仅限本机、单次随机令牌的回传会话，严格校验 Origin、请求大小、有效期和测量来源；禁用任意路径读写。不读取已有 Cookie 或浏览器配置。未明确导入目标浏览器证据时，报告继续写清“终端检测”。

验收：用同一浏览器的真实结果完成查询；页面失败、回传失败、旧观测都不能显示完成；不同环境的报告不串台。这项尚未实现。

### 2. 把“修完了吗”做成复查结果

已有 `scan-compare` 和 IPv6 配置确认核心。下一步把它们呈现成用户看得懂的“上次问题 → 本次结果 → 仍需处理”，保存用户指定环境的基线与预期路由，不保存账号密码。

验收：换出口、换情报源、只改配置但没有生效分别识别。来源分歧应明确是哪种判断冲突、先核对什么，不让用户自己解读大表，也不仅凭一个标签要求换 IP。

### 3. 做有证据的特征与案例库

保持“平台动机 → 特征 → 可观测证据 → 正常反例 → 行动 → 复查”。优先收集同一环境多次结果、来源标签变动、操作前后差异和用户自愿提供的实际结果。

每个案例保留时间窗口与混杂因素，脱敏后由作者明确提交；无默认上传。相同上游的数据不算独立佐证。能支撑某条研究假说，才考虑加入规则；更多样本不自动等于掌握 目标服务 的内部权重。

完整能力补齐与浏览器回传、复查体验分别推进。安装方面稳定完整 ZIP 和跨系统验收；插件/通用 Skill 安装器分发也保留在覆盖清单，必须证明会携带核心，不能只安装一份说明书。
