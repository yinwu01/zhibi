# 参与知彼

优先欢迎三类贡献：能复现的检测问题、带来源的规则纠错、包含正常反例的研究。

## 开发

克隆下来就能跑，不需要安装：

```bash
./scripts/test.sh                 # 等价于 PYTHONPATH=src python3 -m unittest discover -s tests
PYTHONPATH=src python3 -m zhibi --help
```

需要安装时（可选）：

```bash
python -m pip install -e '.[dev]'
python scripts/build_knowledge_docs.py
python scripts/check_repository.py
```

浏览器验收与截图重建（开发时使用；运行时不需要 Node）：

```bash
python scripts/build_examples.py
python scripts/build_start.py
python scripts/render_readme.py
npm install --no-save --package-lock=false playwright
npx playwright install chromium
node tests/browser.cjs
python -m zhibi browser --advanced --out .preview/network.html
node tests/browser-network.cjs
python scripts/verify_skill.py
```

已有浏览器或 Playwright 运行时可用 CHROME_PATH / PLAYWRIGHT_MODULE 指定。
页面验收包括移动端布局、默认离线、主动联网的模拟响应和 JSON 导出。
主要入口是内置核心的 Skill；start.html 保留基础体验，源文件在 src/zhibi/assets/browser.html。
修改基础页面后运行 build_start.py。高级探针由 browser --advanced 从 network.html 与 network-probe.js 合成。
不要引入外部字体或脚本。上游改动需同步 THIRD_PARTY_NOTICES.md、许可证与 docs/upstream-lock.json。

检测核心在 `src/zhibi/`；规则元数据与来源位于 `src/zhibi/data/`。
添加检查时同时说明观测对象、失败状态、外部数据流及不会得出的结论。
为改变用户判断的逻辑增加行为测试，尤其是失败、过期和正常反例。

## 研究

用 [特征卡](templates/feature-card.md) 提交一个可反驳主张。
附出处、版本或提交、观察日期、适用范围、正常反例及证据局限。
帖子属于案例陈述；没有对照和充分样本时，不推断因果或宣称防封成功率。
来源变化后，沿规则引用检查受影响结论。

先读 [理论框架](docs/research/theory/README.md) 与 [开发者实验](docs/archive/tutorials/developer-walkthrough.md)。
跨平台类比和待验证假设可进入研究库，但不能直接启用确定性产品结论。
生成目录与源数据必须一起更新；来源查阅日期不能填未来日期。

## 隐私

公开 Issue 不接收 Cookie、token、原始浏览器导出、私人快照、证件或支付资料。
先运行 `zhibi export <report.json>`，检查摘要后再手动提交。
日志和截图也需检查；不要为了复现问题上传账号。

本项目代码与原创文档使用 MIT。外部网页仍受各自许可约束；
优先提交来源链接和短摘要，不复制完整文章或私人内容。
