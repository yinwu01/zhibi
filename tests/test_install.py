"""Installation into host locations must leave existing skills untouched."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from install_skill import host_destination, install


class InstallTests(unittest.TestCase):
    def test_host_paths_and_existing_install_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(Path, "home", return_value=Path(tmp)):
            self.assertEqual(host_destination("codex"), Path(tmp) / ".agents/skills/zhibi")
            self.assertEqual(host_destination("claude"), Path(tmp) / ".claude/skills/zhibi")
            dest = host_destination("codex")
            dest.mkdir(parents=True)
            sentinel = dest / "SKILL.md"
            sentinel.write_text("User's existing skill")
            with self.assertRaises(ValueError):
                install(dest)
            self.assertEqual(sentinel.read_text(), "User's existing skill")


if __name__ == "__main__":
    unittest.main()
