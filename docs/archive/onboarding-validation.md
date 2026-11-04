# 从 GitHub 下载到真实报告的验收

日期：2026-10-19。测试环境：macOS、系统 Python 3.9、Codex CLI 0.159.2。
本页记录实际执行的范围；不把单元测试或合成报告当成真实 IP 查询。

## 已发布的 v0.2.0a1 下载验收

| 步骤 | 实际执行与结果 |
| --- | --- |
| GitHub 下载 | 从私有 Release 下载 `zhibi-skill.zip` 与 `SHA256SUMS`，未使用工作区构建物代替 |
| 完整性 | 下载 ZIP 的 SHA256 为 `2e7c98a06e8bf7ae090f8751e9824337551b095f709beca6fde18aedffb6334a`，与发布清单一致 |
| 安装 | 解压到仓库外临时目录的 `.agents/skills/zhibi`，保留内置 pyz；没有 pip 安装 |
| 宿主发现 | Codex `skills/list` 实际返回该路径的 `zhibi`，scope=repo、enabled=true；没有新建模型任务 |
| 零 Key | 独立空用户目录、清除 `ZHIBI_*` 配置变量；`providers` 显示全部未配置。测试隔离没有修改真实 HOME/CODEX_HOME |
| 查询范围 | dry-run 只选择 IPWhois、ProxyCheck、IPQuery、StopForumSpam；未启用任何可选 Key 来源 |
| 真实联网 | 当前执行环境 IPv4，经 ipify 测量后查询四家，全部 `ok`；该次扫描约 6.4 秒，非性能承诺 |
| 报告生成 | 产生 HTML、Markdown、JSON、私有快照和 Agent 摘要；首屏 2 项通过、2 项需注意/待确认，没有未完成项 |
| 真实结论 | 来源对托管网络、归属与风险提示存在分歧；垃圾信息库未发现记录；IPv6 禁用配置尚未确认。没有把整份报告强行标为通过 |
| 源码安装 | 另外通过 GitHub 克隆完整仓库，用安装器安装到独立 `.agents/skills` 目录，内置核心完整 |

以上检测对象是 Agent 所在环境，**不是 AdsPower**。真实 IP、私人快照和完整报告不进入仓库。
这条流程证明了“有 Python 和仓库访问权限，不配置 IP 服务 Key，也能安装并得到真实报告”。

## v0.2.0a2 改进及本地验证

- Codex 安装器改用当前官方 `.agents/skills` 位置，目标客户端 调用说明修正。
- README 明确完整 ZIP、private 访问要求、目录、首次请求和报告路径。
- 新增 `--progress`，显示固定服务名与查询状态；JSON 输出保持可解析。
- 109 项 Python 行为测试通过，包含超时后继续保留成功来源、进度不泄露私人数据和旧安装不被覆盖。

## v0.2.0a2 发布后重新下载验收

再次从 GitHub Release 下载完整 Skill，解压到另一个仓库外目录，未使用本地 dist 替代。复验结果：

| 检查 | 结果 |
| --- | --- |
| 下载包 SHA256 | `19351490827331076daa17cc98a9f2fcc0afee16f55cf452ba15a0844e49a5f8`，与发布清单及 GitHub asset digest 一致 |
| 运行版本 | `capabilities` 确认为 0.2.0a2；系统 Python 3.9，零 pip 依赖 |
| Key 状态 | 隔离配置为空，全部未配置；没有启用 Key 来源 |
| 宿主识别 | Codex CLI 0.159.2：repo scope、enabled=true |
| 真实免费查询 | 四家均 `ok`，扫描约 6.25 秒；本次未重试 |
| 进度 | 逐项显示查询与结果；未出现真实 IP，stdout 仍为有效 JSON |
| 报告 | 五个本地文件生成；2 项通过、2 项需注意/待确认，无未完成项 |
| 本地回归 | Python 3.12：109 项通过；Python 3.9：108 项通过，1 项可选 Schema 检查跳过；独立 Skill、全新 wheel 安装和仓库链接检查通过 |

本次仍为 Agent 环境实测，没有重新测量 AdsPower 或更改网络。检测结果与上面的 a1 实测一致：IP 来源存在分歧、垃圾信息库未发现记录、IPv6 配置待确认。
新版代码提交为 `2bb3edad91db0a2175cc8e8f879e8c67066eb995`；验收文字在发布后单独补记，不改动已下载验证的发布包。

## 限制

- 已验证 Codex 的真实发现接口和安装包脚本链路；本轮没有另开付费模型对话做自然语言调用，也没有验证 目标客户端 的发现 UI。
- Windows/Linux 未做实机新用户验收。GitHub Actions 之前因账号账单或支出限额未启动；本地通过不能替代云端通过。
- 免费查询仍受服务网络、限流和套餐变化影响；Key 服务为可选，本轮未验证其真实 Key。
- 没有测试账号注册结果、付款、长期可用性或封禁率；没有通过修改系统配置使结果变绿。
