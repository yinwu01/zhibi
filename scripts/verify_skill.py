"""Rehearse the delivered Skill outside the checkout with an isolated home and no pip."""
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from build_skill import build


def verify():
    with tempfile.TemporaryDirectory(prefix="zhibi-skill-") as tmp:
        base = Path(tmp)
        package = build(base / "artifacts")
        with zipfile.ZipFile(package["skill"]) as archive:
            assert all(name.startswith("zhibi/") and ".." not in Path(name).parts for name in archive.namelist())
            archive.extractall(base / "installed")
        skill = base / "installed" / "zhibi"
        entry = skill / "scripts" / "zhibi.py"
        environment = dict(os.environ)
        for key in list(environment):
            if key in {"PYTHONPATH", "PYTHONHOME"} or key.startswith("ZHIBI_"):
                environment.pop(key)
        home = base / "home"
        home.mkdir()
        bootstrap = "import pathlib,runpy,sys; user_dir=pathlib.Path(sys.argv[1]); pathlib.Path.home=classmethod(lambda cls:user_dir); sys.argv=sys.argv[2:]; runpy.run_path(sys.argv[0],run_name='__main__')"
        def run(*args):
            result = subprocess.run([sys.executable, "-I", "-c", bootstrap, str(home), str(entry), *map(str, args)], cwd=base,
                                    env=environment, capture_output=True, text=True, encoding="utf-8", timeout=30)
            assert result.returncode == 0, result.stderr
            return json.loads(result.stdout)
        connection = run("connect", "--host", "example.com")
        assert connection["browser_proxy"]["host"] == "127.0.0.1"
        assert connection["applied"] is False
        exported_connection = run("connect", "--host", "example.com", "--export-out", base / "connection")
        assert Path(exported_connection["launcher"]).is_file()
        assert exported_connection["verified"] is False
        assert (skill / "references/runtime.md").is_file()
        assert (skill / "references/local-vm.md").is_file()
        assert (skill / "references/audit.md").is_file()
        project_dir = base / "project"; project_dir.mkdir()
        start_script = base / "start.sh"; start_script.write_text("true\n"); start_script.chmod(0o600)
        common = ["--project", project_dir, "--state-dir", base / "bindings"]
        run("project", "bind", *common, "--host", "example.com", "--workdir", "/srv/project", "--command-file", start_script)
        assert run("project", "status", *common)["backend"] == "remote"
        assert not run("project", "audit", *common)["attempted"]
        assert run("doctor")["runtime_dependencies"] == []
        assert "scan" in run("capabilities")["commands"]
        assert all(not p["configured"] for p in run("providers")["providers"])
        reputation = run("scan", "--network", "--reputation", "--dry-run")
        assert reputation["providers"] == ["ipwhois", "proxycheck", "ipquery", "stopforumspam"]
        assert all(not s.get("requires_key") for s in reputation["external_services"])
        offline = run("scan", "--out", base / "offline")
        assert offline["summary"]["contacted_services"] == []
        dns = run("dns", "--out", base / "dns")
        assert dns["summary"]["status"] == "skipped" and not dns["summary"]["attempted"]
        assert run("dns", "--dry-run")["context"] == "dig_default_resolver"
        for scenario in ("conflicting-sources", "missing-coverage", "provider-outage"):
            demo = run("scan-demo", "--scenario", scenario, "--out", base / scenario)
            assert demo["summary"]["sample"] is True
            assert len(demo["summary"]["providers"]) == 4
            exported = run("export", base / scenario / "report.json")
            assert "8.8.8.8" not in json.dumps(exported)
        config = base / "synthetic-ipv6-config.txt"
        config.write_text("Synthetic dedicated-environment IPv6 outbound block.\n", encoding="utf-8")
        confirmed = run("confirm-ipv6", base / "provider-outage", "--evidence", config,
                        "--configuration", "blocked", "--method", "local_config", "--reviewed",
                        "--out", base / "ipv6-confirmed")
        assert next(r for r in confirmed["summary"]["assessment"]["overview"]["table_rows"]
                    if r["label"] == "IPv6 出站策略")["result"] == "通过"
        run("browser", "--advanced", "--out", base / "probe.html")
        page = (base / "probe.html").read_text()
        assert "probeBrowserExit" in page and "Permission is hereby granted" in page
        assert 'schema_version:"4"' in page and 'id="detail-fonts"' in page and "ZhibiDetails.collect" in page
        assert "ZhibiExtras.collect" in page and 'id="extra-dns"' in page
        assert len(run("modules")) >= 13
        suite = run("suite", "--preset", "custom", "--module", "browser-extras", "--out", base / "suite")
        assert suite["summary"]["recipients"] == [] and not suite["summary"]["environment_modified"]
        assert suite["summary"]["modules"]["browser-extras"]["status"] == "blocked_dependency"
        run("suite-share", base / "suite", "--out", base / "share")
        assert "ZHIBI_NETWORK_MODULE" not in page
        assert (skill / "licenses/CCBaga-MIT.txt").is_file()
        assert (skill / "licenses/CheckCC-MIT.txt").is_file()
        for path in skill.rglob("*.md"):
            content = path.read_text(encoding="utf-8")
            assert str(Path(__file__).resolve().parents[1]) not in content
            for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", content):
                if "://" not in link and not link.startswith("#"):
                    assert (path.parent / link.split("#")[0]).is_file(), (path.name, link)
        return {"result": "passed", "scenarios": ["isolated_install", "connection_plan", "offline_scan", "provider_catalog", "keyless_reputation_plan", "conflicting_sources",
                "missing_coverage", "provider_outage", "summary_export", "scoped_ipv6_confirmation", "advanced_browser_v4", "optional_suite", "redacted_suite_share", "dns_offline_and_plan", "third_party_licenses"],
                "python": sys.version.split()[0], "host_natural_language_selection": "not_tested"}


if __name__ == "__main__":
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
