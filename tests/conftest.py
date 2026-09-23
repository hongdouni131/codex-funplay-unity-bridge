from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest


class FakeMcpServer:
    def __init__(self, mode: str = "success") -> None:
        self.mode = mode
        self.requests: list[dict[str, Any]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                request = json.loads(self.rfile.read(length))
                outer.requests.append(request)
                if outer.mode == "not_found":
                    self.send_response(404)
                    self.end_headers()
                    return
                if outer.mode == "invalid_json":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b"not json")
                    return
                if outer.mode == "slow":
                    time.sleep(0.2)
                if "id" not in request:
                    self.send_response(202)
                    self.end_headers()
                    return
                if outer.mode == "jsonrpc_error":
                    payload = {"jsonrpc": "2.0", "id": request["id"], "error": {"code": -32000, "message": "fake failure"}}
                elif request["method"] == "initialize":
                    protocol = "1999-01-01" if outer.mode == "old_protocol" else "2025-03-26"
                    payload = {"jsonrpc": "2.0", "id": request["id"], "result": {"protocolVersion": protocol, "serverInfo": {"name": "fake", "version": "1"}, "capabilities": {}}}
                elif request["method"] == "tools/list":
                    payload = {"jsonrpc": "2.0", "id": request["id"], "result": {"tools": [{"name": "read_scene", "description": "safe", "inputSchema": {"type": "object"}}]}}
                else:
                    payload = {"jsonrpc": "2.0", "id": request["id"], "result": {"content": [{"type": "text", "text": "done"}]}}
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(payload).encode("utf-8"))

            def log_message(self, *_: object) -> None:
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_port}/"

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.thread.join()
        self.httpd.server_close()


@pytest.fixture
def fake_server() -> FakeMcpServer:
    server = FakeMcpServer()
    server.start()
    yield server
    server.stop()
