import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from zhibi.service import deployment
from zhibi.remote import unit
from zhibi.models import InputError


@unittest.skipUnless(os.name == "posix", "POSIX shell transaction harness; Linux service adapter")
class ServiceTransactionTests(unittest.TestCase):
    def execute_transaction(self, fail=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            units = root / "units"
            units.mkdir()
            original = units / "demo.service"
            original.write_text("original unit\n")
            binpath = root / "bin"
            binpath.mkdir()
            systemctl = binpath / "systemctl"
            systemctl.write_text('''#!/bin/sh
case "$1" in
show) echo "$UNIT_PATH";;
is-enabled) echo enabled;;
is-active) if [ "$2" = --quiet ]; then exit "$FAIL_START"; else echo active; fi;;
esac
''')
            systemctl.chmod(0o700)
            for name in ("systemd-analyze", "sleep"):
                script = binpath / name
                script.write_text("#!/bin/sh\nexit 0\n")
                script.chmod(0o700)
            transaction = deployment("demo", "new unit\n")
            # Decode/rebuild embedded rollback paths as well as the outer script.
            import base64
            script = transaction["script"]
            for token in script.split():
                try:
                    decoded = base64.b64decode(token, validate=True).decode()
                except (ValueError, UnicodeDecodeError):
                    continue
                if decoded.startswith("#!/bin/sh"):
                    decoded = decoded.replace("/etc/systemd/system", str(units))
                    script = script.replace(token, base64.b64encode(decoded.encode()).decode())
            script = script.replace("/etc/systemd/system", str(units)).replace("/var/lib/zhibi/deployments", str(root / "receipts"))
            env = dict(os.environ, PATH=str(binpath) + ":" + os.environ["PATH"], UNIT_PATH=str(original), FAIL_START=str(int(fail)))
            result = subprocess.run(["sh", "-c", script], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, int(fail), result.stderr)
            self.assertEqual(original.read_text(), "original unit\n" if fail else "new unit\n")
            receipt = next((root / "receipts").iterdir())
            self.assertEqual((receipt / "previous.service").read_text(), "original unit\n")
            if not fail:
                subprocess.run(["sh", str(receipt / "rollback.sh")], env=env, check=True, capture_output=True)
                self.assertEqual(original.read_text(), "original unit\n")

    def test_deploy_and_explicit_restore(self):
        self.execute_transaction()

    def test_failed_start_restores_previous_service(self):
        self.execute_transaction(fail=True)

    def test_unit_rejects_field_injection(self):
        with self.assertRaises(InputError):
            unit("demo", "/bin/true", workdir="/tmp\nExecStart=/bad")
