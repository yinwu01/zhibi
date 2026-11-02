# 深入检查：使用命令行

只想先检查当前浏览器？下载并打开 [start.html](../start.html)，点击“开始检查”即可。
本教程面向需要检查电脑配置、比较不同入口或使用完整报告的用户，需要 Python。

本教程演示软件使用。实际注册资料、验证和账号决定均在官方服务完成。
不需要先登录 目标服务，也不需要把浏览器资料目录交给工具。

## 安装

从本地源码目录运行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
zhibi doctor
zhibi demo
```

### Windows

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install .
zhibi demo
```

命令输出报告路径。用浏览器打开 HTML；不要把模拟报告当成自己的检测结果。

## 1. 说明使用场景

复制 [profile.json](../examples/profile.json)，按需要填写：

```json
{"product":"web","stage":"registration","country_code":null,"route_intent":"unknown"}
```

- product：web / code / api。
- country_code：真实使用地区的两位大写代码；不想填写或不确定时保留 null。不会通过 IP 替你填写。
- route_intent：期望两侧相同填 same；有意分流填 different；未知填 unknown。
- 不要加入邮箱、手机、Cookie、token、卡号或自由文本；未知字段会被拒绝。

地区代码只提供人工核对背景，alpha 没有自动资格判定。
官方地区来源若尚未生效或已过复核期，会要求先核对原始页面。

## 2. 先做本地检查

```bash
zhibi plan
zhibi check --profile examples/profile.json
```

检测：工具运行条件、代理环境变量状态、DNS 配置文件的解析器数量、目标客户端 是否能从 PATH 找到。
不会执行 目标服务，也不会读取其登录文件。默认未知项较多，是因为外部观测没有启用。

## 3. 在实际浏览器采集

```bash
zhibi browser --out browser.html
```

在准备使用的浏览器中打开文件，点击“开始检查”，先直接阅读结果。
需要导入深入检查时，展开“交给 Skill 做进一步检查”，预览 JSON，再保存浏览器结果。
文件页可能限制存储；不要把这个限制直接解释成 目标站点无法登录。

```bash
zhibi check --profile examples/profile.json --browser ~/Downloads/zhibi-browser.json
```

该 JSON 可能包含 IP，保留在本地。无需粘贴给 AI。

## 4. 按需比较出口

在探针页主动勾选 IPv4 测量后重新采集，在五分钟内运行：

```bash
zhibi check --network --browser ~/Downloads/zhibi-browser.json
```

只有端点、地址族、时间和实际浏览器上下文可比，工具才比较出口。
有意分流时应在 profile 中明确，并结合实际访问目标判断；不要仅因差异购买新的网络服务。
诊断端点不代表到 目标站点的路由。可选 `--ipv6` 观测 IPv6 专用端点，
`--connectivity` 测公共首页无会话 HEAD；这两项仍不能证明泄漏或账号状态。
高级浏览器页面支持 WebRTC，见 [Skill 教程](skill.md)；命令行 DNS 观察见 [DNS 教程](dns.md)。
这些独立测量不替代实际浏览器的全部解析路径。

## 5. 读报告，完成准备

每次检查同时生成 `preparation.md`，也可以单独运行
`zhibi guide --profile examples/profile.json`。清单保持“待完成”，不会替你确认实际步骤。

先看“需要处理”和“需要确认”，展开每项的依据与正常反例：

1. 按报告中的官方链接确认服务范围和产品条件。
2. 为当前使用入口准备必要客户端；只用网页版无需先装 CLI。
3. 对确认属于故障的配置做具体调整，保留修改前记录。
4. 在官方页面自行完成注册和必要验证；账号资料不交给知彼。
5. 若收到限制或验证提示，记录错误类别与时间，并使用官方支持或申诉流程。

这些步骤帮助厘清准备工作，不给出账号通过保证。
遇到具体错误，继续 [异常排查](troubleshooting.md)。

## 6. 复查与分享

```bash
zhibi compare /path/to/before/report.json /path/to/after/report.json
zhibi export /path/to/after/report.json
```

比较只说明规则状态变化。分享前检查摘要；命令不会上传任何内容。
原始 snapshot.private.json 不适合发到公开 Issue。

## 失败怎么办

| 情况 | 处理 |
| --- | --- |
| zhibi 命令不存在 | 激活安装它的虚拟环境，或直接使用虚拟环境里的可执行文件 |
| 输出目录已存在 | 换一个新目录；工具不会覆盖旧报告 |
| 输入被拒绝 | 检查模板、未知字段、大小与时间格式；不要粘贴敏感内容 |
| 外部请求超时 | 当前只能说明测量未完成；检查网络可用性或保持离线模式 |
| 使用 SOCKS 代理 | 此版本的 CLI HTTP 传输不支持 SOCKS；可使用浏览器探针 |
| 报告显示来源过期 | 打开官方来源重新核对，按贡献流程更新来源与测试 |
