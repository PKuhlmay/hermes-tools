#!/usr/bin/env python3
"""Serve token-protected morning briefing HTML pages."""

from __future__ import annotations

import html
import json
import os
import re
import tempfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

DATA_DIR = Path(os.environ.get("BRIEFING_DATA_DIR", "/data"))
PORT = int(os.environ.get("PORT", "8080"))
MAX_BODY_BYTES = 512 * 1024
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")


def write_atomic(path: Path, content: str) -> None:
    """Write a UTF-8 file atomically to avoid partial responses."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(content)
        temporary_path = Path(handle.name)
    temporary_path.replace(path)


class BriefingHandler(BaseHTTPRequestHandler):
    server_version = "BriefingWeb/1.0"

    def log_message(self, _format: str, *_args: object) -> None:
        """Avoid writing bearer-style URLs to container logs."""
        print(f"{self.command} {self.path.split('/', 2)[1] if '/' in self.path else ''} {self.response_code}")

    def send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.response_code = status.value
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not getattr(self, "_head_only", False):
            self.wfile.write(body)

    def do_HEAD(self) -> None:  # noqa: N802
        """Return the same headers as GET without a response body."""
        self._head_only = True
        try:
            self.do_GET()
        finally:
            del self._head_only

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/health":
            self.send_json(HTTPStatus.OK, {"status": "ok"})
            return

        match = re.fullmatch(r"/brief/([A-Za-z0-9_-]{32,128})", path)
        if not match:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return

        page = DATA_DIR / f"{match.group(1)}.html"
        if not page.is_file():
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "briefing not found"})
            return

        body = page.read_bytes()
        self.response_code = HTTPStatus.OK.value
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "private, no-store, max-age=0")
        self.send_header("X-Robots-Tag", "noindex, nofollow, noarchive")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        if not getattr(self, "_head_only", False):
            self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        match = re.fullmatch(r"/api/publish/([A-Za-z0-9_-]{32,128})", path)
        if not match:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid content length"})
            return
        if not 1 <= length <= MAX_BODY_BYTES:
            self.send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "invalid body size"})
            return

        try:
            payload = json.loads(self.rfile.read(length))
            document = payload["html"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid JSON payload"})
            return
        if not isinstance(document, str) or not document.lstrip().lower().startswith("<!doctype html"):
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "expected a complete HTML document"})
            return

        token = match.group(1)
        write_atomic(DATA_DIR / f"{token}.html", document)
        self._prune_old_pages(keep=3)
        self.send_json(HTTPStatus.CREATED, {"path": f"/brief/{token}"})

    def _prune_old_pages(self, keep: int) -> None:
        pages = sorted(DATA_DIR.glob("*.html"), key=lambda item: item.stat().st_mtime, reverse=True)
        for stale_page in pages[keep:]:
            stale_page.unlink(missing_ok=True)


if __name__ == "__main__":
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Briefing web service listening on port {PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), BriefingHandler).serve_forever()
