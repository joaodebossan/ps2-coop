import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from ps2coop.app import Handler, PortalServer


class DummyState:
    token = "test-token"
    profile = {"players": 2, "host_local": False}
    game_dir = Path("/tmp")

    def status(self):
        return {"ok": True, "game": {"title": "Teste"}, "setup": {}}

    def save(self):
        pass

    def set_players(self, players, host_local):
        self.profile["players"] = players
        self.profile["host_local"] = host_local
        return {"players": players, "host_local": host_local}

    def players(self):
        return int(self.profile.get("players", 2))

    def host_local(self):
        return bool(self.profile.get("host_local", False))


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = PortalServer(("127.0.0.1", 0), Handler)
        Handler.state = DummyState()
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        data = response.read()
        headers = dict(response.getheaders())
        conn.close()
        return response.status, data, headers

    def test_status_requires_local_host(self):
        status, _, _ = self.request("GET", "/api/status")
        self.assertEqual(status, 200)
        status, _, _ = self.request("GET", "/api/status", headers={"Host": "evil.test"})
        self.assertEqual(status, 403)

    def test_index_has_token_and_csp(self):
        status, data, headers = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"test-token", data)
        self.assertIn("Content-Security-Policy", headers)

    def test_mutation_requires_token_and_same_origin(self):
        status, _, _ = self.request(
            "POST",
            "/api/game/players",
            body=json.dumps({"players": 2}),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 403)
        status, _, _ = self.request(
            "POST",
            "/api/game/players",
            body=json.dumps({"players": 3}),
            headers={
                "Content-Type": "application/json",
                "X-PS2Coop-Token": "test-token",
                "Origin": "https://evil.test",
            },
        )
        self.assertEqual(status, 403)
        status, data, _ = self.request(
            "POST",
            "/api/game/players",
            body=json.dumps({"players": 3, "host_local": True}),
            headers={
                "Content-Type": "application/json",
                "X-PS2Coop-Token": "test-token",
                "Origin": f"http://127.0.0.1:{self.port}",
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(data)["ok"])

    def test_cross_site_get_blocked(self):
        status, _, _ = self.request("GET", "/api/status", headers={"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(status, 403)

    def test_traversal_blocked(self):
        status, _, _ = self.request("GET", "/../ps2coop/config.py")
        self.assertIn(status, (403, 404))


if __name__ == "__main__":
    unittest.main()
