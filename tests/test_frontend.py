"""Verify that the frontend entry point and its linked assets can be served."""

from functools import partial
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from .conftest import ROOT, get


class PageElements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.assets = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        if tag == "script" and attrs.get("src"):
            self.assets.add(attrs["src"])
        if tag == "link" and attrs.get("rel") == "stylesheet":
            self.assets.add(attrs["href"])


@pytest.fixture(scope="module")
def frontend_server():
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(Handler, directory=str(ROOT / "app"))
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:{}".format(server.server_port)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_page_has_media_and_date_controls(frontend_server):
    status, headers, body = get(frontend_server + "/")
    page = PageElements()
    page.feed(body.decode("utf-8"))

    assert status == 200
    assert headers.get_content_type() == "text/html"
    assert {"apod-date-form", "apod-date", "nasa-image", "nasa-video",
            "image-error", "retry-image"} <= page.ids
    assert page.assets == {"./render.js", "./styles.css"}


@pytest.mark.parametrize("path,content_types", [
    ("/render.js", {"text/javascript", "application/javascript"}),
    ("/styles.css", {"text/css"}),
], ids=["JavaScript asset", "CSS asset"])
def test_linked_assets_are_available(frontend_server, path, content_types):
    status, headers, body = get(frontend_server + path)

    assert status == 200
    assert headers.get_content_type() in content_types
    assert body
