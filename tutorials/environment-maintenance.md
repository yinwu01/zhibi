# 可选维护：先看计划，按范围执行，保留恢复

全量检测不会调用这些修改。以下 `zhibi` 是已安装 Skill 的脚本或独立核心。只对自己明确选定的专用环境操作；涉及系统/用户级设置时，影响范围可能比浏览器更大。

## IPv6、时区与区域

```bash
zhibi maintain ipv6 off --scope "专用网络服务名称"
zhibi maintain ipv6 off --scope "专用网络服务名称" --apply --out /新的修改记录目录
zhibi maintain restore /修改记录目录/receipt.private.json
zhibi maintain restore /修改记录目录/receipt.private.json --apply --out /新的恢复记录目录
```

首条命令只读原设置、显示具体命令和恢复方式。macOS 使用 networksetup 的网络服务名；Linux 使用 NetworkManager 连接名；Windows 使用网络适配器名。这些工具可能需要用户在自己的终端取得管理员权限；脚本不偷偷 sudo。

macOS 手动 IPv6 地址模式会拒绝自动改写，避免丢失原配置。Linux 修改的是连接配置，可能需要用户选择时重连；不自动中断网络。**写入成功不等于出站已关闭**，还要在相同浏览器重测。报告通过仍要求现有 `confirm-ipv6` 的设置证据；请求失败不能代替设置核对。

`maintain timezone Asia/Taipei` 可预览用户明确选择的时区；macOS 区域可用 `maintain locale en_US`。加 `--apply` 才写入。不会按 IP 所在国家自动改语言/时区。时区支持 macOS/Linux/Windows 适配，区域写入当前仅 macOS；Windows 使用系统的时区 ID。

恢复时重新读当前值；如果已有后续变更，拒绝覆盖。所有操作结果和原值留在本机。

## AdsPower API（可选）

免费用户使用 `session` 即可测量实际浏览器。API 适配是额外能力，官方文档说明可能需要付费权限；不要为基础检测购买套餐。

在权限为 600 的本机 JSON 中配置 `port`（默认 50325）、`profile_id`、可选 `api_key` 和明确的 `patch`，例如 `{"webrtc":"disabled"}`。不要填写 Cookie、账号、密码、坐标或整套未知身份。API 只连接 `127.0.0.1`，不经过 HTTP 代理。

```bash
zhibi adspower inspect --config /本机配置.json --out /新的检查目录
zhibi adspower update --config /本机配置.json --out /新的计划目录
zhibi adspower update --config /本机配置.json --apply --out /新的修改目录
zhibi adspower restore --config /本机配置.json --receipt /修改目录/receipt.private.json --apply --out /新的恢复目录
```

运行中的环境不会被强制关闭。API 未返回待修改字段原值时，拒绝修改；因此不同 AdsPower 版本或套餐可能只支持状态检查。配置保存后还需重新打开同一环境，通过探针验收实际效果。本项目不读取 Cookie、不创建/删除账号、不分享到云端。

## 缓存隔离与本地工作区

关闭目标应用后，明确指定配置目录。默认只预览，`--closed` 表示操作者已经核对关闭；发现运行锁仍会拒绝处理。

```bash
zhibi workspace cache --root /专用配置目录 --closed
zhibi workspace cache --root /专用配置目录 --closed --apply --out /新的隔离目录
zhibi workspace cache-restore --archive /隔离目录 --closed --apply
```

只移动 Cache、Code Cache、GPUCache、Service Worker/CacheStorage，不选 Cookie、Local Storage 或账号文件。原缓存没有删除；恢复时若应用已生成新缓存则拒绝覆盖。不要把缓存隔离叫作登出、清空账号或“设备洗白”。

需要保存完整的用户自选专用目录时，可装可选 `cryptography>=43,<47`：

```bash
zhibi workspace backup --root /专用配置目录 --closed --out /新的备份目录
zhibi workspace restore --root /专用配置目录 --archive /备份目录/profile.enc --closed
zhibi workspace restore --root /专用配置目录 --archive /备份目录/profile.enc --closed --apply
zhibi workspace empty --root /专用配置目录 --closed
```

备份使用 scrypt 与 AES-GCM，口令只在自己的终端隐藏输入，写入前做加密解密往返核验。至多 256 MiB/一万个文件；拒绝符号链接、目录穿越和活跃配置。恢复/空工作区时，旧目录保留在旁边 `*.zhibi-previous-*`，**旧目录是本机原数据，不是加密归档**；权限收紧为 700。需要恢复原目录时，关闭应用，将当前目录移到新位置，再把保留目录改回原名。空工作区加 `--apply` 才执行，不自动归档或伪造身份；建议先完成并验证加密备份。

这是一套用户选择目录的本地备份工具，不复制操作系统 Keychain，不保证某个产品的登录状态可迁移，不接触未经选择的浏览器或账户目录。

## CLI 修复与网络配置交付

```bash
zhibi maintain cli-repair 你的固定版本号
zhibi network-setup client-config --config /本机代理配置.json --out /新的交付目录
zhibi network-setup ssh-tunnel --config /本机SSH配置.json
```

CLI 修复仅支持已检测到的 npm/bun/native 渠道，版本必须为明确的 `x.y.z`；加 `--apply` 才执行，写入前版本被记录，修复后再次读实际版本。未知渠道/brew/winget 不自动替换安装。

代理配置字段为 `type`（socks5/http）、`server`、`port`，可选 `username`、`password`、`local_port`。生成独立 Mihomo JSON 配置和 AdsPower 本地代理配置；文件含私人凭据，只留本机。交付目录附完整运行、导入与回退步骤。默认绑定 loopback，不启用 TUN、系统代理或 LAN；使用者需用已有 Mihomo 检查配置并启动。随后回到实际浏览器测量，不能把文件生成当作部署成功。

SSH 配置字段为 `host`、`user`、`port`、`identity_file`、`known_hosts`、`local_port`。仅使用已有私钥和经过核对的主机密钥；`--apply` 在前台运行 SSH SOCKS，Ctrl-C 停止。不改远端系统，不安装 Xray、不买 VPS，不执行 CCBaga 的整机升级、防火墙/SSH 配置改写或明文订阅服务。

CCBaga 的完整 Debian VPS 部署目前仍是覆盖缺口，详见[能力覆盖](../docs/capability-coverage.md)。这些已交付的客户端/隧道能力不能冒充其整套服务端部署。

## Skill 升级与回退

从本项目 GitHub Release 下载 Skill ZIP 与 SHA256SUMS，核对来源后：

```bash
zhibi skill-install --archive /下载的Skill.zip --sha256 完整SHA256 --dest /实际路径/skills/zhibi --replace
zhibi skill-rollback --dest /实际路径/skills/zhibi --previous /同目录/zhibi.previous-命令返回的编号
```

升级核对包摘要、文件路径、大小和完整性，旧版本保留，不执行新包代码。回退也保留被替换版本。新开宿主会话后用 `doctor` 确认实际载入版本。
