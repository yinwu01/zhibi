"""Rebuild only public synthetic artifacts. No live observations are published."""
import json
import tempfile
from pathlib import Path

from zhibi.demo import SCENARIOS, fixture
from zhibi.engine import evaluate
from zhibi.models import timestamp
from zhibi.reports import html, markdown
from zhibi.research import render_learning_html
from zhibi.guidance import preparation_markdown
from zhibi.scan_demo import run_demo
from zhibi.scan import render_scan, scan_markdown, validate_scan

root = Path(__file__).resolve().parents[1]
examples = root / "examples"
for scenario in SCENARIOS:
    data = fixture(scenario)
    (examples / "scenarios").mkdir(exist_ok=True)
    (examples / "scenarios" / (scenario + ".json")).write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
data = fixture()
report = evaluate(data["observations"], data["profile"], sample=True, at=timestamp(data["evaluated_at"]))
(examples / "report.sample.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
(examples / "report.sample.html").write_text(html(report), encoding="utf-8")
(examples / "report.sample.md").write_text(markdown(report), encoding="utf-8")
(examples / "learning.html").write_text(render_learning_html(), encoding="utf-8")
(examples / "preparation.sample.md").write_text(preparation_markdown(data["profile"], timestamp(data["evaluated_at"])), encoding="utf-8")
with tempfile.TemporaryDirectory(prefix="zhibi-examples-") as tmp:
    result = run_demo("conflicting-sources", str(Path(tmp) / "scan"))
    scan = json.loads((Path(result["directory"]) / "report.json").read_text(encoding="utf-8"))
    validate_scan(scan)
    assert scan["sample"] and scan["data_flows"] == []
    snapshot = json.loads((Path(result["directory"]) / "snapshot.private.json").read_text(encoding="utf-8"))
    assert snapshot["sample"]
    (examples / "scan.sample.json").write_text(json.dumps(scan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (examples / "scan.sample.html").write_text(render_scan(scan, snapshot), encoding="utf-8")
    (examples / "scan.sample.md").write_text(scan_markdown(scan), encoding="utf-8")
print("Rebuilt synthetic scenarios and sample reports.")
