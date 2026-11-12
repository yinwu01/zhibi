# 两条路线的验收

先记录用户实际需求和目标出口。配置存在、进程运行、上游命令退出 0 都不是完整验收。

## 应用上下文

远程路线的探针默认跑在服务器主环境；若应用经 bwrap 包裹，bind 时传 `--probe-prefix-file FILE`。文件为 600 的 JSON argv 数组，如 `["python3", "/private/profile/run.py", "--"]`；这些路径是远端路径。知彼在前缀后追加自己的 Python 探针，不运行来源仓库里的自动配置。没有前缀时报告明确标注未核验应用沙箱上下文。

PVM 路线的探针运行在绑定 VM 内。实际浏览器必须是用户选定的浏览器：远程路线通常为本地专用浏览器，VM 路线可为 VM 桌面浏览器。`session` 导出的 JSON 用于同一次出口对比；旧读数不算新验收。

```bash
zhibi project audit --project LOCAL_PROJECT --network --expected-ip EXPECTED_IP \
  --browser BROWSER_JSON --out NEW_REPORT.private.json
```

探针显式访问 api.ipify.org；报告私有保存，输出包含本次 IP。DNS 解析成功只说明可解析，不证明查询经过哪个出口；IPv6 逐接口内核配置是配置读数；PVM 还检查地址清空及 IPv6 路由不可用。对 DNS 路径需要自建观察端或 PVM 出口探针，UDP 用已知可达的测试端点验证，IPv6 需结合路由和实际请求。缺少观测保持 not_measured。

## 受控断网演练

准备两个本机 600 私人脚本，仅操作本次已授权测试环境的出口：断开脚本与恢复脚本。脚本可以通过 SSH 操作特定服务，也可以操作测试网关；不得停止用户整个代理、整台宿主网络或无关服务。

```bash
zhibi project audit --project LOCAL_PROJECT --network --expected-ip EXPECTED_IP \
  --disconnect-file DISCONNECT_SCRIPT --reconnect-file RECONNECT_SCRIPT \
  --browser BROWSER_JSON --out NEW_REPORT.private.json
```

先证明正常状态可访问，才执行断开；恢复动作在 finally 执行。探针必须仍可执行，但 HTTPS 请求失败，才是这项阻断证据。如果 SSH/VM 整体失联，不能证明应用没有直连。恢复后应重新访问成功且出口保持一致。

这个 HTTPS 演练不证明所有协议均无泄漏，所以报告不自动将 complete 设为 true。交付还需：应用实际操作、浏览器访问、DNS 路径、UDP 策略、IPv6 策略、直连例外、退出/重启/恢复逐项有证据。上游 PVM audit 附在同一报告里；它的协议成功也不替代应用和浏览器验收。

配置不支持的协议明确标“已阻断”需要实际验证或有效隔离证据；请求超时不自动等于已阻断。将结果与未完成项写入交付记录，不把手填结果冒充测量。
