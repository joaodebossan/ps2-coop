import tempfile
import unittest
from pathlib import Path

from ps2coop.games import (
    find_image_by_name,
    find_images,
    human_size,
    slugify,
    title_from_filename,
)


class GamesTest(unittest.TestCase):
    def test_title_from_filename(self):
        self.assertEqual(title_from_filename(Path("God of War (USA) [SCUS-97399].iso")), "God of War")
        self.assertEqual(title_from_filename(Path("Timesplitters 2.chd")), "Timesplitters 2")
        self.assertEqual(title_from_filename(Path(".iso")), ".iso")

    def test_find_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "A (USA).iso").write_bytes(b"a")
            (folder / "B.CHD").write_bytes(b"b")
            (folder / "readme.txt").write_text("x")
            (folder / "sub").mkdir()
            images = find_images(folder)
            self.assertEqual([item.name for item in images], ["A (USA).iso", "B.CHD"])
            self.assertIsNotNone(find_image_by_name(folder, "B.CHD"))
            self.assertIsNone(find_image_by_name(folder, "missing.iso"))

    def test_slug_and_size(self):
        self.assertEqual(slugify("Gran Turismo 4 (USA)"), "gran-turismo-4-usa")
        self.assertEqual(slugify("!!!"), "ps2-game")
        self.assertEqual(human_size(0), "0 B")
        self.assertIn("MB", human_size(5 * 1024 * 1024))
        self.assertIn("GB", human_size(5 * 1024 * 1024 * 1024))


if __name__ == "__main__":
    unittest.main()
