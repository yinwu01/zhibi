"""Build and install the complete Skill to an explicitly chosen directory."""
import argparse
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

from build_skill import build


def host_destination(host):
    folder = ".agents" if host == "codex" else ".other-agent"
    return Path.home() / folder / "skills" / "zhibi"


def install(destination):
    destination = Path(destination).expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError("目标已存在。请先保留旧版本，再选择新的目录；不会覆盖已有 Skill。")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".zhibi-install-", dir=destination.parent) as tmp:
        temporary = Path(tmp)
        result = build(temporary / "build")
        with zipfile.ZipFile(result["skill"]) as archive:
            # This archive was built from the allowlisted repository files immediately above.
            archive.extractall(temporary / "unpacked")
        source = temporary / "unpacked" / "zhibi"
        if not (source / "scripts" / "zhibi.py").is_file() or not (source / "assets" / "zhibi-core.pyz").is_file():
            raise ValueError("Skill 构建不完整，未安装。")
        if destination.exists() or destination.is_symlink():
            raise ValueError("目标已被创建，未覆盖。")
        os.rename(source, destination)
    return destination


def main():
    parser = argparse.ArgumentParser(description="将知彼 Skill 与内置核心一起安装；无 pip，无网络。")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--host", choices=("codex",))
    group.add_argument("--dest", help="明确的 Skill 文件夹路径，例如 /path/to/skills/zhibi")
    args = parser.parse_args()
    if args.dest:
        destination = args.dest
    else:
        destination = host_destination(args.host)
    try:
        installed = install(destination)
    except (OSError, ValueError):
        parser.exit(2, "安装未完成：目标已存在、权限不足或构建不完整。未覆盖已有 Skill。\n")
    print("已安装完整知彼 Skill：" + str(installed))
    invocation = "$zhibi" if args.host == "codex" else "知彼（在宿主中按 Skill 名调用）"
    print("在宿主中选择知彼 Skill，或新开会话后输入：" + invocation + " 检查我实际使用 目标服务 的环境，用默认免 Key 方案操作浏览器完成检测，核对相关设置并打开报告。")
    print("直接验证安装：python3 \"" + str(installed / "scripts" / "zhibi.py") + "\" doctor")


if __name__ == "__main__":
    main()
