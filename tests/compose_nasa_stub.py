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


def apod(requested_date):
    """Return a post shaped like science.nasa.gov's APOD Basic JSON."""
    if requested_date == "2024-01-02":
        return {
            "title": "A launch", "date": requested_date,
            "explanation": "<strong>Explanation:</strong> A video", "copyright": "",
            "media_type": "video", "hdurl": MEDIA_BASE_URL + "/media/thumb.png",
            "basic_html": '<iframe width="960" height="540" src="{}/media/video.html"></iframe>'.format(MEDIA_BASE_URL),
        }
    return {
        "title": "A galaxy", "date": requested_date,
        "explanation": "<strong>Explanation:</strong> Spiral arms",
        "copyright": "<b> Image Credit &amp; Copyright: </b> <a href=\"https://example.com\">A. Astronomer</a>",
        "media_type": "image", "hdurl": MEDIA_BASE_URL + "/media/large.png",
        "basic_html": "<img src=\"{}/media/large.png\">".format(MEDIA_BASE_URL),
    }


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

        # The latest APOD is the newest-first list; a single day is /apod-basic/{YYMMDD}
        if request.path == "/apod-basic" and parse_qs(request.query).get("per_page") == ["1"]:
            self.send_json(200, [apod("2024-01-01")])
            return
        if not request.path.startswith("/apod-basic/"):
            self.send_json(400, {"error": "Unexpected NASA request"})
            return

        date_code = request.path.rsplit("/", 1)[1]
        requested_date = "20{}-{}-{}".format(date_code[:2], date_code[2:4], date_code[4:])
        if requested_date == "2024-01-03":
            self.send_json(503, {"error": "NASA temporarily unavailable"})
        # Fail every attempt of the first API request (the server retries 3 times)
        elif requested_date == "2024-01-04" and Handler.retry_requests < 3:
            Handler.retry_requests += 1
            self.send_json(503, {"error": "NASA temporarily unavailable"})
        else:
            self.send_json(200, apod(requested_date))

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
