from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from formalprompt.adapters.openai_compatible import OpenAICompatibleAssistant
from formalprompt.assistant import AssistantProtocolError


class _Handler(BaseHTTPRequestHandler):
    request_body: dict | None = None
    authorization: str | None = None

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        type(self).request_body = json.loads(self.rfile.read(length))
        type(self).authorization = self.headers.get("Authorization")
        request_text = type(self).request_body["messages"][1]["content"]
        request = json.loads(request_text)
        content = json.dumps(
            {
                "contract": "agent-canvas-assistant/v1",
                "request_id": request["request_id"],
                "summary": "A focused response",
                "suggestions": [],
                "questions": ["Which constraint matters most?"],
            }
        )
        response = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format, *args):
        return


def test_openai_compatible_adapter_round_trips_protocol_without_sdk():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assistant = OpenAICompatibleAssistant(
            base_url=f"http://127.0.0.1:{server.server_port}/v1",
            model="muse-test",
            api_key="super-secret",
        )
        request = {
            "contract": "agent-canvas-assistant/v1",
            "request_id": "request-42",
            "operation": "specification-review",
            "context": {"role": "critic", "document": {"metadata": {"title": "Test"}}},
        }

        response = assistant.invoke(request)

        assert response.request_id == "request-42"
        assert response.questions == ["Which constraint matters most?"]
        assert _Handler.authorization == "Bearer super-secret"
        assert _Handler.request_body["model"] == "muse-test"
        assert _Handler.request_body["temperature"] == 0.2
        assert "super-secret" not in json.dumps(_Handler.request_body)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_adapter_accepts_chat_completions_endpoint_without_duplication():
    assistant = OpenAICompatibleAssistant(
        base_url="http://localhost:1234/v1/chat/completions",
        model="local-model",
    )

    assert assistant.endpoint == "http://localhost:1234/v1/chat/completions"


def test_authenticated_cross_origin_redirect_is_rejected_without_disclosing_key():
    class DestinationHandler(BaseHTTPRequestHandler):
        authorization = None

        def do_POST(self):
            type(self).authorization = self.headers.get("Authorization")
            self.send_response(200)
            self.end_headers()

        def log_message(self, format, *args):
            return

    destination = ThreadingHTTPServer(("127.0.0.1", 0), DestinationHandler)

    class RedirectHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(307)
            self.send_header(
                "Location",
                f"http://127.0.0.1:{destination.server_port}/stolen",
            )
            self.end_headers()

        def log_message(self, format, *args):
            return

    redirect = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
    threads = [
        threading.Thread(target=destination.serve_forever, daemon=True),
        threading.Thread(target=redirect.serve_forever, daemon=True),
    ]
    for thread in threads:
        thread.start()
    try:
        assistant = OpenAICompatibleAssistant(
            base_url=f"http://127.0.0.1:{redirect.server_port}/v1",
            model="muse-test",
            api_key="redirect-secret",
        )
        with pytest.raises(AssistantProtocolError, match="HTTP 307"):
            assistant.invoke(
                {
                    "contract": "agent-canvas-assistant/v1",
                    "request_id": "redirect-test",
                    "operation": "specification-review",
                    "context": {},
                }
            )
        assert DestinationHandler.authorization is None
    finally:
        redirect.shutdown()
        destination.shutdown()
        redirect.server_close()
        destination.server_close()
        for thread in threads:
            thread.join(timeout=2)


def test_authenticated_non_loopback_http_endpoint_is_rejected():
    with pytest.raises(ValueError, match="HTTPS or loopback"):
        OpenAICompatibleAssistant(
            base_url="http://example.test/v1",
            model="model",
            api_key="secret",
        )
