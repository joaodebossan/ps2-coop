import unittest

from ps2coop.gamepads import Gamepad, build_pad_map, pad_map_description


class GamepadsTest(unittest.TestCase):
    def test_empty_map(self):
        self.assertEqual(build_pad_map(2, False, []), {})

    def test_host_local_physical_first(self):
        pads = [
            Gamepad(0, "Controle virtual 1", True),
            Gamepad(1, "DualSense", False),
            Gamepad(2, "Controle virtual 2", True),
        ]
        self.assertEqual(build_pad_map(2, True, pads), {1: 1, 2: 0})
        self.assertEqual(build_pad_map(3, True, pads), {1: 1, 2: 0, 6: 2})

    def test_remote_virtual_first(self):
        pads = [
            Gamepad(0, "DualSense", False),
            Gamepad(1, "Controle virtual 1", True),
            Gamepad(2, "Controle virtual 2", True),
        ]
        self.assertEqual(build_pad_map(2, False, pads), {1: 1, 2: 2})
        self.assertEqual(build_pad_map(1, False, pads), {1: 1})

    def test_description(self):
        pads = [Gamepad(1, "DualSense", False)]
        result = pad_map_description(2, True, pads, {1: 1})
        self.assertEqual(result[0]["player"], 1)
        self.assertTrue(result[0]["connected"])
        self.assertFalse(result[0]["virtual"])
        self.assertFalse(result[1]["connected"])
        self.assertIsNone(result[1]["sdl"])


if __name__ == "__main__":
    unittest.main()
