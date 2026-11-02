"""Generate references from the packaged knowledge; do not maintain a second copy."""
from pathlib import Path

from zhibi.engine import bundle
from zhibi.research import render_theory_markdown, validate_knowledge

root = Path(__file__).resolve().parents[1]
counts = validate_knowledge()
content = render_theory_markdown().replace("# 知彼：平台目标、事件、证据与行动", "# 主张与特征目录", 1)
content += "\n## 特征卡\n\n"
for feature in bundle("features"):
    content += "### " + feature["id"] + " · " + feature["title"] + "\n\n"
    content += "可见范围：" + feature["visibility"] + "\n\n"
    content += "派生方式：" + feature["derivation"] + "\n\n"
    content += "正常反例：" + feature["counterexample"] + "\n\n"
    content += "验证方式：" + feature["validation"] + "\n\n"
    content += "关联主张：" + ", ".join(feature["claim_ids"]) + "\n\n"
content += "\n---\n由 scripts/build_knowledge_docs.py 从 src/zhibi/data 生成；请修改源数据后重新生成。\n"
(root / "docs/theory/catalog.md").write_text(content, encoding="utf-8")
print(counts)
