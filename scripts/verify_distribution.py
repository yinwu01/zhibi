"""Install the built wheel into a fresh environment and exercise packaged resources."""
import json
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path
from zhibi import __version__

root = Path(__file__).resolve().parents[1]
wheel = next((root / "dist").glob("zhibi-" + __version__ + "-*.whl"))
with tempfile.TemporaryDirectory(prefix="zhibi-wheel-") as tmp:
    directory = Path(tmp).resolve()
    environment = directory / "env"
    venv.EnvBuilder(with_pip=True).create(environment)
    binary = environment / ("Scripts" if os.name == "nt" else "bin")
    python = binary / ("python.exe" if os.name == "nt" else "python")
    command = binary / ("zhibi.exe" if os.name == "nt" else "zhibi")
    clean_env = dict(os.environ)
    clean_env.pop("PYTHONPATH", None)
    clean_env.pop("PYTHONHOME", None)
    for key in list(clean_env):
        if key.startswith("ZHIBI_"):
            clean_env.pop(key)
    def run(args):
        return subprocess.run(args, check=True, cwd=tmp, env=clean_env, capture_output=True, text=True, encoding="utf-8")
    run([str(python), "-m", "pip", "install", "--no-deps", "--no-index", str(wheel)])
    cap = json.loads(run([str(command), "capabilities"]).stdout)
    assert cap["version"] == __version__
    connection = json.loads(run([str(command), "connect", "--host", "example.com"]).stdout)
    assert connection["browser_proxy"]["type"] == "socks5" and not connection["applied"]
    process = json.loads(run([str(command), "process-workspace", "--workdir", str(directory),
                              "--out", str(directory / "process")]).stdout)
    assert Path(process["runner"]).is_file()
    if os.name != 'nt':
        entry = json.loads(run([str(command), "process-entry", "--workspace", process["directory"],
                                "--name", "demo", "--program", "/usr/bin/true"]).stdout)
        assert Path(entry["entry"]).is_file()
    run([str(command), "demo", "--out", str(directory / "demo")])
    run([str(command), "browser", "--out", str(directory / "browser.html")])
    run([str(command), "browser", "--advanced", "--out", str(directory / "advanced.html")])
    scan = json.loads(run([str(command), "scan", "--out", str(directory / "offline")]).stdout)
    assert scan["summary"]["contacted_services"] == []
    assert len(json.loads(run([str(command), "modules"]).stdout)) >= 13
    suite = json.loads(run([str(command), "suite", "--preset", "custom", "--module", "browser-extras", "--out", str(directory / "suite")]).stdout)
    assert suite["summary"]["recipients"] == [] and not suite["summary"]["environment_modified"]
    run([str(command), "suite-share", str(directory / "suite"), "--out", str(directory / "share")])
    demo = json.loads(run([str(command), "scan-demo", "--out", str(directory / "intel")]).stdout)
    assert demo["summary"]["sample"] and len(demo["summary"]["providers"]) == 4
    run([str(command), "export", str(directory / "intel/report.json")])
    dns = json.loads(run([str(command), "dns", "--out", str(directory / "dns")]).stdout)
    assert dns["summary"]["status"] == "skipped"
    assert "Permission is hereby granted" in (directory / "advanced.html").read_text(encoding="utf-8")
    run([str(command), "explain", "network.route"])
    for args in (["theory", "--format", "json"], ["learn"], ["lab", "repair"],
                 ["guide"], ["triage", "--channel", "web", "--signal", "http_403"]):
        run([str(command)] + args)
    run([str(command), "learn", "--format", "html", "--out", str(directory / "learning.html")])
    run([str(command), "export", str(directory / "demo/report.json")])
    assert (directory / "demo/report.html").exists()
    assert "开始检查" in (directory / "browser.html").read_text(encoding="utf-8")
print("Fresh wheel install passed: commands, knowledge, offline scan, multi-provider demo, advanced browser/licenses, DNS offline, reports and summaries.")
