from functools import partial
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/buddhist_canon_pipeline"))
from serve_candana_review import MARKER, ReviewHandler, review_directory  # noqa: E402


class PreviewTests(unittest.TestCase):
    def test_unicode_quotes_and_pali_are_served_as_utf8_without_changing_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            expected = '“The Snake”\n1. “Aṅguttara — Bhikkhu.”\n'.encode("utf-8")
            for name in ("sutta.txt", "sutta.html", "review.json"):
                (directory / name).write_bytes(expected)
            (directory / "source.pdf").write_bytes(b"%PDF-synthetic")
            handler = partial(ReviewHandler, directory=str(directory))
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                for name in ("sutta.txt", "sutta.html", "review.json"):
                    with urlopen(f"http://127.0.0.1:{server.server_port}/{name}") as response:
                        self.assertEqual(response.headers.get_content_charset(), "utf-8")
                        self.assertEqual(response.read(), expected)
                        self.assertEqual(response.headers["Cache-Control"], "no-store")
                        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
                with urlopen(f"http://127.0.0.1:{server.server_port}/source.pdf") as response:
                    self.assertEqual(response.headers.get_content_type(), "application/pdf")
                    self.assertIsNone(response.headers.get_content_charset())
                    self.assertEqual(response.read(), b"%PDF-synthetic")
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=5)

    def test_preview_requires_a_marked_private_directory_not_a_repo_or_public_site(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "build/review"
            directory.mkdir(parents=True)
            for wrong in (root, root / "build", root / "public", directory):
                with self.assertRaises((ValueError, OSError)):
                    review_directory(wrong, root)
            marker = directory / ".candana-private-review.json"
            marker.write_text(json.dumps(MARKER))
            self.assertEqual(review_directory(directory, root), directory)
            link = root / "build/linked"
            link.symlink_to(directory, target_is_directory=True)
            with self.assertRaises(ValueError):
                review_directory(link, root)
            marker.write_text('{}')
            with self.assertRaises(ValueError):
                review_directory(directory, root)


if __name__ == "__main__":
    unittest.main()
