# Setup

`zhibi-skill.zip` contains the whole Skill and a stdlib-only Python core.
Unzip the complete `zhibi` folder into `~/.agents/skills/` (Codex desktop) or the skills directory your host uses, preserving `scripts/`, `assets/` and `references/`.
Select the skill in Codex (or type `$zhibi`); use `/zhibi` in 目标客户端. Restart the host if it is not discovered.
Current private releases require a GitHub account with repository access. A 404 is not a Python or Skill error.
Python 3.9+ is required. No pip, virtual environment or account login is required at runtime.

Invoke `python3 <skill>/scripts/zhibi.py doctor`. On Windows use `py -3` or the known Python executable.
Use absolute paths; do not assume shell activation carries across agent calls.

If Python is missing, report that prerequisite. If the entrypoint reports a missing core, the user copied only
the source Skill folder: use the full release, or build from the repository with `python3 scripts/build_skill.py`.
The repository's Skill entrypoint can run directly against `src/`.

Commands work from any working directory. Outputs default to a fresh private directory under `~/.zhibi/`.
`--out` must not exist. The Skill never installs upstream projects at runtime.
For standalone use, `python3 zhibi-core.pyz --help` exposes the same commands.
Basic `start.html` still works without Python; advanced intelligence and key management require the bundled core.
