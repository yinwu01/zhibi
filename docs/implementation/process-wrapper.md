# 通用进程包裹：实施与验收

## 已实现

`process-workspace` 创建专用 HOME、环境变量白名单、指定工作目录及可选只读应用目录。导出的 `run.py -- PROGRAM ARGS...` 在 Linux 用 bubblewrap 执行，依赖缺失时退出，不回退原始程序。

- 默认 `isolated` 网络：独立网络空间，没有外部线路。
- 显式 `host` 网络：仍隔离文件与进程，但共享服务器网络。
- 系统运行库只读；临时目录与 /proc、/dev 独立；不挂载宿主 HOME。
- TZ、LANG、LC_ALL 在启动进程时设置，不再只生成语言文件。目标 locale 必须由 Agent 在服务器核验可用。
- 用户安装的应用可用 --app-dir 显式只读映射到 /opt/app；原账号配置不会自动复制，应用在新 HOME 自行初始化。

2026-11-05：在现有 Linux 开发服务器的独立临时目录测试通过：独立 HOME、TZ 生效、宿主环境变量未继承、原用户 SSH 目录不可见、指定工作目录可写、直接 TCP 连接失败。未修改现有应用启动器和代理。

## 接下来需要完成

- 用户实际联网应用的完整操作、交互、升级后检查；用户级持续托管与恢复已实现并实测。
- 长期会话与完整应用操作测试；真实外部 HTTPS 已通过。
- 公开发布前检查 Git 历史、用户数据、第三方许可、文档声明和发布包，完成后再处理仓库可见性。

