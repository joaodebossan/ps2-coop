import hashlib
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ps2coop.downloads import Job, download, sha256


class RangeHandler(BaseHTTPRequestHandler):
    payload = b"0123456789" * 1000

    def log_message(self, *args):
        pass

    def do_GET(self):
        start = 0
        header = self.headers.get("Range", "")
        if header.startswith("bytes="):
            start = int(header.split("=", 1)[1].split("-", 1)[0] or 0)
        body = self.payload[start:]
        self.send_response(206 if start else 200)
        self.send_header("Content-Length", str(len(body)))
        if start:
            self.send_header("Content-Range", f"bytes {start}-{len(self.payload) - 1}/{len(self.payload)}")
        self.end_headers()
        self.wfile.write(body)


class DownloadsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), RangeHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}/file.bin"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_download_with_checksum(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "file.bin"
            job = Job(id="x", label="x")
            expected = hashlib.sha256(RangeHandler.payload).hexdigest()
            download(self.url, dest, job, attempts=1, expected_sha256=expected)
            self.assertEqual(dest.read_bytes(), RangeHandler.payload)
            self.assertEqual(job.progress, 1.0)

    def test_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "file.bin"
            part = dest.with_name(dest.name + ".part")
            part.write_bytes(RangeHandler.payload[:123])
            download(self.url, dest, attempts=1)
            self.assertEqual(dest.read_bytes(), RangeHandler.payload)

    def test_bad_checksum_removes_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "file.bin"
            with self.assertRaises(RuntimeError):
                download(self.url, dest, attempts=1, expected_sha256="0" * 64)
            self.assertFalse(dest.exists())

    def test_sha256(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x"
            path.write_bytes(b"abc")
            self.assertEqual(sha256(path), hashlib.sha256(b"abc").hexdigest())


if __name__ == "__main__":
    unittest.main()
