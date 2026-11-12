# 项目绑定、会话与文件

用于用户希望以后自己启动、继续同一项目或传入文件时。绑定保存在 `~/.zhibi/projects`（700），不读取项目仓库里的自动执行配置；脚本复制到私人状态目录（600）。不要把该目录提交 Git。

## 远程路线

先按 runtime 参考准备应用；绑定不代替依赖安装、隔离或出口验收。用户的启动脚本应调用已经准备好的进程入口。远端项目目录必须已存在。

```bash
zhibi project bind --project LOCAL_PROJECT --host HOST --user USER --identity KEY \
  --workdir REMOTE_PROJECT --command-file START_SCRIPT --resume-file RESUME_SCRIPT --interactive
zhibi project status --project LOCAL_PROJECT
zhibi project status --project LOCAL_PROJECT --live --network
zhibi project start --project LOCAL_PROJECT --apply
zhibi project resume --project LOCAL_PROJECT --apply
```

省略 `--project` 使用当前目录。当前按精确目录绑定，不自动继承父目录绑定。`status` 默认只读保存的配置；`--live` 检查真实服务器，`--network` 额外测出口。`start/resume` 不带 `--apply` 只预览，执行时先检查远端项目目录。交互程序需要 PTY。

恢复脚本是可选项，只在应用支持时填写，例如应用自身的 continue/resume 命令。不存在通用会话恢复协议。HOME/应用数据由已有进程工作区持久化，绑定只记住连接和命令。终端断开后需要继续运行的任务使用 runtime-service 等进程托管，不能承诺历史会话恢复会维持后台运行。

启动时本机 SOCKS 默认 10818，与已有浏览器工作区接法一致。端口冲突明确失败，不接管现有监听。远程进程实际出口仍需验收。

## 文件与图片

日常开发优先用编辑器的远程 SSH 工作区，直接编辑远端文件。传图、报告和单个文件使用显式传输：

```bash
zhibi project upload --local IMAGE_OR_FILE --remote-file uploads/example.png --apply
zhibi project download --remote-file reports/result.txt --local NEW_LOCAL_FILE --apply
```

远端需 Python 3。路径相对绑定的远端项目，父目录需预先存在。目标必须不存在；禁止覆盖、`..`、通过符号链接逃出项目。上传校验大小与 SHA256 后才发布文件。下载失败清理本次不完整文件。不实现双向同步，不自动抓取用户剪贴板。先把选定图片保存为文件再上传，将远端路径提供给应用。

## 解除与变更

`project unbind --apply` 仅删除已知绑定文件，不删除远端项目、应用配置、SSH 密钥或任何会话。目录里有额外文件则拒绝删除。更换绑定时先记录 status，再解除并重新 bind；不要直接修改保存的启动脚本，完整性检查会拒绝运行。

## 验证

实际启动一个无副作用的命令，检查远端工作目录、退出码、终端需求；结束后重新启动验证配置仍在。恢复会话要用应用真实历史验证。上传一张测试图片并下载比对，确认非 ASCII 路径与权限符合使用需求。网络验收另外执行，不以启动成功代替。
