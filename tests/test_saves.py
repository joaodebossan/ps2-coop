import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ps2coop import pcsx2, saves


class SavesTest(unittest.TestCase):
    def test_backup_and_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp)
            memcards = pcsx2.memcards_dir(game)
            (memcards / "Mcd001.ps2").write_bytes(b"card1")
            (memcards / "Mcd002.ps2").write_bytes(b"card2")
            ini = pcsx2.ini_path(game)
            ini.parent.mkdir(parents=True, exist_ok=True)
            ini.write_text("[UI]\n", encoding="utf-8")

            with patch.object(pcsx2, "running", return_value=False):
                first = saves.backup(game)
                second = saves.backup(game)
            self.assertNotEqual(first["name"], second["name"])
            backups = saves.list_backups(game)
            self.assertEqual(len(backups), 2)

            (memcards / "Mcd001.ps2").write_bytes(b"changed")
            with patch.object(pcsx2, "running", return_value=False):
                result = saves.restore(game, first["name"])
            self.assertEqual(result["files"], 2)
            self.assertEqual((memcards / "Mcd001.ps2").read_bytes(), b"card1")

    def test_backup_while_running_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(pcsx2, "running", return_value=True):
                with self.assertRaises(RuntimeError):
                    saves.backup(Path(tmp))

    def test_restore_invalid_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                saves.restore(Path(tmp), "../../etc")


if __name__ == "__main__":
    unittest.main()
