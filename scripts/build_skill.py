"""Build a portable Skill with a deterministic stdlib-only Python zipapp."""
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAMP = (2026, 10, 18, 0, 0, 0)


def add(archive, name, data):
    entry = zipfile.ZipInfo(name, date_time=STAMP)
    entry.compress_type = zipfile.ZIP_DEFLATED
    entry.external_attr = 0o644 << 16
    archive.writestr(entry, data)


def build(destination=None):
    destination = Path(destination) if destination else ROOT / "dist"
    destination.mkdir(parents=True, exist_ok=True)
    output = destination / "zhibi-skill.zip"
    core = destination / "zhibi-core.pyz"
    with zipfile.ZipFile(core, "w") as archive:
        add(archive, "__main__.py", b"from zhibi.cli import main\nraise SystemExit(main())\n")
        for path in sorted((ROOT / "src" / "zhibi").rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix in (".py", ".json", ".html", ".css", ".js", ".txt"):
                if path.is_symlink():
                    raise ValueError("Symlink in package sources")
                add(archive, path.relative_to(ROOT / "src").as_posix(), path.read_bytes())
    with zipfile.ZipFile(output, "w") as archive:
        base = ROOT / "skills" / "zhibi"
        for path in sorted(base.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix in (".md", ".yaml", ".py"):
                if path.is_symlink():
                    raise ValueError("Symlink in skill resources")
                add(archive, "zhibi/" + path.relative_to(base).as_posix(), path.read_bytes())
        add(archive, "zhibi/assets/zhibi-core.pyz", core.read_bytes())
        add(archive, "zhibi/LICENSE", (ROOT / "LICENSE").read_bytes())
        notice = ROOT / "THIRD_PARTY_NOTICES.md"
        if notice.exists():
            add(archive, "zhibi/THIRD_PARTY_NOTICES.md", notice.read_bytes())
            add(archive, "zhibi/docs/research/upstream-lock.json", (ROOT / "docs/research/upstream-lock.json").read_bytes())
        for path in sorted((ROOT / "licenses").glob("*")):
            if path.is_file():
                add(archive, "zhibi/licenses/" + path.name, path.read_bytes())
    return {"skill": str(output), "core": str(core), "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
