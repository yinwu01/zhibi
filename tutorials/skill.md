# 让 Agent 完成一次环境检查与配置协助

这篇教程只走一条路径：**安装 → 指定实际环境 → Agent 检查 → 协助配置 → 复查与交付。**
需要 Python 3.9+ 和本机 Agent。推荐能操作实际浏览器、桌面的 computer use 宿主；Skill 本身不提供这项权限或能力。

## 1. 下载与安装

从 [v0.3.0a3 发布页](https://github.com/JoeyWu-tech/zhibi/releases/tag/v0.3.0a3)下载 `zhibi-skill.zip`。这是包含核心的完整包，无需 pip 或另外安装依赖。
当前仓库为 private，需登录获邀账号；404 通常需要先核对仓库访问权限。

解压整个文件夹到下列位置，保留 `SKILL.md`、`scripts`、`assets`、`references`。已有旧版先移出 skills 目录备份。

| 宿主 | 安装目录 | 调用 |
| --- | --- | --- |
| Codex | `~/.agents/skills/zhibi/` | `$zhibi` |

Windows 的 `~` 指用户目录，Python 命令可用 `py -3`。不要多嵌套一层 `zhibi/zhibi/`。
想核验下载，可用 `shasum -a 256 zhibi-skill.zip` 或 PowerShell `Get-FileHash`，与同页的 `SHA256SUMS` 对照。

<details><summary>从源码安装</summary>

```bash
git clone https://github.com/JoeyWu-tech/zhibi.git
cd zhibi
python3 scripts/install_skill.py --host codex
```

其他宿用 `--dest` 指向自己的 skills 目录。安装器会打包核心；仅复制源码中的 Skill 子目录不能独立运行。

</details>

## 2. 说清楚实际环境，剩下交给 Agent

新开会话调用 Skill，例如：

> 用知彼检查我准备使用 目标服务 的 AdsPower「目标服务 2」环境。允许默认免 Key 查询。你来操作浏览器完成检查，核对相关设置；发现问题后说明具体修改，按我授权的范围处理并复查，最后打开报告。

不需要先申请 IPQS、AbuseIPDB、ipapi.is 的 Key。默认使用 ipify 测出口，并查询 IPWhois、ProxyCheck、IPQuery、StopForumSpam。这些服务会看到连接或被查询的 IP，不接收 目标服务 Cookie、登录资料或私人快照。

默认检查实际浏览器出口、可用 IP 标签与历史记录、IPv6 出站策略。有具体原因再启用 WebRTC 或其他深入检查。

## 3. Agent 应该实际操作什么

| 步骤 | 有 computer use 时 Agent 做什么 | 你会看到什么 |
| --- | --- | --- |
| 找环境 | 定位你指定的现有浏览器/配置，不用另一个浏览器代替 | 确认检测对象 |
| 运行检查 | 打开本机探针，开始检查，保存给本机 Skill | 测量和来源查询进度 |
| 读取结果 | 读取不含原始 IP 的摘要，打开本地报告 | 结论、下一步、简短结果表 |
| 核对设置 | 根据发现打开实际配置界面，记录原值与作用范围 | 一个具体处理方案，或确认无需改动 |
| 配置与复查 | 执行已有授权范围内的修改，检查生效状态，再测同一环境 | 修改结果及复查证据 |

有 computer use 时，不应把这些步骤整段转交给用户。没有界面控制能力时，Agent 只交代当前必须由你完成的操作，接收到结果后继续。

Agent 使用的主命令如下；你不必自己逐条运行：

```bash
python3 <Skill目录>/scripts/zhibi.py doctor
python3 <Skill目录>/scripts/zhibi.py session --preset basic --network
```

若 AdsPower 无法访问 `127.0.0.1`，Agent 使用 `session --file --preset basic --network`，在同一个浏览器打开本地 HTML。点击“保存并交给本机 Skill”后，只接收本次随机命名的下载文件，自动生成报告。下载目录不是默认位置时，按命令返回的指定路径保存，不要上传文件内容到聊天。

## 4. 从检测到配置：如何算做完

例如 IPv6 显示“待确认”时，Agent 应继续查专用环境的设置，而不是让你自行研究所有 IPv6 文档：

1. 找出控制该环境出口的代理、虚拟机或防火墙，读取真实生效设置。
2. 已禁用就保留；需要修改则先明确影响范围，在授权内操作。没有独立控制项时，说明具体缺哪个控制能力，不虚构 AdsPower 开关，也不默认修改整台日常电脑。
3. 保存必要的本地配置依据，复测同一环境，再更新结论。请求失败本身不算禁用成功。

[IPv6 依据与确认方式](ipv6.md)。其他问题同样遵循“发现 → 操作 → 生效依据 → 复查”。IP 标签冲突不自动要求换 IP；无需调整时，保持当前配置就是合理结果。

给 Agent 一篇经验帖时，可以说：

> 按这份教程检查我已经完成了哪些步骤，把剩余可操作的配置做成具体计划，在已授权范围内操作并复查。标出哪些只是作者经验。

Agent 应提取适用环境、当前步骤、前置条件和完成依据，不能把帖子里的猜测当平台政策。作者三账号的详细教程仍待补充；现有协助模式支持实际提供的流程，不编造注册成功方案。

## 5. 看交付，接手必要步骤

`report.html` 保存在本机。首页给出本次结论、Agent 下一步要做什么，以及“检查项｜结果｜建议”。技术依据与所选扩展结果折叠展示。

Agent 还应告诉你实际操作了什么、有没有修改设置、哪些结论已经复验。若需要账号验证、付费服务、缺失权限或超出范围的配置修改，它应指出精确接手点。

| 文件 | 用途 |
| --- | --- |
| `report.html` | 本地人类报告 |
| `agent-summary.json` | Agent 使用的固定摘要 |
| `base/` | 本次基础检查、私人快照和复查依据 |
| `modules.private.json` | 本次已选择的扩展结果 |

不要把私人快照上传到聊天或 GitHub。两次 session 之间可以由 Agent 使用 `suite-compare <旧report目录> <新report目录> --same-context` 比较；不同环境或不同来源不混成“风险改善”。

## 需要时才展开的选项

[额外 IP 来源与 Key](providers.md) · [可选诊断](optional-modules.md) · [维护与恢复](environment-maintenance.md) · [作者实践](author/README.md)

全量组合仍可显式选择，默认流程不执行。额外 Key 缺失不会阻止默认报告交付。

## 常见阻碍

| 现象 | Agent 应如何继续 |
| --- | --- |
| 找不到 Python 或 Skill | 检查安装目录和 `doctor`，给出具体缺失项 |
| 不能操作 AdsPower | 明确宿主控制能力缺失；只交接打开探针/保存这一步 |
| 本机地址打不开 | 切换 `session --file`，保留当前代理设置 |
| 免费来源失败或限流 | 保留成功结果，针对失败项复查，不要求注册三家服务 |
| 没有独立环境配置开关 | 明确控制边界和后续选择，不动全局设置凑通过 |
| 点击保存但没生成报告 | 核对本次下载的精确路径；确认接收并打开最终报告才算交付 |

[本轮验收](../docs/product-flow-validation.md) · [隐私](../docs/privacy.md) · [复用与许可](../docs/upstream-reuse.md)
