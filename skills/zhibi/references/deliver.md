# 交付

交付必须包含可使用的入口和本次真实结果。

- 连接入口：`connect --export-out 新目录` 生成独立启动文件夹。保持原密钥可用；实际启动并完成出口检查。
- 报告：`deliver --host HOST --browser 实际浏览器文件 --build-receipt 本轮回执` 保存两端观测、部署记录、远端停止与恢复命令。按本次情况传入用户、端口、密钥、服务名等参数。
- 恢复：自动脚本只恢复本轮服务和时区；软件安装、浏览器设置和其他手工变更须另记原值与恢复方式。
- 重查：`reproduce.sh` 重新检查服务器，不是重建全部环境；浏览器必须另行重新采集。

先报告能否正常运行、能否完成用户需要的操作、哪些项未测或失败，再给出启动、停止、恢复方式及文件夹路径。不把协议通用接入声称为所有浏览器品牌均已实测。

文件夹包含私人连接与读数，默认仅在本机保存；对外分享应使用脱敏摘要。阶段状态由 Agent 落盘并与现场核对，不宣称尚未实现的自动断点续跑。

使用 runtime-service 时，把远端服务目录、服务名、profile 路径和完整 SSH 目标一起记录在私人交付目录，并给出 `manage.py status`、`systemctl --user restart SERVICE` 与 `manage.py rollback` 的远端执行方式。保留该服务目录中的 receipt.json 和 gateway-owner.json；恢复由对应 manage.py 校验文件摘要和端点归属。不要把用户级服务套用成 `/etc/systemd/system` 的旧 build 恢复命令。交互式应用另交付 process-entry 的 PATH 设置与检查方式。
