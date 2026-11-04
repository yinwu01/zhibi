# 开发者实验：从一个事实到一条建议

## 先运行三个有不同答案的例子

```bash
python -m pip install -e '.[dev]'
zhibi lab routing
zhibi lab failure
zhibi lab repair
```

| 实验 | 预期行为 | 解释 |
| --- | --- | --- |
| routing | 出口差异由 needs_confirmation 变为 verified | 只改变“有意分流”的背景，说明建议不能脱离用户预期 |
| failure | coverage 为 unavailable，没有 verified 判断 | 测量失败不产生安全结论 |
| repair | host.proxy 从 needs_confirmation 变为 verified | 两个合成环境从冲突变为一致，仅证明变量检查的语义 |

repair 不修改你电脑上的代理。修好这项模拟冲突也不能证明账号结果改善。

## 读一条完整调用链

`checks.proxy_check` 只保留变量是否存在、是否带认证、是否有不支持的协议和大小写冲突。
地址、用户名、密码都不进入观测。`models.validate_observations` 按字段白名单校验输入。
`engine.evaluate` 根据背景选择建议，再检查主张状态与来源有效期。
`reports` 渲染三个报告格式；`privacy.agent_summary` 从固定词汇重新构建最小摘要。

```bash
zhibi explain host.proxy
zhibi theory --format json --out theory.json
zhibi demo --scenario proxy-conflict --out /tmp/zhibi-before
zhibi demo --scenario proxy-corrected --out /tmp/zhibi-after
zhibi compare /tmp/zhibi-before/report.json /tmp/zhibi-after/report.json
```

输出目录需要不存在。Windows 可换成当前目录下的新文件夹。

## 增加一个检查时改哪里

1. 在 [特征目录源数据](../../../src/zhibi/data/features.json) 定义对象、可见范围、正常反例和验证方法。
2. 在 [主张库](../../../src/zhibi/data/claims.json) 定义范围与反驳条件；未验证的平台假设保持 proposed。
3. 在 [models.py](../../../src/zhibi/models.py) 增加最小字段契约，在 [checks.py](../../../src/zhibi/checks.py) 实现观测。
4. 若要联网，先扩充 [transport.py](../../../src/zhibi/transport.py) 白名单和 `plan`；默认关闭、固定接收方、无凭据。
5. 添加 [规则](../../../src/zhibi/data/rules.json) 和受控处理器；研究材料不能动态执行代码。
6. 只为有意义的正确性边界补测试：正常反例、失败、隐私、证据失效、输出和导出。

不要为了“凑特征”采集更多私密资料。没有可执行建议的特征可以先留在研究层。

## 运行验收

```bash
python -m unittest discover -s tests -v
python scripts/build_examples.py
python scripts/build_knowledge_docs.py
python scripts/check_repository.py
python -m build
python scripts/verify_distribution.py
```

浏览器视觉验收见 [验证记录](../../architecture/validation.md)。CI 使用合成输入，不调用真实账号和外部诊断服务。
