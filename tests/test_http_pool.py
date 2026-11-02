"""Real HTTP checks for pooling without retaining cookies or credentials."""
import json
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import http_pool


@pytest.fixture()
def pooling_server():
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        connections = 0
        seen = []

        def setup(self):
            super().setup()
            self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            Handler.connections += 1

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            Handler.seen.append((dict(self.headers), body))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "2")
            self.send_header("Set-Cookie", "provider_session=private")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    yield f"http://127.0.0.1:{server.server_port}/", Handler
    server.shutdown()
    server.server_close()


def test_pool_reuses_connections_between_new_job_threads_without_credentials_leaking(pooling_server):
    url, handler = pooling_server
    for index in range(3):
        # The production workers are separate, short-lived threads, not a stable thread pool.
        with ThreadPoolExecutor(max_workers=1) as pool:
            response = pool.submit(http_pool.post, url, json={"request": index},
                                   headers={"Authorization": f"Bearer key-{index}"}, timeout=2).result()
            assert response.status_code == 200
    assert handler.connections == 1
    assert [headers["Authorization"] for headers, _ in handler.seen] == [
        "Bearer key-0", "Bearer key-1", "Bearer key-2",
    ]
    assert all("Cookie" not in headers for headers, _ in handler.seen)


def test_request_local_headers_are_not_retained(pooling_server):
    url, handler = pooling_server
    http_pool.post(url, json={}, headers={"Authorization": "Bearer private", "X-Alpha-Token": "secret"}, timeout=2)
    http_pool.post(url, json={}, timeout=2)
    headers = handler.seen[-1][0]
    assert "Authorization" not in headers
    assert "X-Alpha-Token" not in headers
    assert "Cookie" not in headers


def test_concurrent_requests_remain_isolated(pooling_server):
    url, handler = pooling_server
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(http_pool.post, url, json={"request": index},
                               headers={"Authorization": f"Bearer key-{index}"}, timeout=2)
                   for index in range(8)]
        assert all(future.result().status_code == 200 for future in futures)
    assert len(handler.seen) == 8
    assert all(headers["Authorization"] == f"Bearer key-{body['request']}"
               and "Cookie" not in headers for headers, body in handler.seen)


def test_pool_does_not_add_automatic_retries():
    assert http_pool._adapter.max_retries.total == 0
    assert http_pool.exceptions.Timeout is __import__("requests").exceptions.Timeout
