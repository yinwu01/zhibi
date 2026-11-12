# 成熟项目复用：候选能力与接入记录

核对日期：2026-10-18；接入更新：2026-10-19。
已将 CCBaga 的 IP 验证/浏览器出口请求、CheckCC 的浏览器环境采集适配到 `src/zhibi/assets/network-probe.js`。
高级探针实际调用这些实现，迁移与边界测试位于 `tests/browser-network.cjs`。
v0.2.0a3 又将 CheckCC 同一文件的固定字体探测与浏览器/设备标记适配到 `src/zhibi/assets/browser-details.js`。
新增六组独立开关，全部无需 Key、只在本地处理；26 个候选字体采用三种回退字体的文字宽度对比。
UA/设备、运行容器、Emoji 系列保留自报或推断性质，中文字体和语言不直接计为风险。
验收包含 `tests/browser-details.cjs` 的纯逻辑测试及 `tests/test_browser_details.py` 的导入、隐私、报告测试。
原始许可见 [第三方通知](../../THIRD_PARTY_NOTICES.md)，固定源文件哈希见 [upstream-lock.json](upstream-lock.json)。
未创建 GitHub fork；未引入桌面 UI、浏览器引擎或 IPQuality 的 AGPL 代码。下表未明确接入的部分仍是候选。

本记录将对话中的 CC checker 按此前讨论的 **yacuo/check-cc（CheckCC）** 核对。

## 2026-10-19：信誉能力源码复核

重新获取上述两仓库 HEAD，提交与下表一致。结论限定于这些公开提交，不推测线上私有后端：

