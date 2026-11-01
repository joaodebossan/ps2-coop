import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ps2coop import moonlight


class MoonlightTest(unittest.TestCase):
    def setUp(self):
        moonlight.clear_cache()

    def test_invite_from_slot(self):
        invite = moonlight._invite_from_slot(
            {"slot": 2, "state": "shared", "devices": [], "name": "Jogador 2"},
            {"url": "https://example/p/x", "pin": "123456", "reach": "lan", "available": True},
        )
        self.assertEqual(invite["slot"], 2)
        self.assertEqual(invite["pin"], "123456")
        self.assertEqual(invite["reach"], "lan")
        self.assertFalse(invite["connected"])

    def test_get_invites_create_sets_permissions_before_activate(self):
        calls = []

        def fake_request(path, method="GET", payload=None, port=None, host_header="localhost", forwarded_host="", timeout=12):
            calls.append((path, payload, forwarded_host))
            if path.endswith("/activate"):
                return {
                    "slot": 2,
                    "state": "shared",
                    "name": "Jogador 2",
                    "permissions": {"gamepad": True, "keyboardMouse": False, "hid": False},
                    "access_level": "gamer",
                    "url": "https://lan/p/abc",
                    "pin": "654321",
                    "reach": "lan",
                }
            return {"ok": True}

        slots = {"slots": [{"slot": 2, "state": "off", "devices": [], "name": "Jogador 2"}]}
        with patch.object(moonlight, "share_status", return_value=slots), patch.object(
            moonlight, "display_app_id", return_value=1
        ), patch.object(moonlight, "_request", side_effect=fake_request), patch.object(
            moonlight, "_lan_host_header", return_value="192.168.0.2:8443"
        ), patch.object(moonlight, "clear_cache"):
            invites = moonlight.get_invites(True, "lan", count=1)

        paths = [call[0] for call in calls]
        self.assertLess(paths.index("/api/share/slots/2/permissions"), paths.index("/api/share/slots/2/activate"))
        self.assertTrue(any(call[2] == "192.168.0.2:8443" for call in calls))
        self.assertEqual(invites[0]["pin"], "654321")
        self.assertEqual(invites[0]["url"], "https://lan/p/abc")

    def test_get_invites_existing_credentials(self):
        slots = {"slots": [{"slot": 2, "state": "shared", "devices": [{"user_agent": "x"}], "streaming": True, "name": "Jogador 2"}]}

        def fake_request(path, method="GET", payload=None, port=None, host_header="localhost", forwarded_host="", timeout=12):
            if path.endswith("/credentials"):
                return {"available": True, "url": "https://lan/p/abc", "pin": "111111", "reach": "lan"}
            return {"ok": True}

        with patch.object(moonlight, "share_status", return_value=slots), patch.object(
            moonlight, "_request", side_effect=fake_request
        ), patch.object(moonlight, "_lan_host_header", return_value="192.168.0.2:8443"):
            invites = moonlight.get_invites(False, count=1)
        self.assertTrue(invites[0]["connected"])
        self.assertEqual(invites[0]["pin"], "111111")

    def test_connection_info(self):
        probe = {"status": "running", "active_port": 8443, "version": "0.4.1", "http_port": 8080}
        inet = {
            "local_ip": "192.168.0.2",
            "local_ips": ["192.168.0.2"],
            "public_ip": "1.2.3.4",
            "internet_access_enabled": True,
            "rendezvous": {"online": True, "url": "https://stream.example/x"},
        }
        with patch.object(moonlight, "server_probe", return_value=probe), patch.object(
            moonlight, "internet_status", return_value=inet
        ), patch.object(moonlight, "public_link", return_value="https://stream.example/x"):
            info = moonlight.connection_info()
        self.assertEqual(info["port"], 8443)
        self.assertEqual(info["lan"], "https://192.168.0.2:8443")
        self.assertEqual(info["public"], "https://stream.example/x")
        self.assertTrue(info["running"])
        self.assertEqual(info["host_page"], "https://localhost:8443/")


if __name__ == "__main__":
    unittest.main()
