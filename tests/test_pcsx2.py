import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ps2coop import pcsx2
from ps2coop.gamepads import Gamepad

SAMPLE_INI = """[UI]
SetupWizardIncomplete = true
StartFullscreen = false

[Folders]
Bios = bios

[Filenames]
BIOS =

[InputSources]
Keyboard = true
SDL = false

[Pad]
MultitapPort1 = false
MultitapPort2 = false

[Pad1]
Type = DualShock2
Up = Keyboard/Up

[Pad2]
Type = None

[Pad3]
Type = None

[Pad4]
Type = None

[Pad5]
Type = None

[Pad6]
Type = None

[Pad7]
Type = None

[Pad8]
Type = None
"""


class Pcsx2IniTest(unittest.TestCase):
    def test_set_value_does_not_cross_sections(self):
        text = pcsx2._set_value(SAMPLE_INI, "Filenames", "BIOS", "SCPH-90001.ROM0")
        self.assertIn("BIOS = SCPH-90001.ROM0", text)
        self.assertEqual(pcsx2._get_value(text, "Filenames", "BIOS"), "SCPH-90001.ROM0")
        self.assertEqual(pcsx2._get_value(text, "UI", "StartFullscreen"), "false")

    def test_apply_pads_two_players(self):
        text = pcsx2.apply_pads_to_text(SAMPLE_INI, 2, {1: 0, 2: 1})
        self.assertIn("MultitapPort2 = false", text)
        self.assertIn("Up = SDL-0/DPadUp", text)
        self.assertIn("Cross = SDL-1/FaceSouth", text)
        self.assertIn("[Pad3]\nType = None", text)
        self.assertNotIn("Keyboard/Up", text)

    def test_apply_pads_four_players_uses_multitap(self):
        text = pcsx2.apply_pads_to_text(SAMPLE_INI, 4, {1: 0, 2: 1, 6: 2, 7: 3})
        self.assertIn("MultitapPort2 = true", text)
        self.assertIn("[Pad6]\nType = DualShock2", text)
        self.assertIn("Up = SDL-2/DPadUp", text)
        self.assertIn("[Pad7]\nType = DualShock2", text)
        self.assertIn("Up = SDL-3/DPadUp", text)

    def test_pad_map(self):
        pads = [
            Gamepad(0, "Controle virtual", True),
            Gamepad(1, "DualSense", False),
            Gamepad(2, "Controle virtual 2", True),
        ]
        from ps2coop.gamepads import build_pad_map

        self.assertEqual(build_pad_map(2, True, pads), {1: 1, 2: 0})
        self.assertEqual(build_pad_map(2, False, pads), {1: 0, 2: 2})
        self.assertEqual(build_pad_map(3, True, pads), {1: 1, 2: 0, 6: 2})

    def test_apply_pads_missing_control_disables_slot(self):
        text = pcsx2.apply_pads_to_text(SAMPLE_INI, 2, {1: 0})
        self.assertIn("Up = SDL-0/DPadUp", text)
        self.assertIn("[Pad2]\nType = None", text)

    def test_configure_sets_ui_and_bios(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            ini = pcsx2.ini_path(folder)
            ini.parent.mkdir(parents=True)
            ini.write_text(SAMPLE_INI, encoding="utf-8")
            with patch.object(pcsx2, "bios_ok", return_value=True):
                pcsx2.configure(folder, 2, {1: 0, 2: 1})
            text = ini.read_text(encoding="utf-8")
            self.assertIn("SetupWizardIncomplete = false", text)
            self.assertIn("StartFullscreen = true", text)
            self.assertIn("ConfirmShutdown = false", text)
            self.assertIn("Slot1_Enable = true", text)

    def test_bios_name_and_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "bios"
            source.mkdir()
            (source / "SCPH-90001.ROM0").write_bytes(b"\0" * (1024 * 1024))
            self.assertEqual(pcsx2._bios_name_from_dir(source), "SCPH-90001.ROM0")
            self.assertTrue(pcsx2._has_bios_files(source))

            game = folder / "game"
            game.mkdir()
            ini = pcsx2.ini_path(game)
            ini.parent.mkdir(parents=True)
            ini.write_text(SAMPLE_INI, encoding="utf-8")
            name = pcsx2.adopt_bios(game, source)
            self.assertEqual(name, "SCPH-90001.ROM0")
            self.assertTrue((pcsx2.bios_dir(game) / name).is_file())
            self.assertTrue(pcsx2.bios_ok(game))
            self.assertEqual(pcsx2.bios_name(game), "SCPH-90001.ROM0")

    def test_save_bios_file_validation(self):
        self.assertRaises(RuntimeError, pcsx2.save_bios_file, Path("/tmp"), "bios.txt", b"x" * (1024 * 1024))


if __name__ == "__main__":
    unittest.main()