- CCBaga [`src-tauri/src/browser/network.rs`](https://github.com/liseami/CCBaga/blob/30a171f5191fbb65dc24e4b1a0392d998f7c5719/src-tauri/src/browser/network.rs)
  的 `SERVICES` 是 `ipwho.is` 和 `ipapi.co/json/`，提供出口与归属。未找到代理信誉、欺诈分或滥用举报适配器。
- CheckCC [`config/services.ts`](https://github.com/yacuo/check-cc/blob/078e7baa1d2a08df28da3f25dacb90e687f4c79f/src/detection/config/services.ts)
  中 `ipIntel.enabled=false`，端点是 `/api/ip-intel`；此提交没有对应可复用后端。
  [`scoring.ts`](https://github.com/yacuo/check-cc/blob/078e7baa1d2a08df28da3f25dacb90e687f4c79f/src/detection/scoring.ts)
  是地区/浏览器信号加权，不是商业 IP 欺诈情报。

因此，本轮保留已复用的 MIT 采集与出口验证代码，没有把不存在的信誉后端说成已经 fork。
新增的 ProxyCheck v3、IPQuery、StopForumSpam 适配器由知彼独立实现，直接调用各服务公开 API。
其能力与费用详见 [供应商教程](../archive/tutorials/providers.md)。未复制其他项目的共享 Key、未抓取检测网站的登录态。
服务接口的可调用性和数据授权独立于这两个项目的 MIT 许可。

## 原则与结构

底层检测优先复用成熟实现。知彼负责按需选择工具、统一观测格式、维护证据和解释，
再由检测模式与协助模式使用。复用范围可以是已有工具的明确接口、独立模块、少量核心代码，
或需要持续合并上游变更的维护分支。选择维护成本最低且能验证行为的方式。

```text
上游检测代码 / 已集成工具
          ↓ 适配：上下文、数据字段、请求范围、状态
      知彼检测核心与报告
          ↓
  检测模式 ← 协助模式按需调用
                 ↓
          用户流程、证据与交付
```

许可证允许复用实现，不自动证明上游的风险解释适用于 目标服务。
观测逻辑与判断逻辑分开审查；已有方法有效的部分保留，推断需要证据支持。

## 固定版本与许可

| 项目 | 核对提交 | 许可与结论 |
| --- | --- | --- |
| [CCBaga](https://github.com/liseami/CCBaga) | `30a171f5191fbb65dc24e4b1a0392d998f7c5719` | [根 LICENSE](https://github.com/liseami/CCBaga/blob/30a171f5191fbb65dc24e4b1a0392d998f7c5719/LICENSE) 与网络 Skill LICENSE 为 MIT；可优先提取已核对的原创模块，保留通知 |
| [CheckCC](https://github.com/yacuo/check-cc) | `078e7baa1d2a08df28da3f25dacb90e687f4c79f` | [LICENSE](https://github.com/yacuo/check-cc/blob/078e7baa1d2a08df28da3f25dacb90e687f4c79f/LICENSE) 为 MIT；保留版权与许可声明，连同实际依赖一起核对 |
| [IPQuality](https://github.com/xykt/IPQuality) | `87397e2c3196ec796f5477c83343c2354df601ea` | [LICENSE](https://github.com/xykt/IPQuality/blob/87397e2c3196ec796f5477c83343c2354df601ea/LICENSE) 为 AGPL-3.0；属于可研究的复用路线，但须先确定符合其义务的分发方式，不能并入后统一标为 MIT |

CCBaga 的 [NOTICE](https://github.com/liseami/CCBaga/blob/30a171f5191fbb65dc24e4b1a0392d998f7c5719/NOTICE.md)
区分了原创代码、Chromium 引擎及其依赖、图标与 vendored UI。它还明确指出部分 UI 缺少独立上游许可声明，
须确认后再分发。因此，根 MIT 不是整包所有素材与依赖的统一许可。
本轮优先考虑检测代码，不将桌面界面、浏览器二进制和第三方素材一并纳入。

## 已读源码与具体复用点

| 来源文件 | 读取到的能力 | 接入选择与需适配之处 |
| --- | --- | --- |
| CheckCC `src/detection/client-engine.ts` 的环境采集部分 | 采集语言、时区、locale、UA 等浏览器事实 | 已接入 collectBrowserEnvironment 的适配版；属性留在私人导出，地区评分另以显式可选研究对照接入，不影响主结论 |
| CheckCC `src/detection/runner.ts`、`plugin.ts` | 配置化检测插件、统一上下文、并行执行与信号去重 | 候选复用调度结构；补齐单模块失败隔离、测量状态和来源信息，不能把一个插件报错变成整次成功 |
| CCBaga `src/browser-network.ts` | 浏览器自身发起出口请求、响应验证、超时与备用服务 | 已适配 IP 校验和有界请求；显式双栈端点、omit credentials、no-referrer，无自动备用服务 |
| CCBaga `src/browser-network.test.ts` | 出口解析与请求行为测试 | 已迁移关键解析/请求用例，并补充独立 HTML、导出导入、隐私、错误与移动布局测试 |
| CCBaga `src/browser-verification.ts` | 实际值/目标值/未知值的逐项比对 | 可提取比对表达与未知处理；目标必须来自用户预期或明确依据，不照搬统一时区语言目标作为注册条件 |
| CCBaga `skills/ccbaga-network/scripts/network.py` | 配置验证、网络检查，同时包含 SSH、密钥与部署相关操作 | 先拆清只读检查和会改变系统的操作；检测模式只调用适配后的检查，部署类操作留给有明确流程的协助模式评估 |

源码入口：[CheckCC detection](https://github.com/yacuo/check-cc/tree/078e7baa1d2a08df28da3f25dacb90e687f4c79f/src/detection)、
[CCBaga browser-network](https://github.com/liseami/CCBaga/blob/30a171f5191fbb65dc24e4b1a0392d998f7c5719/src/browser-network.ts)、
[CCBaga network Skill](https://github.com/liseami/CCBaga/tree/30a171f5191fbb65dc24e4b1a0392d998f7c5719/skills/ccbaga-network)。

CheckCC 的 `scoring.ts` 按地区画像对国家、时区、语言、locale、浏览器等特征加权并映射访问状态。
这是该实现的评分模型，不能因开源或可运行就当作 目标服务 已确认的内部规则。
知彼可以复用采集代码，同时对这部分推断独立验证。

## 第一批接入顺序

1. 选择与现有 JS 探针相接近的纯采集和出口校验模块，记录上游文件、提交与依赖。
2. 保留原始许可与署名，保存适配差异；发生代码引入时再创建实际第三方清单，不能只列名字充当已集成。
3. 让输出进入知彼严格输入契约：主体、端点、时间、事实、测量状态、来源。模型不处理未经筛选的上游响应。
4. 运行上游相关用例和知彼边界验证，再加入 `zhibi capabilities` 与 Skill 的可调用能力说明。
5. 记录上游更新方式与本地补丁；需要持续维护大量差异时再建立明确的 fork/维护分支。

复制代码、直接调用已安装工具和维护 fork 都是可选实现方式，不保证任意一项都更轻量。
采用第三方服务或数据库时，源码许可证与服务使用权分开核对。

[Skill 两种模式](../archive/tutorials/skill.md) · [IP 情报方案](../reference/ip-intelligence.md) · [实现进度](../product/roadmap.md)

## v0.3 实际交付与未覆盖部分

CheckCC 六特征地区模型和十个客户端加权信号已移植到 `checkcc_model.py`，保留固定提交、MIT 与输入缺失状态。CCBaga 新提交 `bdfb90c` 的系统/CLI/身份/网络交付逻辑已逐项审查：本轮的维护、工作目录备份、AdsPower API、Mihomo/SSH 交付为独立实现，并未复制其 root Debian 部署脚本。IPQuality 仅用于能力对照，未并入 AGPL 源码。

当前接入方式、可选依赖和仍未完成的子项见[覆盖表](../architecture/capability-coverage.md)，真实运行与夹具测试分别记录在[验收记录](full-coverage-validation.md)。所有对外服务有自己的服务条款；源码 MIT 不等于取得商业数据使用权。

## 双路线运行环境参考（2026-11-12）

| 项目 | 固定版本 | 接入边界 |
| --- | --- | --- |
| Blackhole | `49e27ed949384b69b07c1bb52c43ce5cd3e145ba`，MIT | 借鉴项目绑定、持久化与启动体验，未复制代码或镜像 |
| PVM | v1.1.6 / `edebd3cfbf266f7c5a8bbf86907b6f5d19140b6c` | 独立 CLI 适配层；调用已安装的程序，未复制源码、镜像或二进制。所读源码未包含 LICENSE，不将其标为 MIT |

PVM 的 `audit` 对 warn/skipped 也可能返回 0；知彼逐项解析并保留缺测状态。创建时先 `--no-start`，启动空白 VM 建立网关后配置实例级出口，再挂载项目并运行用户应用，不修改集群默认出口。版本接口需要更新时先验证命令、输出和实际 VM 行为，再调整固定版本。完整状态见[双路线实施记录](../implementation/two-route-plan.md)。
