# 目标验收矩阵

更新：2026-11-05。此表区分实现、隔离验证和用户环境验收，不以单元测试替代实机效果。

最新进程实现及实测见 [进程包裹](process-wrapper.md)：独立工作区、命令入口、应用文件替换后继续包裹、graftcp 代理网络、私人网关、真实 HTTPS 与停网关后失败、用户级持续服务与恢复均有 Linux 验证。完整应用会话仍待验收。

| 用户目标 | 实现及证据 | 当前结论 |
|---|---|---|
| 先检查当前网络与 VPS | session/scan/check；原探针测试、离线扫描和包外验收 | 实现存在，指定实际环境未验收 |
| 检查后按需配置 | 主 Skill 五阶段；普通/指纹浏览器可选，命令由用户提供 | 已更新，独立宿主行为验收待做 |
| 在 VPS 启动用户命令 | connect 的 shell/PTY；process-entry 的独立命令；runtime-service 的后台应用 | SSH/PTY/退出码通过，实际 Claude Code 2.1.318 隔离启动通过；登录后业务操作待验 |
| 本地浏览器直接接入 | 回环 SOCKS5、独立连接包、connection-check | 独立 Chrome 测试配置已通过 SOCKS 加载专用域名页面；用户所选指纹浏览器待验 |
| 后续可以自己使用 | 导出 start.py、私人参数、说明；不依赖 Agent 会话 | 包外启动与真实协议测试通过 |
| 停止连接 | lifecycle 处理 Ctrl-C/SIGTERM/SIGHUP，仅清理自身 SSH | 集成测试确认终止启动器后端口关闭 |
| 后台服务稳定与恢复 | build 原 unit/状态备份；runtime-service 新用户服务、就绪握手、失败恢复与回执 | 用户级服务已通过真实 systemd 安装、网关故障重启、冲突与恢复；旧系统级替换路径仍为模拟 systemctl 验证 |
| 整体复测与报告 | 实际浏览器结构归一、时效检查、accept/deliver、部署回执 | 测试覆盖结果保留与 SSH 参数；完整用户流程待验 |
| 安装灵活 | Skill 按系统选择依赖与浏览器方式 | 策略已写明，各操作系统实机安装未穷尽 |

## 仍需完成的实现核对

- check/browse/accept --out 以及 build --apply 保存阶段结果；恢复时由 Agent 核对现场与记录，不自动重跑已执行的变更。
- 原远端 locale 准备只生成语言资源；新 process-workspace 在应用启动时设置 LANG/LC_ALL/TZ。系统登录会话没有因此改变。
- 时区和服务恢复有自动命令；依赖安装、浏览器设置等其他修改依赖明确的原值记录与单独恢复。
- 导出的 SOCKS5 为 TCP；HTTP-only 浏览器需要协议适配，UDP/WebRTC 需要按目标客户端能力验证。通用协议支持不等于所有品牌实测。
- 0.4.0a1 的 wheel 新环境安装、Skill 包外运行与文档契约检查已通过；真实用户流程和宿主发现验收仍待完成。

## 完整用户验收所需输入

Linux 临时工作区实测已完成，未修改现有应用、代理或账号。最终仍需确认目标部署身份、实际应用及浏览器配置；临时测试不代表现有账号与完整业务操作已验收。

## 验证命令

- `env -u HTTP_PROXY -u HTTPS_PROXY bash scripts/test.sh`（POSIX，排除本机代理对回环测试的干扰）
- `PYTHONPATH=src uv run --no-project --with paramiko python scripts/verify_ssh_integration.py`
- 上一条设置 `CHROME_PATH` 可额外运行隔离 Chrome SOCKS 页面验证。只创建临时浏览器目录，不读取用户配置。
- `python scripts/verify_skill.py`，`python scripts/check_repository.py`
- 构建新 wheel 后运行 `python scripts/verify_distribution.py`

CI 已加入 SSH/Chrome 与 Linux namespace 集成步骤。最近推送的 GitHub 任务因账号账单锁定未能启动，远端 CI 尚未通过。

## 当前交接点

本地版本为 0.4.0a1。最新回归 198 项，196 通过、2 跳过；真实 SSH、PTY、端口冲突、停止清理、隔离 Chrome 代理访问，以及 Linux 进程、网关和用户级持续服务验证已分别完成。发布包已重建，新环境 wheel 安装与归档内容检查通过；登录后完整应用及用户浏览器流程仍待验收。

## 专用浏览器信息暴露控制

browser-workspace 创建独立 Chromium 配置与启动入口，不导入日常配置；默认限制位置、麦克风、摄像头、通知，禁用扩展与同步，配置 SOCKS5 与 WebRTC 非代理 UDP 限制。真实 Chrome 基线的四项权限为 prompt，新环境均为 denied，已通过页面回传验证（scripts/verify_browser_workspace.py）。这项验收不包含其他指纹浏览器厂商实现。Chromium 偏好项参考官方 [权限注册实现](https://github.com/chromium/chromium/blob/main/components/content_settings/core/browser/content_settings_registry.cc)。
