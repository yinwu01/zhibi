import os
import shlex
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zhibi import connect
from zhibi.models import InputError


def options(**kwargs):
    values = dict(host="example.com", user="worker", port=22, identity=None,
                  local_port=10818, command_file=None, workdir=None, interactive=False, apply=False)
    values.update(kwargs)
    return SimpleNamespace(**values)


class ConnectTests(unittest.TestCase):
    def test_tunnel_is_loopback_and_fails_if_port_taken(self):
        command = connect.argv(options())
        self.assertIn("127.0.0.1:10818", command)
        self.assertIn("ExitOnForwardFailure=yes", command)
        self.assertEqual(command[-3:], ["-N", "--", "worker@example.com"])

    def test_dry_run_never_starts_ssh(self):
        with patch("zhibi.connect.foreground", side_effect=AssertionError("started")):
            result = connect.run(options())
        self.assertFalse(result["applied"])

    def test_command_is_shell_quoted_and_not_exposed_in_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "command"
            script.write_text("printf '%s' 'secret text' | cat\n")
            script.chmod(0o600)
            args = options(command_file=str(script), workdir="/tmp/a b", interactive=True)
            command = connect.argv(args)
            parsed = shlex.split(command[-1])
            self.assertEqual(parsed[:2], ["sh", "-lc"])
            self.assertIn("cd -- '/tmp/a b'", parsed[2])
            self.assertIn(script.read_text(), parsed[2])
            self.assertIn("-tt", command)
            self.assertNotIn("secret text", str(connect.run(args)))

    def test_exit_failure_not_reported_as_success(self):
        with patch("zhibi.connect.foreground", return_value=255):
            result = connect.run(options(apply=True))
        self.assertEqual(result["exit_status"], 255)

    def test_invalid_port(self):
        with self.assertRaises(InputError):
            connect.argv(options(local_port=0))

    def test_explicit_private_ssh_config_is_used_for_proxy_connections(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "ssh.config"
            config.write_text("Host example.com\n  ProxyJump jump.example.com\n")
            config.chmod(0o600)
            command = connect.argv(options(ssh_config=str(config)))
            self.assertEqual(command[command.index("-F") + 1], str(config))
            if os.name == "posix":
                config.chmod(0o644)
                with self.assertRaises(InputError):
                    connect.argv(options(ssh_config=str(config)))


class RouteCheckTests(unittest.TestCase):
    def test_network_opt_in(self):
        with patch("zhibi.diagnostics.route", side_effect=AssertionError("network")):
            result = connect.verify_route(SimpleNamespace(local_port=10818, expected_ip=None, network=False))
        self.assertFalse(result["attempted"])

    def test_uses_remote_dns_and_expected_exit(self):
        with patch("zhibi.diagnostics.route", return_value={"status": "review"}) as route:
            result = connect.verify_route(SimpleNamespace(local_port=10818, expected_ip="8.8.8.8", network=True))
        self.assertEqual(result["status"], "review")
        self.assertEqual(route.call_args.args[0], {"proxy_url": "socks5h://127.0.0.1:10818", "expected_ip": "8.8.8.8"})


class ConnectionBundleTests(unittest.TestCase):
    def test_standalone_launcher_and_private_profile(self):
        import json
        import subprocess
        import sys
        from zhibi.connection_bundle import export
        with tempfile.TemporaryDirectory() as tmp:
            args = options(export_out=str(Path(tmp) / "bundle"))
            result = export(args, [sys.executable, "-c", "raise SystemExit(7)"])
            folder = Path(result["directory"])
            profile = json.loads((folder / "browser.json").read_text())
            self.assertFalse(profile["verified"])
            self.assertEqual(profile["protocol"], "socks5")
            done = subprocess.run([sys.executable, "-I", str(folder / "start.py")], cwd=tmp, capture_output=True)
            self.assertEqual(done.returncode, 7)
            if os.name == "posix":
                self.assertEqual((folder / "connection.private.json").stat().st_mode & 0o777, 0o600)

    def test_export_does_not_connect_or_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp, patch("zhibi.connect.foreground", side_effect=AssertionError("connected")):
            args = options(export_out=str(Path(tmp) / "bundle"))
            self.assertFalse(connect.run(args)["applied"])
            with self.assertRaises(InputError):
                connect.run(args)
