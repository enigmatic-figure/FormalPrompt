from __future__ import annotations

import pytest

from formalprompt.launchers import LauncherUnavailable, build_canvas_url, choose_renderer, launch


def test_auto_uses_graphical_browser_on_windows_desktop():
    selected = choose_renderer(
        "auto", platform="win32", environment={}, executable_lookup=lambda name: None
    )

    assert selected == "browser"


def test_auto_uses_carbonyl_for_ssh_when_available():
    selected = choose_renderer(
        "auto",
        platform="linux",
        environment={"SSH_CONNECTION": "client server"},
        executable_lookup=lambda name: "/usr/bin/carbonyl" if name == "carbonyl" else None,
    )

    assert selected == "carbonyl"


def test_auto_falls_back_to_url_only_in_headless_session_without_carbonyl():
    selected = choose_renderer(
        "auto", platform="linux", environment={}, executable_lookup=lambda name: None
    )

    assert selected == "none"


def test_explicit_carbonyl_requires_installed_executable():
    with pytest.raises(LauncherUnavailable, match="Carbonyl"):
        launch(
            "carbonyl",
            "http://127.0.0.1:9000/#token=secret",
            executable_lookup=lambda name: None,
        )


def test_access_token_is_placed_in_fragment_not_query_string():
    url = build_canvas_url("127.0.0.1", 9341, "a secret/token")

    assert url == "http://127.0.0.1:9341/#token=a%20secret%2Ftoken"
    assert "?" not in url
