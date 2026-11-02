# DNS 检测：先分清测的是哪条路径

`scan` 读取本地 DNS 配置概况；`dns` 提供独立、可选的解析器观察。二者不替代浏览器 DNS 检测。

## 使用

在安装后的 Skill 中让 Agent 执行：

```bash
python3 <skill>/scripts/zhibi.py dns --dry-run
python3 <skill>/scripts/zhibi.py dns --network --out dns-report
```

将 `<skill>` 换成实际安装目录。第一次命令只展示查询范围；第二次需要本机已有 `dig`。
省略 `--network` 不发起 DNS 查询。没有 dig 返回 `unsupported`，不自动安装工具。
存在自定义 `~/.digrc` 时返回 `configuration_present`，不读取内容、不修改文件、不执行其中的设置。

打开 `dns-report/report.html` 阅读结果。Agent 只读 `agent-summary.json`；
解析器 IP 和 ECS 子网保存在 `snapshot.private.json`，不需要贴到聊天中。

## 测量范围

通过 dig 默认解析器查询固定名称 `whoami.ds.akahelp.net.` 的 TXT 记录。
按 [Akamai 的接口说明](https://www.akamai.com/blog/developers/introducing-new-whoami-tool-dns-resolver-information)，
`ns` 描述递归解析器，`ecs` 是可能传递的子网；`ip` 是该子网的代表值，本项目不把它当作用户公网 IP。

这次查询沿 DNS 链路发生，不自动遵循 HTTP 代理。接收方包括当前 DNS 链路及可能被联系的 Akamai 权威服务。
调用一次 dig，设置查询尝试与超时，并在八秒后终止进程；递归服务内部可能发起多个查询。
不改变解析器，不提交账号、Cookie 或供应商密钥。

## 结果怎么用

| 观察 | 可以判断 | 仍然不知道 |
| --- | --- | --- |
| 返回解析器记录 | 该诊断查询返回了哪些递归出口 | 浏览器 DoH、系统分域解析、其他应用是否使用相同链路 |
| 返回 ECS | 响应包含子网信息 | 所有请求是否传递 ECS、平台如何使用它 |
| DNS 与 HTTPS 地址不同 | 两者是不同测量对象 | 是否违反用户预期，不能仅凭地址不同判定泄漏 |
| 失败、空响应或工具缺失 | 此次测量未完成 | 不能给出“无泄漏”结论 |

固定诊断名称可能命中缓存；不承诺新鲜的权威观察，也没有进行独立 DNSSEC 校验。
浏览器路径需要在实际浏览器内单独取得证据。默认不根据 DNS 结果更改系统配置。

命令参数依据 [BIND dig 文档](https://bind9.readthedocs.io/en/v9.20.23/manpages.html)。
原始响应由严格解析器处理；异常文本不会进入 Agent 摘要。

[返回 Skill 教程](skill.md) · [读懂报告](ip-report.md)
