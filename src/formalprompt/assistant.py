from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from formalprompt.models import CanvasDocument


class AssistantProtocolError(RuntimeError):
    pass


class CommandOutputLimitExceeded(RuntimeError):
    def __init__(self, stream: str):
        super().__init__(f"Assistant {stream} exceeded the configured size limit")
        self.stream = stream


@dataclass(frozen=True)
class BoundedCommandResult:
    returncode: int
    stdout: str
    stderr: str


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AssistantRequest(StrictModel):
    contract: Literal["agent-canvas-assistant/v1"]
    request_id: str = Field(min_length=1)
    operation: Literal["field-assistance", "specification-review", "initialization-compose"]
    context: dict[str, Any]


class Suggestion(StrictModel):
    value: Any
    label: str = Field(min_length=1)
    implications: str = ""


class AssistantResponse(StrictModel):
    contract: Literal["agent-canvas-assistant/v1"]
    request_id: str = Field(min_length=1)
    summary: str
    suggestions: list[Suggestion] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    disposition: Literal["advisory", "needs-clarification", "ready"] = "advisory"
    next_document: CanvasDocument | None = None


class AssistantBackend(Protocol):
    def invoke(self, request: dict[str, Any] | AssistantRequest) -> AssistantResponse: ...


class CommandAssistant:
    def __init__(
        self,
        command: list[str],
        *,
        timeout_seconds: float = 120,
        maximum_output_bytes: int = 1_000_000,
        maximum_error_bytes: int = 65_536,
    ):
        if not command:
            raise ValueError("Assistant command cannot be empty")
        if timeout_seconds <= 0 or maximum_output_bytes < 1 or maximum_error_bytes < 1:
            raise ValueError("Assistant timeout and stream limits must be positive")
        self.command = list(command)
        self.timeout_seconds = timeout_seconds
        self.maximum_output_bytes = maximum_output_bytes
        self.maximum_error_bytes = maximum_error_bytes

    def invoke(self, request: dict[str, Any] | AssistantRequest) -> AssistantResponse:
        envelope = (
            request
            if isinstance(request, AssistantRequest)
            else AssistantRequest.model_validate(request)
        )
        try:
            completed = run_bounded_command(
                self.command,
                envelope.model_dump_json(),
                timeout_seconds=self.timeout_seconds,
                maximum_stdout_bytes=self.maximum_output_bytes,
                maximum_stderr_bytes=self.maximum_error_bytes,
            )
        except CommandOutputLimitExceeded as exc:
            raise AssistantProtocolError(str(exc)) from exc
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AssistantProtocolError(f"Assistant command failed to run: {exc}") from exc
        if completed.returncode != 0:
            raise AssistantProtocolError(
                f"Assistant command exited with status {completed.returncode}"
            )
        try:
            raw = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise AssistantProtocolError("Assistant did not return valid JSON") from exc
        try:
            response = AssistantResponse.model_validate(raw)
        except ValidationError as exc:
            raise AssistantProtocolError("Assistant response did not match the protocol") from exc
        if response.request_id != envelope.request_id:
            raise AssistantProtocolError("Assistant response request ID did not match")
        return response


