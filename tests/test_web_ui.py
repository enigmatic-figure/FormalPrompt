from __future__ import annotations

from fastapi.testclient import TestClient

from formalprompt.server import create_app
from formalprompt.store import RunStore
from tests.test_session_api import minimal_document


def test_browser_shell_is_packaged_and_hardened(tmp_path):
    store = RunStore.create(tmp_path, minimal_document())
    client = TestClient(create_app(store, token="token"))

    page = client.get("/")
    script = client.get("/static/app.js")

    assert page.status_code == 200
    assert '<main id="app"' in page.text
    assert 'type="module" src="/static/app.js"' in page.text
    assert page.headers["content-security-policy"].startswith("default-src 'self'")
    assert page.headers["x-frame-options"] == "DENY"
    assert page.headers["referrer-policy"] == "no-referrer"
    assert script.status_code == 200
    assert "innerHTML" not in script.text
    assert "textContent" in script.text
    assert "Authorization" in script.text
    assert "sessionStorage" in script.text
    assert 'api("/api/assistance"' in script.text
    assert 'api("/api/review"' in script.text
    assert 'api("/api/compose"' in script.text
    assert 'api("/api/proposals/apply"' in script.text
    assert "api(`/api/artifacts/" in script.text
    assert "Apply suggestion" in script.text
    assert "Apply proposed canvas" in script.text
    assert "Compose initialization" in script.text


def test_validation_endpoint_returns_current_issues(tmp_path):
    document = minimal_document()
    field = document["tabs"][0]["sections"][0]["fields"][0]
    field["value"] = ""
    field["provenance"] = "unresolved"
    field["review_status"] = "needs-input"
    store = RunStore.create(tmp_path, document)
    client = TestClient(create_app(store, token="token"))

    response = client.get("/api/validation", headers={"Authorization": "Bearer token"})

    assert response.status_code == 200
    assert response.json()["ready"] is False
    assert {issue["code"] for issue in response.json()["issues"]} == {
        "required-value-missing",
        "unresolved-blocker",
    }
