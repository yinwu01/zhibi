# 先确认是哪一种问题

同一个数字或提示可以出现在不同产品和阶段。先选择入口、阶段和错误类别，
不把原始响应、请求头、账号邮件或登录截图交给工具。

```bash
zhibi triage --channel web --stage registration --signal http_403
zhibi triage --channel api --stage usage --signal http_401
zhibi triage --channel code --stage usage --signal http_429
zhibi triage --channel web --stage login --signal account_suspended
```

返回的是排查方向、下一步和来源；用户选择“账号暂停”只代表用户报告该提示，
工具没有登录账号进行验证。

| 现象 | 优先排查 | 不能直接推出 |
| --- | --- | --- |
| 解析 / TLS / 超时 | 同一客户端的连接层，保留证书校验 | 账号被暂停 |
| 网页 401 / 403 | 官方页面的登录、验证、访问提示 | API Key 错误或封号 |
| API 401 / 403 | 认证 / 资源权限 | 所有产品的账号状态 |
| 429 | 对应产品的速率、额度和费用上限 | 永久限制 |
| 5xx | 服务可用性 | 用户环境风险 |
| 要求验证 / 付款失败 | 对应官方验证或账单流程 | 必须换身份或购买网络 |
| 明确账号限制通知 | 官方支持与申诉 | 工具能自动解除 |

API 语义参考 [官方错误文档](https://platform.claude.com/docs/en/api/errors)，
账号复核参考 [官方入口](https://support.claude.com/en/articles/8241253-safeguards-warnings-and-appeals)。

## 不带账号的连接诊断

```bash
zhibi plan --network --ipv6 --connectivity
zhibi check --network --ipv6 --connectivity
```

会请求两个 ipify 端点，并向 目标服务 公共首页发送一次无会话 HEAD。
结果仅限这条请求链路；代理可能隐藏实际错误层次，HEAD 也可能与真实浏览器的页面请求不同。
不会绕过 TLS、不跟随重定向、不自动重试、不调用登录或认证接口。

每个 socket 操作超时为 8 秒，系统 DNS 解析可能超过这个时间；这里没有硬性总耗时保证。
不需要这些诊断时保留默认离线模式。