def run_bounded_command(
    command: list[str],
    stdin_text: str,
    *,
    timeout_seconds: float,
    maximum_stdout_bytes: int,
    maximum_stderr_bytes: int,
) -> BoundedCommandResult:
    """Run a child while bounding both captured streams before they enter memory."""
    group_options: dict[str, Any]
    if os.name == "nt":
        group_options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    else:
        group_options = {"start_new_session": True}
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **group_options,
    )
    windows_job = _attach_windows_job(process) if os.name == "nt" else None
    stdout = bytearray()
    stderr = bytearray()
    exceeded = threading.Event()
    exceeded_stream: list[str] = []

    def drain(pipe, buffer: bytearray, limit: int, stream: str) -> None:
        try:
            while chunk := pipe.read(65_536):
                remaining = limit + 1 - len(buffer)
                if remaining > 0:
                    buffer.extend(chunk[:remaining])
                if len(buffer) > limit:
                    exceeded_stream.append(stream)
                    exceeded.set()
                    return
        finally:
            pipe.close()

    def feed() -> None:
        assert process.stdin is not None
        try:
            process.stdin.write(stdin_text.encode("utf-8"))
            process.stdin.flush()
        except (BrokenPipeError, OSError):
            pass
        finally:
            process.stdin.close()

    assert process.stdout is not None
    assert process.stderr is not None
    threads = [
        threading.Thread(
            target=drain,
            args=(process.stdout, stdout, maximum_stdout_bytes, "stdout"),
            daemon=True,
        ),
        threading.Thread(
            target=drain,
            args=(process.stderr, stderr, maximum_stderr_bytes, "stderr"),
            daemon=True,
        ),
        threading.Thread(target=feed, daemon=True),
    ]
    for thread in threads:
        thread.start()

    deadline = time.monotonic() + timeout_seconds
    timed_out = False
    tree_terminated = False
    while process.poll() is None:
        if exceeded.wait(timeout=0.02):
            _terminate_process_tree(process, windows_job)
            tree_terminated = True
            break
        if time.monotonic() >= deadline:
            timed_out = True
            _terminate_process_tree(process, windows_job)
            tree_terminated = True
            break
    if exceeded.is_set() and not tree_terminated:
        _terminate_process_tree(process, windows_job)
    process.wait()
    if windows_job is not None:
        windows_job.close()
    for thread in threads:
        thread.join(timeout=1)
    if timed_out:
        raise subprocess.TimeoutExpired(command, timeout_seconds)
    if exceeded_stream:
        raise CommandOutputLimitExceeded(exceeded_stream[0])
    return BoundedCommandResult(
        returncode=process.returncode,
        stdout=stdout.decode("utf-8", errors="replace"),
        stderr=stderr.decode("utf-8", errors="replace"),
    )


def _terminate_process_tree(process: subprocess.Popen, windows_job=None) -> None:
    """Terminate the complete subprocess invocation after a bounded failure."""
    if os.name == "nt":
        if windows_job is not None and windows_job.terminate():
            return
        completed = subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0 and process.poll() is None:
            process.kill()
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + 0.25
    while process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.01)
    with suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)


def _attach_windows_job(process: subprocess.Popen):
    """Attach a Windows process to a kill-on-close job, falling back when unavailable."""
    try:
        return _WindowsJob(process)
    except OSError:
        return None


class _WindowsJob:
    def __init__(self, process: subprocess.Popen):
        import ctypes
        from ctypes import wintypes

        class IoCounters(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_ulonglong),
                ("WriteOperationCount", ctypes.c_ulonglong),
                ("OtherOperationCount", ctypes.c_ulonglong),
                ("ReadTransferCount", ctypes.c_ulonglong),
                ("WriteTransferCount", ctypes.c_ulonglong),
                ("OtherTransferCount", ctypes.c_ulonglong),
            ]

        class BasicLimitInformation(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class ExtendedLimitInformation(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BasicLimitInformation),
                ("IoInfo", IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        self._ctypes = ctypes
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        self._kernel32.SetInformationJobObject.restype = wintypes.BOOL
        self._kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        self._kernel32.TerminateJobObject.restype = wintypes.BOOL
        self._kernel32.CloseHandle.restype = wintypes.BOOL
        self._handle = self._kernel32.CreateJobObjectW(None, None)
        if not self._handle:
            raise ctypes.WinError(ctypes.get_last_error())
        information = ExtendedLimitInformation()
        information.BasicLimitInformation.LimitFlags = 0x00002000
        configured = self._kernel32.SetInformationJobObject(
            self._handle,
            9,
            ctypes.byref(information),
            ctypes.sizeof(information),
        )
        assigned = configured and self._kernel32.AssignProcessToJobObject(
            self._handle,
            int(process._handle),
        )
        if not assigned:
            error = ctypes.get_last_error()
            self.close()
            raise ctypes.WinError(error)

    def terminate(self) -> bool:
        return bool(self._handle and self._kernel32.TerminateJobObject(self._handle, 1))

    def close(self) -> None:
        if self._handle:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None
