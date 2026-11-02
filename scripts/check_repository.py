"""Check local links, packaged provenance and synthetic report contracts."""
import json
import re
from pathlib import Path
from urllib.parse import unquote

import jsonschema

from zhibi.engine import bundle, validate_report
from zhibi.models import browser_input, read_json
from zhibi.research import validate_knowledge
from zhibi.scan import validate_scan

root = Path(__file__).resolve().parents[1]
assert (root / "start.html").read_bytes() == (root / "src/zhibi/assets/browser.html").read_bytes(), "Rebuild start.html with scripts/build_start.py"
errors = []
roots = [root / n for n in ("docs", "templates", "tutorials", "knowledge", "skills", "examples")]
paths = list(root.glob("*.md"))
for folder in roots:
    paths.extend(folder.rglob("*.md"))
for path in paths:
    content = path.read_text(encoding="utf-8")
    for link in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", content):
        link = link.split("#")[0].strip("<>")
        if not link or "://" in link or link.startswith("mailto:"):
            continue
        if not (path.parent / unquote(link)).exists():
            errors.append(str(path.relative_to(root)) + ": broken local link: " + link)
schema = read_json(root / "schemas/report.schema.json")
jsonschema.Draft202012Validator.check_schema(schema)
report = read_json(root / "examples/report.sample.json")
jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(report)
validate_report(report)
assert report["sample"] is True
scan = validate_scan(read_json(root / "examples/scan.sample.json"))
assert scan["sample"] and scan["data_flows"] == []
validate_knowledge()
source_ids = {s["id"] for s in bundle("sources")}
rule_ids = [r["id"] for r in bundle("rules")]
assert len(rule_ids) == len(set(rule_ids))
for rule in bundle("rules"):
    assert set(rule["sources"]) <= source_ids
    assert rule["counterexample"] and rule["motivation"]
if errors:
    raise SystemExit("\n".join(errors))
print("Local links, report schema and provenance references passed.")
