import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ps2coop import config


class ConfigTest(unittest.TestCase):
    def test_profile_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self.assertEqual(config.load_profile(folder), {})
            config.save_profile(folder, {"players": 3, "title": "Jogo"})
            self.assertEqual(config.load_profile(folder)["players"], 3)
            self.assertTrue((folder / ".ps2coop" / "profile.json").is_file())

    def test_game_dir_from_argv(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(config.game_dir_from_argv(["--game", tmp]), Path(tmp).resolve())
            self.assertEqual(config.game_dir_from_argv([f"--game={tmp}"]), Path(tmp).resolve())
            with patch("ps2coop.config.Path.cwd", return_value=Path(tmp)):
                self.assertEqual(config.game_dir_from_argv([]), Path(tmp).resolve())

    def test_tools_root_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"PS2COOP_HOME": tmp}):
                self.assertEqual(config.tools_root(), Path(tmp).resolve())
                self.assertEqual(config.downloads_root(), Path(tmp).resolve() / "downloads")
                self.assertTrue((Path(tmp) / "downloads").is_dir())

    def test_platform(self):
        self.assertIn(config.platform_label(), {"windows", "linux", "macos"})
        self.assertTrue(config.platform_name())


if __name__ == "__main__":
    unittest.main()
