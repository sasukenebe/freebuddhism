#!/usr/bin/env python3
"""Serve the private Candana review on loopback with explicit UTF-8 text headers."""

from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MARKER = {"kind": "candana-private-review", "automatic_publication": False}


class ReviewHandler(SimpleHTTPRequestHandler):
    def guess_type(self, path):
        mime = super().guess_type(path)
        if mime.startswith("text/") or mime == "application/json":
            mime += "; charset=utf-8"
        return mime

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()


def review_directory(directory: Path, root: Path = ROOT) -> Path:
    directory = directory.absolute()
    relative = directory.relative_to(root.absolute())
    if len(relative.parts) < 2 or relative.parts[0] != "build" or ".." in relative.parts:
        raise ValueError("Only a marked private review directory below build/ can be served")
    if any(path.is_symlink() for path in (directory, *directory.parents)):
        raise ValueError("Private review paths must not contain symlinks")
    marker = directory / ".candana-private-review.json"
    if marker.is_symlink() or json.loads(marker.read_text(encoding="utf-8")) != MARKER:
        raise ValueError("Missing or incorrect private review marker")
    return directory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--directory", type=Path, default=ROOT / "build/candana-batch-review")
    args = parser.parse_args()
    directory = review_directory(args.directory)
    handler = partial(ReviewHandler, directory=str(directory))
    with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
        print(f"Private Candana review: http://127.0.0.1:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
