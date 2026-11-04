---
name: zhibi
description: Prepare a user's own Linux server and local fingerprint browser so both look like the same machine, then verify it and deliver an environment file. Use when the user wants a working network environment on their VPS, asks for server setup, browser alignment, or a recheck.
---

# 知彼 · 让 Agent 把环境搭好、验好、交到手上

One task ends when the user has a **working environment** and a **folder they can keep**: the service running on their server, their local browser matching it, one verification result, and instructions for stopping or undoing everything.

## 唯一一条说话规则（违反即失败）

**跟用户说的每一句话，必须让不懂计算机网络的人听懂。报告可以详尽，对话必须人话。**

| 不要这样说 | 这样说 |
|---|---|
| 出口 IP / egress | 你这台机器在网上的身份 |
| DNS 泄漏 | 你上网时"查地址"的请求跑到了别处，没走你设的通道 |
| WebRTC 泄漏 | 浏览器有个小便道，会把你的真实位置漏出去 |
| locale | 系统语言设置 |
| systemd unit | 让程序在后台一直跑、关机重启后自己起来的那份配置 |
| 时区不一致 | 机器认为的时间和它所在的地方对不上 |
| NTP 未同步 | 机器的时钟不准 |
| 机房 IP / ASN | 这个地址属于数据中心，不是家庭宽带 |
| 代理未生效 | 你设的通道没起作用 |
| `not_measured` | 这一项没测 |

术语第一次出现时用人话解释一次，之后可以继续用。**不确定用户能不能听懂，就再说一遍人话。**

## DAG（串行，一条主线）

```
N1 受理 → N2 本机体检 → N3 远端体检 → N4 出计划 ═ G1 用户确认 ═ → N5 远端部署 → N6 本机浏览器 → N7 两端验收 → N8 交付
                                                                        ↑                │
                                                                        └── G2 不一致 ────┘
```

| 节点 | 做什么 | 用户看到什么 |
|---|---|---|
| N1 受理 | 收齐两个输入：要跑的命令 + 服务器怎么连 | 一次提问，只问缺的 |
| N2 本机体检 | 系统、Python、指纹浏览器在不在、能不能点按操作 | 一句话结论 |
| N3 远端体检 | 服务器的时间、语言、时钟、解析器、资源 | 一句话结论 |
| N4 出计划 | 合成"要改什么"和"浏览器要填什么" | **三行摘要 + 一句"要不要开始"** |
| **G1** | 用户点头。**全程只需要这一次确认** | — |
| N5 远端部署 | 让命令在后台常驻 + 对齐时间与语言 | 两句话：做了什么、现在什么状态 |
| N6 本机浏览器 | 按服务器的读数反推浏览器该填什么并写入 | 两句话 |
| N7 两端验收 | 服务器 4 项 + 本机 4 项逐条对撞 | **一张表，每项一句话** |
| N8 交付 | 一个文件夹 + 一份 HTML 报告 | 文件夹路径 |

每个节点的中间结果落盘到 `~/.zhibi/sessions/<id>/`。中断后从断点续跑，不重跑已完成节点。

**G2 回到 N6 的条件**：本机任一项不通过，或任一项未测量。改动前先留快照。

## 用户只用做三件事

1. 说一句话（要跑什么、服务器怎么连）
2. 看三行摘要，点一次头
3. 收一个文件夹

其余全部由你完成。不要给用户逐步教程，不要让用户自己敲命令——除非宿主没有 computer use 能力，那时只交接无法自动完成的那一步。

## Computer Use

本 Skill **不安装** computer use、不授予权限。有就用，没有就降级，绝不假装完成。

指纹浏览器三档（详见 [browser](references/browser.md)）：

| 档 | 条件 | 做法 |
|---|---|---|
| 自动 | 浏览器本地 API 已开启 | 直接写配置，不点击 |
| 半自动 | API 未开启 | 用 computer use 点击：选中环境 → 编辑 → 填时间和语言 → 保存 → 关掉再开 → 读回验证 |
| 手动 | 宿主无 computer use | 只交接这一步，给一张"填什么"对照表，等用户回来继续 N7 |

## 失败时怎么说

一句话说清，然后停下。不要绕路，不要伪造成功。

- 连不上服务器：`我连不上这台服务器，先确认地址和登录方式。`
- 命令起不来：`命令在这台服务器上启动失败，日志我读过了，是这个错：…`
- 没验证：`配置已经改了，但还没有重新测过，所以现在还不能算成功。`
- 地区不对：`这不是改设置能解决的问题，属于地区限制，改配置解决不了。`
- 拿不到官方安装包：`我拿不到官方安装包，不会从第三方网站下载。`

## 边界

- **不推荐、不返佣、不销售**任何 VPS、代理、指纹浏览器或服务。
- **不代装、不代搜、不改写**用户给的启动命令；命令由用户提供，原样使用。
- **不管账号**：不注册、不验证、不代付、不做多账号切换。
- **不提供绕过地区限制的能力**。地区不符 → 属于合规问题，结论是停止。
- **不承诺**通过、匿名或账号安全。没测就是没测。

## 命令

```bash
python3 <this-skill>/scripts/zhibi.py check  --host <host>                  # N3
python3 <this-skill>/scripts/zhibi.py build  --host <host> --command "..."   # N5，默认只出计划
python3 <this-skill>/scripts/zhibi.py browse --host <host>                   # N6
python3 <this-skill>/scripts/zhibi.py accept --host <host>                   # N7
python3 <this-skill>/scripts/zhibi.py deliver --host <host>                  # N8
python3 <this-skill>/scripts/zhibi.py doctor                                 # N2
```

`build` 默认只打印计划，加 `--apply` 才真正执行。密钥与服务器地址只在本机使用，不上传、不外发。

## 按节点加载

- [intake](references/intake.md) — N1：问什么、不问什么
- [remote](references/remote.md) — N3 / N5 / N7
- [browser](references/browser.md) — N6 / N8，含三档操作
- [deliver](references/deliver.md) — N8：交付什么、怎么说
- [boundaries](references/boundaries.md) — 声明纪律与判读三分法

HTML 报告由 `deliver` 生成，保留完整技术细节；给用户的对话只用上面那套人话。
