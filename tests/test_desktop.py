import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ps2coop import desktop


class DesktopTest(unittest.TestCase):
    def setUp(self):
        desktop._DESKTOP_CACHE = None
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.desktop_dir = self.root / "Desktop"
        self.home.mkdir()
        self.desktop_dir.mkdir()
        self.env = patch.dict(
            os.environ,
            {
                "HOME": str(self.home),
                "PS2COOP_DESKTOP_DIR": str(self.desktop_dir),
            },
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()
        desktop._DESKTOP_CACHE = None
        self.tmp.cleanup()

    def test_exec_quoting(self):
        self.assertEqual(desktop._desktop_quote("/tmp/a b/app.py"), '"/tmp/a b/app.py"')
        self.assertEqual(desktop._desktop_quote("/tmp/100%/app.py"), '"/tmp/100%%/app.py"')
        self.assertEqual(desktop._desktop_quote('a"b'), '"a\\"b"')

    def test_create_shortcut(self):
        game = self.root / "Jogo com espaço"
        game.mkdir()
        result = desktop.create(game, "Jogo: teste")
        paths = [Path(path) for path in result["paths"]]
        if desktop.IS_WINDOWS:
            self.assertTrue(any(path.suffix == ".lnk" for path in paths))
            self.assertTrue(desktop.existing(game, "Jogo: teste"))
            desktop.remove("Jogo: teste")
            self.assertFalse(desktop.existing(game, "Jogo: teste"))
            return
        self.assertTrue(any(path.suffix == ".desktop" for path in paths))
        desktop_file = next(path for path in paths if "Desktop" in str(path) or path.parent == self.desktop_dir)
        text = desktop_file.read_text(encoding="utf-8")
        self.assertIn("PS2 Co-op", text)
        self.assertIn("Name=Jogo", text)
        self.assertIn(f'Path={game}', text)
        self.assertIn("--game", text)
        self.assertIn(f'--game "{game}"', text)  # pasta com espaços citada
        self.assertTrue(desktop.existing(game, "Jogo: teste"))
        desktop.remove("Jogo: teste")
        self.assertFalse(desktop.existing(game, "Jogo: teste"))

    def test_safe_title(self):
        self.assertEqual(desktop.safe_title("  foo\nbar  "), "foo bar")
        if desktop.IS_WINDOWS:
            self.assertEqual(desktop.safe_title('a:b?c*'), "a b c")

    def test_appimage_is_the_persistent_shortcut_target(self):
        appimage = self.root / "Jogo" / "PS2Coop-x86_64.AppImage"
        appimage.parent.mkdir()
        appimage.write_bytes(b"appimage")
        with patch.object(desktop.sys, "frozen", True, create=True), patch.dict(
            os.environ, {"APPIMAGE": str(appimage)}
        ):
            target, prefix = desktop._launch_target()
        self.assertEqual(target, appimage.resolve())
        self.assertEqual(prefix, [])


if __name__ == "__main__":
    unittest.main()
