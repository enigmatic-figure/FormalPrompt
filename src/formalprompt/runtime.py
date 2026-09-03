from __future__ import annotations

import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from contextlib import suppress

import uvicorn

from formalprompt.assistant import AssistantBackend
from formalprompt.launchers import (
    LauncherUnavailable,
    Renderer,
    ResolvedRenderer,
    build_canvas_url,
    choose_renderer,
    launch,
)
from formalprompt.server import create_app
from formalprompt.store import RunStore


class CanvasRuntime:
    def __init__(
        self,
        store: RunStore,
        *,
        token: str,
        host: str = "127.0.0.1",
        port: int = 0,
        renderer: Renderer = "auto",
        assistant: AssistantBackend | None = None,
        reviewer: AssistantBackend | None = None,
        auto_stop: bool = True,
    ):
        self.store = store
        self.token = token
        self.host = host
        self.port = port
        self.renderer: ResolvedRenderer = choose_renderer(renderer)
        self.assistant = assistant
        self.reviewer = reviewer
        self.auto_stop = auto_stop
        self._socket: socket.socket | None = None
        self._server: uvicorn.Server | None = None
        self._server_thread: threading.Thread | None = None
        self._monitor_thread: threading.Thread | None = None
        self._renderer_process: subprocess.Popen | None = None

    @property
    def base_url(self) -> str:
        browser_host = "127.0.0.1" if self.host in {"0.0.0.0", "::"} else self.host
        return f"http://{browser_host}:{self.port}"

    @property
    def canvas_url(self) -> str:
        return build_canvas_url(self.host, self.port, self.token)

    def start(self) -> None:
        if self._server_thread is not None:
            raise RuntimeError("Canvas runtime has already been started")
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind((self.host, self.port))
        except OSError as exc:
            listener.close()
            raise RuntimeError(
                f"Unable to bind canvas server to {self.host}:{self.port}. "
                "Choose another port or retry with --port 0."
            ) from exc
        listener.listen(128)
        self.port = listener.getsockname()[1]
        self._socket = listener

        config = uvicorn.Config(
            create_app(self.store, self.token, self.assistant, self.reviewer),
            host=self.host,
            port=self.port,
            log_level="warning",
            access_log=False,
        )
        self._server = uvicorn.Server(config)
        self._server_thread = threading.Thread(
            target=self._server.run,
            kwargs={"sockets": [listener]},
            name=f"formalprompt-server-{self.store.run_id}",
            daemon=True,
        )
        self._server_thread.start()
        if self.auto_stop:
            self._monitor_thread = threading.Thread(
                target=self._monitor_completion,
                name=f"formalprompt-monitor-{self.store.run_id}",
                daemon=True,
            )
            self._monitor_thread.start()

    def wait_until_ready(self, timeout_seconds: float = 10) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if self._server_thread is not None and not self._server_thread.is_alive():
                return False
            try:
                with urllib.request.urlopen(f"{self.base_url}/healthz", timeout=0.25) as response:
                    if response.status == 200:
                        return True
            except (OSError, urllib.error.URLError):
                time.sleep(0.05)
        return False

    def open_renderer(self) -> None:
        process = launch(self.renderer, self.canvas_url)
        if process is not None:
            self._renderer_process = process
            time.sleep(0.1)
            return_code = process.poll()
            if return_code is not None:
                self._renderer_process = None
                raise LauncherUnavailable(
                    f"Carbonyl exited during startup with status {return_code}. "
                    "Review its terminal error output and dependencies."
                )

    def wait(self, timeout_seconds: float | None = None) -> bool:
        if self._server_thread is None:
            return True
        self._server_thread.join(timeout=timeout_seconds)
        return not self._server_thread.is_alive()

    def stop(self) -> None:
        self._stop_renderer()
        if self._server is not None:
            self._server.should_exit = True
        if self._server_thread is not None and self._server_thread.is_alive():
            self._server_thread.join(timeout=5)
        if self._socket is not None:
            with suppress(OSError):
                self._socket.close()

    def _monitor_completion(self) -> None:
        while self._server is not None and not self._server.should_exit:
            try:
                if (
                    self.store.read_state()["status"] == "compiled"
                    and (self.store.path / "result.json").is_file()
                ):
                    self._stop_renderer()
                    self._server.should_exit = True
                    return
            except (OSError, ValueError):
                return
            time.sleep(0.1)

    def _stop_renderer(self) -> None:
        process = self._renderer_process
        if process is None:
            return
        self._renderer_process = None
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
