"""Local README preview; optional development dependency: markdown-it-py."""
from pathlib import Path
import re
from html import unescape
from markdown_it import MarkdownIt

root = Path(__file__).resolve().parents[1]
destination = root / ".preview"
destination.mkdir(exist_ok=True)
md = MarkdownIt("commonmark", {"html": True}).enable("table")
content = md.render((root / "README.md").read_text(encoding="utf-8"))
def heading(match):
    plain = unescape(re.sub("<[^>]+>", "", match.group(2))).lower()
    slug = re.sub(r"[^\w\- ]", "", plain).replace(" ", "-")
    return '<h' + match.group(1) + ' id="' + slug + '">' + match.group(2) + '</h' + match.group(1) + '>'
content = re.sub(r"<h([1-6])>(.*?)</h\1>", heading, content)
content = content.replace('href="#', 'href=".preview/readme.html#')
# Local preview only: navigation is still relative to the repository.
style = """
*{box-sizing:border-box}body{margin:0;background:#f6f8fa;color:#1f2328;font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}
.bar{padding:18px 30px;background:#fff;border-bottom:1px solid #d1d9e0;font-size:15px}.bar b{color:#0969da}.bar span{float:right;color:#59636e;font-size:12px}
main{max-width:1012px;background:#fff;border:1px solid #d1d9e0;border-radius:6px;margin:28px auto;padding:38px 46px}
img{max-width:100%;height:auto}h1,h2{border-bottom:1px solid #d1d9e0;padding-bottom:9px;line-height:1.3}h2{font-size:24px;margin-top:36px}h3{font-size:20px}
a{color:#0969da;text-decoration:none}a:hover{text-decoration:underline}code{background:#eff1f3;padding:2px 6px;border-radius:4px;font-size:85%}
pre{background:#f6f8fa;padding:16px;border-radius:6px;overflow:auto;line-height:1.5}pre code{padding:0;background:transparent}
table{border-collapse:collapse;display:block;overflow:auto;margin:18px 0}td,th{border:1px solid #d1d9e0;padding:8px 14px}tr:nth-child(2n){background:#f6f8fa}
blockquote{border-left:4px solid #d1d9e0;padding:0 16px;color:#59636e;margin:20px 0}sub{color:#59636e}
@media(max-width:700px){main{border:0;border-radius:0;padding:22px 16px;margin:0}.bar{padding:14px 16px}.bar span{display:none}body{font-size:14px}h2{font-size:22px}}
"""
page = '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><base href="../"><title>zhibi · README preview</title><style>' + style + '</style></head><body><div class="bar"><b>zhibi</b> / README.md <span>LOCAL PREVIEW · NOT PUBLISHED</span></div><main>' + content + '</main></body></html>'
(destination / "readme.html").write_text(page, encoding="utf-8")
print(destination / "readme.html")
