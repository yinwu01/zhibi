"""Build a reviewable source ZIP from an explicit public-file allowlist."""
import hashlib
import json
import zipfile
from pathlib import Path

from zhibi import __version__

root = Path(__file__).resolve().parents[1]
dist = root / "dist"
dist.mkdir(exist_ok=True)
files = [root / n for n in (
    "README.md", "README.en.md", "CONTRIBUTING.md", "SECURITY.md", "CHANGELOG.md",
    "LICENSE", "THIRD_PARTY_NOTICES.md", "MANIFEST.in", "pyproject.toml", ".gitignore", "start.html")]
extensions = {".py", ".md", ".json", ".html", ".css", ".svg", ".png", ".yaml", ".yml", ".cjs", ".js", ".txt"}
for directory in (".github", "src/zhibi", "scripts", "tests", "docs", "examples", "knowledge", "schemas", "skills", "templates", "tutorials", "licenses"):
    files += [p for p in (root / directory).rglob("*")
              if p.is_file() and p.suffix in extensions and "__pycache__" not in p.parts]
files = sorted(set(files))
if any(p.is_symlink() or ".private." in p.name for p in files):
    raise SystemExit("Unexpected private file or symlink in public release selection.")
prefix = "zhibi-" + __version__
archive = dist / (prefix + "-source.zip")
(dist / "start.html").write_bytes((root / "start.html").read_bytes())
with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
    for path in files:
        info = zipfile.ZipInfo(prefix + "/" + path.relative_to(root).as_posix(), date_time=(2026, 10, 18, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        output.writestr(info, path.read_bytes())
from build_skill import build
skill = build(dist)
artifacts = sorted([*dist.glob("zhibi-" + __version__ + "-*.whl"), *dist.glob("zhibi-" + __version__ + "*.tar.gz"), archive, dist / "start.html", Path(skill["skill"]), Path(skill["core"])])
digests = [(p.name, hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_size) for p in artifacts]
(dist / "SHA256SUMS").write_text("".join(digest + "  " + name + "\n" for name, digest, _ in digests), encoding="utf-8")
print(json.dumps({"archive_files": len(files), "artifacts": [
    {"file": name, "sha256": digest, "bytes": size} for name, digest, size in digests]}, indent=2))
