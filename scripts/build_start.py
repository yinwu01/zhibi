"""Publish the same self-contained browser tool as a directly openable root file."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
(root / "start.html").write_bytes((root / "src/zhibi/assets/browser.html").read_bytes())
print("start.html is ready: open directly; no installation required.")