参考：
- [bubblewrap 官方说明](https://github.com/containers/bubblewrap)
- [graftcp 官方说明](https://github.com/hmgle/graftcp)

本项目调用外部工具，不复制或打包其源码/二进制；如后续分发，需另行落实对应许可。

## 独立命令入口

`process-entry --workspace PROFILE --name myapp --program /opt/app/bin/myapp` 生成 `PROFILE/bin/myapp`，不覆盖应用自己的安装入口；返回 PATH 激活、检查与移除命令。程序路径必须是沙箱内绝对路径，参数按原样传递。同名文件存在时拒绝覆盖。

2026-11-05 在 Linux 临时工作区执行 `scripts/verify_process_workspace.py`：通过 PATH 启动、应用文件原子替换后再次启动、子进程 HOME、环境变量隔离、参数保留、退出码 7 传递，以及 bwrap 缺失时退出 125 均通过。测试未改现有应用、代理或账号。

这覆盖了保持路径不变的应用更新。安装器迁移路径、shell 别名/函数、绝对路径启动、后台服务的 ExecStart 仍需单独核对；不能仅凭 PATH 入口宣称所有启动方式均被强制包裹。CI 已加入独立 Linux bwrap 验证任务；当前 GitHub 账号账单锁定阻止任务启动，尚无远端 CI 通过结果。

## 指定代理联网

当前适配并实测的是 [graftcp 574b30b](https://github.com/hmgle/graftcp/tree/574b30bfe1d4d36b3f3bff72041665b4df19573f)，使用合并后的 `local/graftcp`；旧版 graftcp-local/FIFO 接口不适用。源码在隔离目录编译，项目不分发其源码或二进制。构建工具与第三方依赖许可由部署时核对。

```bash
zhibi process-workspace --out PROFILE --workdir WORK --app-dir APP_DIR \
  --network proxy --graftcp /absolute/path/to/graftcp \
  --graftcp-sha256 VERIFIED_SHA256 --proxy-socket /private/directory/proxy.sock \
  --dns-server 1.1.1.1
```

`VERIFIED_SHA256` 是对可信来源构建产物计算的 SHA256；每次启动重新核对，文件变化即拒绝运行。socket 必须属于当前用户，位于当前用户所有且其他用户不可访问的目录。该端点须提供 SOCKS5 CONNECT。

运行器创建无外部路由的独立网络空间，用只读挂载的 Unix socket 接入宿主代理。初始化阶段以映射到宿主当前用户的命名空间 UID 0 创建无外部路由的 dummy 接口，让 AI_ADDRCONFIG 可用；随后 setpriv 清空所有 capabilities 并启用 no-new-privileges，再启动 graftcp 与应用。这里的 UID 0 不具有宿主 root 权限。

graftcp 显式使用空配置、only_socks5、DNS-over-TCP，禁用通用 UDP，不继承用户历史 graftcp 配置。依赖 bubblewrap、iproute2、util-linux 的 setpriv；缺失或初始化失败直接退出。不存在 direct 回退路径。

Linux 实测 `scripts/verify_proxy_workspace.py /path/to/graftcp` 通过：TCP 请求、DNS 请求实际到达受控代理，孙进程联网成功；应用的 CapEff/CapPrm/CapInh/CapBnd/CapAmb 均为零；没有默认路由；IPv4/IPv6 的直接 UDP 发送失败；停止代理后联网失败。测试只操作临时目录与专用 namespace，不使用已有代理和应用凭据。

## 私人网关

```bash
install -d -m 700 /absolute/private/gateway
zhibi proxy-gateway --socket /absolute/private/gateway/proxy.sock
```

网关前台运行，仅监听私人 Unix socket，使用服务器已有 TCP 出口，不开放公网代理端口，不保存目的地址或流量内容。支持 SOCKS5 CONNECT、IPv4/IPv6/域名、TCP 半关闭；限制最多 64 个并发连接、600 秒空闲超时。退出时只移除自己创建的 socket，已有路径拒绝覆盖。网关允许应用访问服务器可到达的目的地址，包括本机地址；它是出站通道，不是目标地址访问控制器。

`--dns-server` 必须填写此网关能够通过 TCP 53 访问的解析器。实测服务器不能访问公共解析器的 TCP 53，选择了其已有解析器；没有修改宿主 DNS 或路由。不要把不可达解析器的问题掩盖为直接联网回退。

代理工作区通过 gai.conf 优先 IPv4，避免 IPv6 不可用时 graftcp 已完成本地 connect、远端失败却表现为 TLS 重置的问题。这影响采用系统地址排序的应用，不承诺改写所有应用的自有 DNS/地址选择逻辑。

2026-11-05 运行 `scripts/verify_proxy_live.py --graftcp BINARY --url https://example.com --dns-server RESOLVER`：使用本项目网关，HTTPS 证书校验正常，返回 200，读取 577 字节；关闭网关后新应用请求失败。网关大块传输与 TCP 半关闭另有 262144 字节测试。实际付费应用登录、交互和长期任务仍需独立验收。

## 用户级持续服务

`runtime-service --workspace PROFILE --name zhibi-NAME --out SERVICE_DIR` 导出网关服务，可追加 `-- PROGRAM ARGS...` 托管非交互后台应用。目录中的 `manage.py install/status/rollback` 不依赖源码仓库或 Agent 会话。工作区和 graftcp 仍保留在原安装路径。

先正常关闭用于创建工作区的前台网关，再安装服务；它不会删除未知的已有 socket。仅安装新名称，不覆盖已有系统或用户服务。Type=notify 在 SOCKS5 握手验证完成后报告就绪；网关故障触发整套运行环境重启，停止与恢复清理该服务的进程组。安装失败恢复为安装前不存在的单元状态。后续修改过的单元或新增 drop-in 会阻止自动删除。

已在真实 Linux user manager 中运行 `scripts/verify_runtime_service.py BINARY`，验证启动、网关故障重启、同名冲突保护、显式恢复和失败启动自动恢复；测试路径包含空格、美元符号、百分号及引号。全部随机测试服务均已恢复，未修改既有服务。服务就绪验证不代替应用业务操作验收。用户退出登录后的持续运行取决于 user manager/linger 配置，导出与安装不会擅自改变该设置。

故障测试使用 SIGKILL 强制终止网关。服务保存 socket 的设备号与 inode 回执，重启前仅清理回执匹配、当前用户所有且已无监听者的残留端点；未知或仍在运行的端点拒绝删除。

实际应用启动验证：在临时专用 HOME 与只读应用目录内，通过生成的 PATH 命令入口运行已安装的 Claude Code `--version`，返回 `2.1.318 (Claude Code)`，退出码 0。没有使用原账号配置或进行付费请求；这项证据证明实际程序能够启动，不等同于已完成登录后的业务会话。
