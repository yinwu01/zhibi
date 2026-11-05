import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from zhibi.browser_workspace import create
from zhibi.models import InputError


class WorkspaceTests(unittest.TestCase):
    def test_fresh_workspace_has_explicit_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "new"
            result = create(SimpleNamespace(browser_binary=sys.executable, local_port=10818, out=str(out)))
            prefs = json.loads((out / "profile/Default/Preferences").read_text())
            self.assertEqual(set(prefs["profile"]["default_content_setting_values"].values()), {2})
            self.assertFalse(result["runtime_verified"])
            compile((out / "start-browser.py").read_text(), "start-browser.py", "exec")
            self.assertFalse((out / "profile/Default/Cookies").exists())
            with self.assertRaises(InputError):
                create(SimpleNamespace(browser_binary=sys.executable, local_port=10818, out=str(out)))
