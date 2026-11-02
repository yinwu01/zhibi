#!/usr/bin/env python3
"""One self-contained Skill entrypoint. No pip, installer, network or shell bootstrap."""
import runpy
import sys
from pathlib import Path

if sys.version_info < (3, 9):
    raise SystemExit("知彼需要 Python 3.9 或更新版本。")

skill = Path(__file__).resolve().parents[1]
archive = skill / "assets" / "zhibi-core.pyz"
repository = skill.parent.parent
if archive.is_file():
    runpy.run_path(str(archive), run_name="__main__")
elif (repository / "src" / "zhibi" / "cli.py").is_file():
    sys.path.insert(0, str(repository / "src"))
    from zhibi.cli import main
    raise SystemExit(main())
else:
    raise SystemExit("Skill 缺少随包核心。请使用完整的 zhibi-skill.zip；源码使用 scripts/build_skill.py 构建。")
