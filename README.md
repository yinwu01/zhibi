# 知彼 (zhibi) · 让 Agent 帮你检查和对齐网络环境

> **从风控视角做网络环境切换前的本地自检与判读。不推荐、不返佣、不卖任何服务。**
>
> [快速开始](#3-分钟快速开始) · [它能帮你做什么](#知彼能帮你做什么) · [实际效果示例](#实际会得到什么) · [使用前提与边界](#使用前提与能力边界) · [English](README.en.md)

---

## 为什么需要「知彼」？

换一个网络环境去使用海外或跨区服务时，很多人常遇到这类抓狂的问题：

* 页面能打开，但登录直接被拒；
* 同一个账号在家里用得好好的，放到服务器上跑程序就出问题；
* 代理明明开着，某些流量却偷偷从本地直连了出去；
* 去网上的「环境检测站」测分，不仅不知道对方拿你的数据做了什么，还容易被各种玄学传言误导（比如“输入中文会封号”、“改个时区就会被标记”）。

作者曾在某面向国际应用的风控团队学习过，也长期稳定使用过多个付费账号。核心认知只有一句话：

> **先把环境查清楚，再让运行环境、浏览器和网络路径保持自洽。**

时区、语言、DNS 出口、IP 类型和浏览器配置需要放在一起核对。例如，原本想使用 VPS 出口，浏览器却仍然从本地直连；或者应用与浏览器分别走了两条线路。知彼把这些配置差异转成可检查、可修改、可复测的项目，不把单一语言或时区直接解释成账号风险。

**知彼（zhibi）就是一个自带本地工具的 Agent Skill。**
它让 AI Agent 帮你把环境查清楚、把配置对齐好，并在更小、更专用的环境里减少无关信息的暴露：
1. **本地处理报告**：配置与报告保存在自己的设备上，不收集 Cookie 和登录凭据。联网测量仍会访问指定的 IP 查询服务；对方能看到请求 IP（[数据流说明](docs/reference/privacy.md)）。
2. **给原因、给解法**：把发现的问题明确分为**技术问题**（能通过改配置修好）、**渠道问题**（IP/线路本身有问题，得换路）、**合规问题**（没有技术解）。
3. **一次“区域用户 Cosplay”**：如果你需要在 VPS 上跑应用（如 CLI 工具），同时在本地用浏览器操作账号，知彼能帮你把这两端接进同一条线路，并把时区、语言、网络出口对齐。

---

## 知彼能帮你做什么？

你可以根据自己的需求，只用它的**阶段一（纯检测）**，或者用完**阶段一 + 阶段二（全套搭建）**：

### 阶段一：本地浏览器与网络环境体检（无需 VPS）
直接让 Agent 检查你正在用的浏览器（支持 AdsPower 等指纹浏览器或普通 Chromium 浏览器）：

* 核对浏览器的**实际网络出口**（而不是只看系统代理开没开）；
* 免 Key 查询 **IP 标签与历史记录**；
* **默认关闭 IPv6**：PVM guest 持久禁用，私人代理仅使用 IPv4；检查 WebRTC、DNS、时区与语言是否存在泄漏或前后矛盾；
* **只报事实，不制造焦虑**：“请求超时”或“未配置付费 API Key”会如实标注，绝不会被包装成吓人的“高风险扣分”。

### 阶段二：两条 Linux 运行路线

**首推：自己的远程 Linux 服务器。**
当你需要“程序在服务器上跑，账号在本地浏览器用，且两边看起来是同一个区域环境”时，Agent 会按以下流程帮你推进：
`扫描当前环境 → 确认配置需求 → 准备 VPS 并隔离运行程序 → 配置本地浏览器 → 实际复测与交付`

* **服务器端（应用运行环境）**：在你自己的 Linux VPS 上，用沙箱（`bwrap`）和代理工具（`graftcp`）把应用包裹起来，按目标区域配置时区与语言；proxy 模式阻断直接 UDP，并支持配置 `systemd` 后台托管与故障自启。
* **本地端（浏览器操作环境）**：通过 SSH 隧道将你本地的指纹浏览器或独立 Chromium 接入同一台 VPS 线路，知彼生成的 Chromium 工作区使用独立历史目录，限制定位、摄像头、麦克风、通知权限，关闭扩展与同步；其他浏览器按实际 API 或界面配置，减少无关信息暴露。
* **可脱离 Agent 独立使用**：配置完成后，可导出独立的启动文件夹（含一键脚本），后续日常使用只需本地 Python + SSH，无需每次都打开 Agent。

**备选：本机创建完整 Linux VM。** 没有远程运行服务器时，由 Agent 使用 PVM 准备虚拟机，将指定项目共享到 `/workspace`，在同一 VM 内运行应用与桌面浏览器。网络可以接入已注册的自有 VPS 出口；明确选择 `direct` 时使用宿主出口。创建 VM 不会自动获得特定地区的专用线路。

两条路线都使用项目绑定：记住启动位置、应用命令及可选的恢复命令。远程路线提供单文件上传下载；本地 VM 直接共享项目文件。登录和应用历史保存在运行环境中，会话恢复按应用自身能力配置。

---

## 3 分钟快速开始

### 1. 基础环境要求

* **本机**：Python 3.9+、SSH 客户端、一个 Agent 宿主（如 Codex；推荐具备操作桌面/浏览器的 computer use 能力，若无，仅少量浏览器界面点击需你手动配合）。
* **仅做本地检测**：满足上面本机要求即可，不需要 pip 安装依赖，也不需要先注册任何 IP 情报服务。
* **远程路线**：准备有 SSH 权限的 Linux 服务器。**本地 VM 路线**：准备受支持的本机、PVM v1.1.6 和足够的内存/磁盘；首次镜像构建需要额外时间。两条路线都需单独确认网络出口（见[使用前提](#使用前提与能力边界)）。

### 2. 安装 Skill
目前请直接使用源码安装。打开终端（或直接让你的 Agent 执行）：

```bash
git clone https://github.com/yinwu01/zhibi.git
cd zhibi
python3 scripts/install_skill.py --host codex
```

### 3. 让 Agent 开始

> 使用知彼检查我实际使用的浏览器和网络。如果需要配置，优先使用我的 Linux 服务器；没有服务器就评估本地 VM。根据我的情况安装与配置，最后保存启动方法和验收结果。

只做检测也可以。命令由 Agent 执行；浏览器品牌、应用安装渠道和交互方式按你的环境安排。

## 实际会得到什么

- 一套专用 Linux 应用环境，以及与它配合的浏览器环境。
- 按项目保存的启动入口；支持的应用可另配会话恢复命令。
- 具体的出口读数、协议检查、浏览器对比与缺测项。
- 单文件传输或共享项目目录，以及停止、恢复和解除绑定的说明。

目标是在更小、更专用的环境里统一时区、语言和网络路径，减少无关 HOME、配置、扩展与权限的暴露。这就是我们所说的“区域用户 Cosplay”：先明确要呈现的环境，再逐项配置和验证。

### 后续日常使用

以下命令由 Agent 在首次配置时补齐参数。Skill 安装用户将 `zhibi` 换成 `python3 ~/.agents/skills/zhibi/scripts/zhibi.py`；独立 CLI 可用 `python3 -m pip install .` 安装。

```bash
# 在已经绑定的本地项目目录中
zhibi project status
zhibi project start --apply
# 应用支持、且已保存恢复命令时
zhibi project resume --apply
```

远程文件传输不覆盖已有文件：

```bash
zhibi project upload --local ./image.png --remote-file uploads/image.png --apply
zhibi project download --remote-file reports/result.txt --local ./result.txt --apply
```

本地 VM 的对应入口：

```bash
zhibi vm status --workspace VM_WORKSPACE --live
zhibi vm desktop --workspace VM_WORKSPACE --apply
zhibi vm stop --workspace VM_WORKSPACE --apply
```

[项目绑定与文件](skills/zhibi/references/projects.md) · [本地 VM 配置](skills/zhibi/references/local-vm.md) · [协议与断网验收](skills/zhibi/references/audit.md)

## 使用前提与能力边界

**远程路线需要自己的 Linux 服务器。** 家宽或机房网络均可，重点是自己有管理权限、出口来源清楚。大量用户共用的机场节点不能替代服务器或专用出口。

**本地 VM 路线把运行环境放在本机。** 当前知彼适配器接受 macOS arm64 和 Linux amd64，调用单独安装的 PVM v1.1.6。它支持自有 VPS 出口，也允许明确选择宿主直连；两者交付结果不同。WARP 是上游可选出口，不能直接等同于固定地区的专用 VPS。

**验收按实际证据交付。** 已实现能力、开发测试和用户环境实测分开记录。DNS 解析成功不等于 DNS 路径正确，探针失联不等于流量已被阻断。应用登录、浏览器操作和完整协议策略需要在选定环境验证；查看[本轮实施与验收状态](docs/implementation/two-route-plan.md)。

应用会话恢复不等于后台任务持续运行。远程持续任务可使用 `runtime-service`；本机关闭后，本地 VM 里的任务也会停止。

## 数据与复用

报告与私人配置留在本机。联网测量和可选 IP 情报查询会访问对应服务；读取[数据流说明](docs/reference/privacy.md)。知彼不打包 PVM、QEMU 或应用程序；外部工具由用户单独安装。

[MIT](LICENSE) · [第三方声明](THIRD_PARTY_NOTICES.md) · [贡献](CONTRIBUTING.md) · [English](README.en.md)

## 致谢与参考项目

感谢以下项目的作者与贡献者：

- [xiaoxiaodong-vps](https://github.com/nevertoday/xiaoxiaodong-vps)：VPS 部署、Agent Skill 组织与运维流程参考。
- [CCBaga](https://github.com/liseami/CCBaga)：网络检查与环境配置流程，部分浏览器出口检测代码适配。
- [CheckCC](https://github.com/yacuo/check-cc)：部分浏览器环境采集、字体探测与研究模型适配。
- [IPQuality](https://github.com/xykt/IPQuality)：IP 质量检查的研究与对照。
- [Blackhole](https://github.com/tommy0103/blackhole)：项目绑定、持久化会话和启动体验参考。
- [PVM](https://github.com/huangzheng2016/pvm)：本地 Linux VM、共享目录、桌面与出口的可选外部后端。
- [bubblewrap](https://github.com/containers/bubblewrap)：Linux 进程隔离。
- [graftcp](https://github.com/hmgle/graftcp)：应用和子进程的代理网络接入。

具体版本、接入方式与许可见[上游复用说明](docs/research/upstream-reuse.md)和[第三方声明](THIRD_PARTY_NOTICES.md)。
