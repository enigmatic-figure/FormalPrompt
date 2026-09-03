from __future__ import annotations

import os
import shutil
import subprocess
import sys
import webbrowser
from collections.abc import Callable, Mapping
from typing import Literal
from urllib.parse import quote

Renderer = Literal["auto", "browser", "carbonyl", "none"]
ResolvedRenderer = Literal["browser", "carbonyl", "none"]


class LauncherUnavailable(RuntimeError):
    pass


def choose_renderer(
    requested: Renderer,
    *,
    platform: str | None = None,
    environment: Mapping[str, str] | None = None,
    executable_lookup: Callable[[str], str | None] = shutil.which,
) -> ResolvedRenderer:
    if requested != "auto":
        return requested
    current_platform = platform or sys.platform
    env = environment if environment is not None else os.environ
    remote = bool(env.get("SSH_CONNECTION") or env.get("SSH_TTY"))
    linux_headless = current_platform.startswith("linux") and not (
        env.get("DISPLAY") or env.get("WAYLAND_DISPLAY")
    )
    if remote or linux_headless:
        return "carbonyl" if executable_lookup("carbonyl") else "none"
    return "browser"


def build_canvas_url(host: str, port: int, token: str) -> str:
    browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    return f"http://{browser_host}:{port}/#token={quote(token, safe='')}"


def launch(
    renderer: ResolvedRenderer,
    url: str,
    *,
    executable_lookup: Callable[[str], str | None] = shutil.which,
    browser_open: Callable[[str], bool] = webbrowser.open,
) -> subprocess.Popen | None:
    if renderer == "none":
        return None
    if renderer == "browser":
        if not browser_open(url):
            raise LauncherUnavailable(f"No graphical browser accepted {url}")
        return None
    executable = executable_lookup("carbonyl")
    if not executable:
        raise LauncherUnavailable(
            "Carbonyl is not installed or is not on PATH. Install it globally with npm, "
            "use --renderer browser, or use --renderer none and open the printed URL."
        )
    command = [executable, url]
    return subprocess.Popen(command)
