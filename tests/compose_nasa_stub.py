"""Deterministic APOD responses for the containerized integration suite."""

import json
import socket
import struct
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


MEDIA_BASE_URL = "http://{}:8000".format(socket.gethostbyname(socket.gethostname()))


def pixel_png():
    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data +
                struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff))

    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")) +
            chunk(b"IEND", b""))


class Handler(BaseHTTPRequestHandler):
    retry_requests = 0

    def do_GET(self):
        request = urlsplit(self.path)
        if request.path in ("/media/galaxy.png", "/media/large.png", "/media/thumb.png"):
            self.send_body(200, "image/png", pixel_png())
            return
        if request.path == "/media/video.html":
            self.send_body(200, "text/html", b"<title>Launch footage</title><h1>Launch footage</h1>")
            return

        params = parse_qs(request.query)

        if request.path != "/apod" or params.get("api_key") != ["pytest-token"] or params.get("thumbs") != ["true"]:
            self.send_json(400, {"error": "Unexpected NASA request"})
            return

        requested_date = params.get("date", ["2024-01-01"])[0]
        if requested_date == "2024-01-03":
            self.send_json(503, {"error": "NASA temporarily unavailable"})
        elif requested_date == "2024-01-04" and Handler.retry_requests == 0:
            Handler.retry_requests += 1
            self.send_json(503, {"error": "NASA temporarily unavailable"})
        elif requested_date == "2024-01-02":
            self.send_json(200, {
                "title": "A launch", "date": requested_date, "explanation": "A video",
                "media_type": "video", "url": MEDIA_BASE_URL + "/media/video.html",
                "thumbnail_url": MEDIA_BASE_URL + "/media/thumb.png",
            })
        else:
            self.send_json(200, {
                "title": "A galaxy", "date": requested_date,
                "explanation": "Spiral arms", "copyright": "A. Astronomer",
                "media_type": "image", "url": MEDIA_BASE_URL + "/media/galaxy.png",
                "hdurl": MEDIA_BASE_URL + "/media/large.png",
            })

    def send_json(self, status, payload):
        self.send_body(status, "application/json", json.dumps(payload).encode("utf-8"))

    def send_body(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
