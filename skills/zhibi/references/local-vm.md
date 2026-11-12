# 本地 Linux VM 路线（PVM）

没有远程 Linux 运行服务器，或用户希望项目文件保留在本机时读取。首选远程路线保持不变。PVM 提供本机 Linux VM；地区网络出口是另一个配置项，不因创建 VM 自动获得。

## 安装与预检

适配 PVM v1.1.6，首版入口支持 macOS arm64 / Linux amd64。Windows 是上游能力，尚未纳入知彼适配器。使用 [上游安装器](https://github.com/huangzheng2016/pvm/blob/v1.1.6/scripts/install.sh)；先读取脚本，再按用户环境执行。上游安装器需要 gh、Python 3，会核对 SHA256 与 GitHub attestation，再安装 PVM 和 QEMU。不跳过校验，不把 PVM 二进制打进知彼发布物。读取 `pvm version` 确认版本。

`PVM_HOME` 应使用短的私人绝对目录，默认 `~/.pvm`。macOS Unix socket 路径有限制，长临时目录会导致大镜像下载后才失败。不要移动已安装的 PVM_HOME；其中 runtime 符号链接可能含绝对路径。VM 工作区和 PVM_HOME 均放在共享项目之外。

检查宿主内存、CPU 和剩余磁盘；默认 VM 2 核/4 GiB/20 GiB 稀疏磁盘，网关与镜像还占额外资源。首次下载与镜像构建可能持续十几分钟，持续观察进度；不要因一次超时重复创建。用活动进程与日志判断，不把旧 pid 文件当成仍在运行。

## 出口

优先注册自己的 VPS 出口，使用上游 `pvm exit add NAME --server HOST:PORT --token-file PRIVATE_FILE --fingerprint VERIFIED_FINGERPRINT`。由 Agent 按上游版本准备 exit agent，保留服务原值；初次证书指纹经可信通道核对。令牌不放命令行或聊天。

用户选择 WARP 时使用上游 add-warp，但不得把它描述为固定地区专用出口。没有外部出口也可显式 `--exit direct` 创建本地 Linux 环境；这使用宿主网络，不满足专用地区出口要求。不要默默替用户选 direct。

## 创建与日常使用

```bash
zhibi vm prepare --workspace VM_WORKSPACE --project LOCAL_PROJECT --name dev1 --exit MY_EXIT \
  --timezone Asia/Tokyo --locale en_US.UTF-8
zhibi vm provision --workspace VM_WORKSPACE --apply
zhibi vm status --workspace VM_WORKSPACE --live
```

prepare 只保存私人计划。provision 顺序是创建但不启动 → 首次启动建立网关 → 设置这台 VM 的出口 → 在 guest 持久禁用 IPv6并核验 → coherent 共享当前项目到 `/workspace`。不会修改整个集群默认出口。PVM v1.1.6 首次启动才创建网关，无法在网关不存在时设置实例出口。因此镜像构建和首次系统启动使用准备阶段网络；出口设置完成前不共享项目、不安装或启动用户应用。若用户要求连系统首次启动也不能直连，先由 Agent 准备独立出口环境，不能使用本流程直接交付。

失败时状态与各步骤的 `*.private.log` 保存在工作区。现有 VM 不会被自动删除，也不会自动重放创建。Agent 先用同一 PVM_HOME 的 `pvm ls`、`pvm mount ls NAME`、`pvm route ls` 和日志定位，再处理失败步骤；处理完成后用 `vm reconcile --workspace VM_WORKSPACE --apply` 读回镜像、用户、共享目录、出口和目录可访问性，符合计划才恢复 ready；不要手改 phase。准备重新创建时先显式清理本次实例，不能删除其他 VM 或整个 PVM_HOME。

在 VM 内按用户提供的方式安装应用，验证版本和实际启动。不要从宿主复制 HOME、Git 身份、SSH agent 或浏览器配置。需要同一系统浏览器时在 VM 桌面内安装用户选择的 Linux 浏览器；桌面本身不是已经安装或验证的浏览器。

```bash
zhibi project bind --backend pvm --vm-workspace VM_WORKSPACE --project LOCAL_PROJECT \
  --command-file START_SCRIPT --resume-file RESUME_SCRIPT --interactive
zhibi project start --project LOCAL_PROJECT --apply
zhibi project resume --project LOCAL_PROJECT --apply
zhibi vm desktop --workspace VM_WORKSPACE --apply
zhibi vm stop --workspace VM_WORKSPACE --apply
```

project start 会启动 VM、检查默认出口仍符合绑定、重新禁用并核验 guest IPv6，再进入 `/workspace`。应用 HOME 保存在虚拟磁盘；恢复脚本按应用自身协议。VM 关机后任务不继续运行，需要常驻时优先远程路线。desktop 只打开回环桌面，不启用 public；URL 含密码，不贴进聊天或公开日志。

本地编辑器与 VM 共享同一项目；测试双向可见与文件权限。图片保存到项目中，向应用提供 `/workspace/相对路径`。不额外挂载整台电脑，也不承诺跨桌面快捷键与图片剪贴板已自动适配。

IPv6 默认关闭：只在这台 guest 写入 `/etc/sysctl.d/99-zhibi-disable-ipv6.conf`，并用 GRUB 启动参数 `ipv6.disable=1` 防止网络管理器在重启后重新启用，不改宿主或其他 VM。`vm start`、`project start/resume`、`vm desktop` 会应用并核验；失败就不启动应用或桌面。已有工作区执行 `vm start --workspace VM_WORKSPACE --apply` 即可更新。不要绕过知彼入口后假定策略已生效。

## 验收与恢复

`vm audit --workspace VM_WORKSPACE --network` 逐项读 PVM 的 TCP/UDP/ICMP/DNS/IPv6、时区和语言结果，同时列出路由规则。warn/skipped/缺失项不算通过；WARP 无专用 probe agent 时可能有跳过。规则里的 direct/internal 例外仍然有效。

继续按 [项目验收](audit.md) 验证应用实际出口、VM 浏览器、断开与恢复。重启后检查项目内容、应用配置和会话仍然存在。关闭桌面用同一 PVM_HOME 的 `pvm desktop NAME --stop`；停止 VM 用知彼 stop；解除项目绑定不会删除 VM。真正卸载前由用户明确选择是否保留虚拟磁盘、登录信息及应用会话。
