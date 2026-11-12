---
name: zhibi
description: Inspect the user's browser and network, prepare a remote Linux workspace or a local PVM Linux VM, bind project launch and file workflows, and verify the selected application and browser paths. Use for network checks, Linux application hosting, browser setup, and rechecks.
---

# 知彼

用用户能理解的话解释现状、需要的操作和验证结果。主线是：扫描与判断 → 确认运行位置与出口 → 准备 Linux 环境和应用 → 所选浏览器 → 总体验收。优先远程 Linux 服务器；没有远程运行服务器时可提供本地 PVM VM。仅检查也是完整任务，不要求用户先提供 VPS 或命令。

脚本入口为本 Skill 下的 `scripts/zhibi.py`。由 Agent 运行命令；安装依赖和界面操作根据宿主、系统及用户现状安排。已有授权继续有效，缺什么问什么。

## 1. 扫描与判断

先确定用户实际使用的浏览器、机器和已有线路。运行 `doctor` 检查工具条件；`session --preset basic --network` 在实际浏览器采集，必要时使用 `--file`。不要用 Agent 的浏览器或终端出口替代用户环境。

有用户指定的 VPS 时用 `check --host HOST --egress` 读取远端现状。`scan`、`suite` 保留深入检查，按问题选模块。外部查询只在允许范围内执行；原始配置和凭据留在本机。

以具体观测解释结果。数据中心标签、公共 DNS、中文语言或不同系统本身不构成失败；现有评分仅供背景，不能据此要求更换线路。说明已测、未测以及实际需要处理的问题。

## 2. 询问配置需求

用户仅要求检查时先交付结果。需要配置时分开确认运行环境与网络出口：有 Linux 服务器则优先远程路线；没有则按 [local-vm](references/local-vm.md) 检查本机资源并准备 PVM。VM 不自动提供地区出口。补齐用户启动命令和浏览器选择，不默认品牌；仅进程、普通浏览器或指纹浏览器均可。

按 [intake](references/intake.md) 收集信息，检查现有软件、服务和端口，给出具体修改计划。用户已授权的步骤直接继续；新增范围才补问。不购买资源、不代替用户登录账号。

## 3. VPS 服务与进程

本节用于远程路线。本地路线按 local-vm 参考创建共享项目与桌面，并使用相同的 project 启动/恢复入口；不要把整个远程部署流程重复套在本地 VM 上。

阅读 [runtime](references/runtime.md) 和 [remote](references/remote.md)。根据命令的真实运行方式选择交互终端、一次性执行或后台服务。准备依赖时根据实际 Linux 发行版、安装渠道和权限安排，安装后验证可执行文件和版本。不要改变用户命令的用途。

`connect` 可以同时提供本机 SOCKS5 与远端进程；`build` 用于非交互后台服务，默认只出计划。后台常驻不等于应用可用，必须检查日志和用户所需的应用操作。先保存原值和已有服务配置，再执行授权的变更。

需要专用进程环境时，按 runtime 参考使用 `process-workspace` 与 `process-entry`。需要受控代理联网时选择 proxy 模式，核验固定版本 graftcp 和解析器可达性；长期运行用 `runtime-service` 交付用户级网关服务及恢复入口。不要把默认完全隔离模式交付成可联网环境，也不要把 host 模式描述成代理专用网络。

需要按项目保存连接、再次启动或恢复应用会话时，阅读 [projects](references/projects.md)。`project bind/start/resume/status` 复用现有远程环境；`project upload/download` 处理选定的单个文件或图片。绑定不等于完成部署，应用会话恢复与后台常驻分别验证。

## 4. 浏览器

阅读 [browser](references/browser.md)。用户可以自行配置或委托 Agent。API、computer use 或手动均可；以实际浏览器版本和官方说明选择方式。本地 VM 路线可在同一 VM 桌面内运行浏览器；确认 Linux 浏览器已安装且实际出口正确。配置目标固定，点击步骤灵活。

## 5. 总体验收与交付

两条路线共同按 [audit](references/audit.md) 执行项目上下文测量、实际浏览器对比、协议检查和受控断网恢复。PVM audit 的 warn/skipped 与 0 退出码不能组合成“通过”。保存缺测项；单一 HTTPS 阻断演练不证明全协议无泄漏。

远程路线在隧道实际运行时，从指定浏览器重新采集，测出口和所选 DNS/WebRTC 项。用 `accept --host HOST --egress --browser FILE` 比对；只有用户确实选择了时区/语言目标才传对应参数。`deliver` 同样接收 `--browser`，将两端结果保存到本机。本地 VM 路线使用 project audit 与 vm audit，不把 VM 名称作为远程 VPS 地址传给 accept；报告和 VM 工作区分别保存。

按 [deliver](references/deliver.md) 保存启动入口与报告。检查进程的实际操作是否成功、浏览器是否可以正常访问用户需要的服务，由用户在浏览器完成账号登录。还要验证停止连接及恢复原配置。缺失观测不能算通过；未解决的问题写清影响，不能把部分结果说成全部可用。

`build --apply` 保存私人原值与部署回执；交付时传 `--build-receipt`，生成作用于该 VPS 的服务与时区恢复命令。安装依赖、语言生成和浏览器修改仍需记录各自恢复方式，不能承诺这些都由脚本自动恢复。check/browse/accept 使用 `--out` 保存阶段结果，build --apply 保存原值和回执；其余阶段过程由 Agent 在私人会话目录保存，恢复任务时先读文件并核对实际状态；不能假定 CLI 已有自动断点恢复。

## 必要边界

服务端进程与本地浏览器可以共用出口，但这不意味着它们是同一设备，也不保证账号结果。只管理用户授权的环境；不收集 Cookie 或账号凭据。遵循用户选用软件的实际使用要求，不用泛化的产品禁令或幽默免责声明替代事实。
