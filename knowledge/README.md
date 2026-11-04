# 知彼研究入口

这是随代码版本维护的种子知识库，尚不是完整公开资料调查。
当前范围：官方资格/申诉来源、上游反滥用公开披露、支付/反机器人/账号防护的跨平台类比、
网络端点语义、测量解释与正常反例。11 份来源不代表穷尽调查。

| 内容 | 唯一维护位置 |
| --- | --- |
| 来源、核对日期、生效日期、复核周期 | [sources.json](../src/zhibi/data/sources.json) |
| 规则、动机、主张、观测依赖、正常反例 | [rules.json](../src/zhibi/data/rules.json) |
| 有范围的主张、状态、反驳条件 | [claims.json](../src/zhibi/data/claims.json) |
| 特征可见性、派生方式、验证方法 | [features.json](../src/zhibi/data/features.json) |
| 离线课程、练习与答案 | [lessons.json](../src/zhibi/data/lessons.json) |
| 可读的生成目录 | [catalog.md](../docs/research/theory/catalog.md) |
| 从来源到规则的运行时追溯 | [engine.py](../src/zhibi/engine.py)，命令 zhibi explain |
| 特征与案例模板 | [templates](../templates) |
| 竞品主张审查 | [competitor-review.md](../docs/research/competitor-review.md) |

规则数据随 Python 包发布，避免源码知识库和安装包出现两份冲突版本。
证据 Graph 包含来源、主张、特征和规则，不需要数据库服务，也不提供账户关联推断。
运行 `python scripts/build_knowledge_docs.py` 更新文档目录；完整框架见 [知彼理论](../docs/research/theory/README.md)。

接下来优先补充：按日期整理的政策变更、经核验的社区案例、
一般平台风控公开资料，以及对注册准备确实有帮助的可观测特征。
研究队列见 [研究教程](../docs/archive/tutorials/research.md)。
