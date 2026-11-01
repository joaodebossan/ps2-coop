import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from ps2coop import config
from ps2coop.app import AppState
from ps2coop.gamepads import Gamepad


def wait_job(job, timeout=5):
    deadline = time.time() + timeout
    while job.running and time.time() < deadline:
        time.sleep(0.02)
    return job


class AppStateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.game = Path(self.tmp.name)
        (self.game / "Jogo (USA).iso").write_bytes(b"fake")
        self.desktop = self.game / "desktop-test"
        self.desktop.mkdir(exist_ok=True)
        self.env = patch.dict(
            os.environ,
            {
                "PS2COOP_AUTOSETUP": "0",
                "PS2COOP_NO_SHORTCUT": "1",
                "PS2COOP_DESKTOP_DIR": str(self.desktop),
            },
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def state(self):
        return AppState(self.game, auto_setup=False)

    def test_profile_defaults_and_status(self):
        state = self.state()
        self.assertEqual(state.title(), "Jogo")
        self.assertEqual(state.players(), 2)
        status = state.status()
        self.assertTrue(status["ok"])
        self.assertEqual(status["game"]["image"], "Jogo (USA).iso")
        self.assertIn("session", status)
        self.assertIn("setup", status)

    def test_auto_setup_blocked_without_bios(self):
        state = self.state()
        with patch.object(config, "AUTO_SETUP", True), patch.object(
            state, "maybe_shortcut"
        ), patch("ps2coop.app.pcsx2.installed", return_value=True), patch(
            "ps2coop.app.pcsx2.bios_ok", return_value=False
        ), patch("ps2coop.app.pcsx2.find_and_adopt_bios", return_value=""), patch(
            "ps2coop.app.moonlight.installed", return_value=True
        ), patch("ps2coop.app.moonlight.can_host", return_value=True):
            state.auto_setup_enabled = True
            job = state.start_auto_setup(force=True)
            wait_job(job)
        self.assertEqual(job.status, "blocked")
        self.assertIn("BIOS", job.message)

    def test_auto_setup_success_configures(self):
        state = self.state()
        with patch.object(state, "maybe_shortcut") as shortcut, patch(
            "ps2coop.app.pcsx2.installed", return_value=True
        ), patch("ps2coop.app.pcsx2.bios_ok", return_value=True), patch(
            "ps2coop.app.pcsx2.configure"
        ) as configure, patch(
            "ps2coop.app.moonlight.installed", return_value=True
        ), patch("ps2coop.app.moonlight.can_host", return_value=True), patch(
            "ps2coop.app.gamepads.detect_gamepads", return_value=[Gamepad(0, "DualSense")]
        ):
            job = state.start_auto_setup(force=True)
            wait_job(job)
        self.assertEqual(job.status, "done")
        configure.assert_called_once()
        shortcut.assert_called()
        self.assertTrue(state.profile.get("auto_setup_completed"))

    def test_start_game_requires_connected_guests(self):
        state = self.state()
        with patch("ps2coop.app.pcsx2.installed", return_value=True), patch(
            "ps2coop.app.pcsx2.bios_ok", return_value=True
        ), patch("ps2coop.app.pcsx2.running", return_value=False), patch(
            "ps2coop.app.moonlight.running", return_value=True
        ), patch("ps2coop.app.moonlight.get_invites", return_value=[]), patch(
            "ps2coop.app.pcsx2.start"
        ) as start:
            with self.assertRaises(RuntimeError):
                state.start_game(force=False)
        start.assert_not_called()

    def test_start_game_force(self):
        state = self.state()
        pads = [Gamepad(0, "Controle virtual", True)]
        with patch("ps2coop.app.pcsx2.installed", return_value=True), patch(
            "ps2coop.app.pcsx2.bios_ok", return_value=True
        ), patch("ps2coop.app.pcsx2.running", return_value=False), patch(
            "ps2coop.app.moonlight.running", return_value=True
        ), patch("ps2coop.app.moonlight.get_invites", return_value=[]), patch(
            "ps2coop.app.gamepads.detect_gamepads", return_value=pads
        ), patch("ps2coop.app.gamepads.count_gamepads", return_value=(1, 0, ["v"], [])), patch(
            "ps2coop.app.pcsx2.start", return_value=123
        ) as start, patch.object(state, "maybe_shortcut"):
            result = state.start_game(force=True)
        self.assertEqual(result["pid"], 123)
        start.assert_called_once()

    def test_four_players_requires_host_local(self):
        state = self.state()
        with patch("ps2coop.app.moonlight.running", return_value=False):
            with self.assertRaises(RuntimeError):
                state.set_players(4, False)
            state.set_players(4, True)
        self.assertEqual(state.players(), 4)
        self.assertEqual(state.remote_players(), 3)

    def test_maybe_shortcut_profile(self):
        state = self.state()
        state.auto_setup_enabled = False
        with patch.dict(os.environ, {"PS2COOP_NO_SHORTCUT": "0"}), patch(
            "ps2coop.app.desktop.create", return_value={"ok": True, "paths": []}
        ) as create, patch("ps2coop.app.desktop.existing", return_value=False):
            state.maybe_shortcut(force=True)
        create.assert_called_once()
        self.assertTrue(state.profile.get("shortcut"))
        self.assertEqual(state.profile.get("shortcut_title"), "Jogo")


if __name__ == "__main__":
    unittest.main()
