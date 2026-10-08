"""Relays chat requests to the model endpoint, asking for tool calls whenever tools are sent.

Albert's gateway up to 0.8.0 turns a missing `tool_choice` into "none", against the OpenAI
convention the engine relies on, so DeepSeek never calls the engine's tools. Albert 0.9.0 fixes
it, announced for deployment on 2026-10-19: this relay can go once it is deployed.
"""

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


def with_tool_choice(body: dict[str, Any]) -> dict[str, Any]:
    """The request body, with `tool_choice: "auto"` when it sends tools without choosing."""
    if body.get("tools") and "tool_choice" not in body:
        return {**body, "tool_choice": "auto"}
    return body


@contextmanager
def relaying(upstream: str) -> Iterator[str]:
    """Relays to `upstream` from a free local port, and yields the address to send requests to."""
    relay = _Relay(upstream, port=0)
    threading.Thread(target=relay.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{relay.server_address[1]}"
    finally:
        relay.shutdown()
        relay.server_close()


def serve(upstream: str, port: int) -> None:
    with _Relay(upstream, port) as relay:
        relay.serve_forever()


class _Relay(ThreadingHTTPServer):
    def __init__(self, upstream, port):
        super().__init__(("127.0.0.1", port), _Handler)
        self.upstream = upstream.rstrip("/")


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = with_tool_choice(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        request = urllib.request.Request(
            self.server.upstream + self.path,
            data=json.dumps(body).encode(),
            headers={
                "Authorization": self.headers.get("Authorization", ""),
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                self._answer(response.status, response.headers, response.read())
        except urllib.error.HTTPError as error:
            self._answer(error.code, error.headers, error.read())
        except urllib.error.URLError as error:
            message = {"error": {"message": f"model endpoint unreachable: {error.reason}"}}
            self._answer(502, {}, json.dumps(message).encode())

    def _answer(self, status, headers, payload):
        try:
            self.send_response(status)
            self.send_header("Content-Type", headers.get("Content-Type", "application/json"))
            if retry_after := headers.get("Retry-After"):
                self.send_header("Retry-After", retry_after)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass  # the engine stopped waiting for this answer, after its own timeout

    def log_message(self, format, *args):
        pass
