"""Run the real API against a local NASA stub for deterministic tests."""

import json
import os
import socket
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import pytest


ROOT = Path(__file__).resolve().parents[1]


def get(url):
    """Return status, headers, and body for success and HTTP error responses."""
    try:
        response = urlopen(url, timeout=3)
    except HTTPError as error:
        response = error
    with response:
        return response.status, response.headers, response.read()


@pytest.fixture
def nasa_stub():
    state = {"status": 200, "body": {}, "requests": []}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state["requests"].append(self.path)
            body = json.dumps(state["body"]).encode("utf-8")
            self.send_response(state["status"])
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state, "http://127.0.0.1:{}".format(server.server_port)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


@pytest.fixture
def api_server(nasa_stub):
    _state, nasa_url = nasa_stub
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    env = os.environ.copy()
    env.update({"PORT": str(port), "API_TOKEN": "pytest-token", "NASA_API_URL": nasa_url + "/apod"})
    process = subprocess.Popen(
        ["node", "index.js"],
        cwd=ROOT / "server",
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    base_url = "http://127.0.0.1:{}".format(port)
    try:
        for _ in range(50):
            if process.poll() is not None:
                pytest.fail("API exited during startup: " + process.stderr.read().decode())
            try:
                if get(base_url + "/")[0] == 200:
                    break
            except URLError:
                time.sleep(0.1)
        else:
            pytest.fail("API did not start within five seconds")
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
        process.stderr.close()
