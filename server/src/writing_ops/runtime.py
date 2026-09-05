from __future__ import annotations

import ctypes
import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from writing_ops.adapters import (
    EdgeLaunchSpec,
    WindowsProcessIdentity,
    acquire_edge_profile_lock,
    get_windows_process_identity,
    release_edge_profile_lock,
)
from writing_ops.loopback import (
    DashboardLoopbackRuntime,
    start_dashboard_loopback,
    validate_storyforge_origin,
)
from writing_ops.service import WritingOpsService

STORYFORGE_DEV_ENTRY = "node scripts/dev-with-writing-bridge.mjs"
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_TERMINATE = 0x0001


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        "read_operation_count",
        "write_operation_count",
        "other_operation_count",
        "read_transfer_count",
        "write_transfer_count",
        "other_transfer_count",
    )]


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("per_process_user_time_limit", ctypes.c_longlong),
        ("per_job_user_time_limit", ctypes.c_longlong),
        ("limit_flags", ctypes.c_ulong),
        ("minimum_working_set_size", ctypes.c_size_t),
        ("maximum_working_set_size", ctypes.c_size_t),
        ("active_process_limit", ctypes.c_ulong),
        ("affinity", ctypes.c_size_t),
        ("priority_class", ctypes.c_ulong),
        ("scheduling_class", ctypes.c_ulong),
    ]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("basic_limit_information", _BasicLimitInformation),
        ("io_info", _IoCounters),
        ("process_memory_limit", ctypes.c_size_t),
        ("job_memory_limit", ctypes.c_size_t),
        ("peak_process_memory_used", ctypes.c_size_t),
        ("peak_job_memory_used", ctypes.c_size_t),
    ]


def _kernel32():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p)
    kernel32.CreateJobObjectW.restype = ctypes.c_void_p
    kernel32.SetInformationJobObject.argtypes = (
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_ulong,
    )
    kernel32.SetInformationJobObject.restype = ctypes.c_int
    kernel32.OpenProcess.argtypes = (ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong)
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.AssignProcessToJobObject.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
    kernel32.AssignProcessToJobObject.restype = ctypes.c_int
    kernel32.TerminateJobObject.argtypes = (ctypes.c_void_p, ctypes.c_ulong)
    kernel32.TerminateJobObject.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    kernel32.CloseHandle.restype = ctypes.c_int
    return kernel32


class WindowsJob:
    def __init__(self, handle: int) -> None:
        self._handle = handle

    def assign_pid(self, pid: int) -> None:
        kernel32 = _kernel32()
        process = kernel32.OpenProcess(_PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, pid)
        if not process:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not kernel32.AssignProcessToJobObject(self._handle, process):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            kernel32.CloseHandle(process)

    def close(self) -> None:
        if self._handle:
            kernel32 = _kernel32()
            if not kernel32.TerminateJobObject(self._handle, 1):
                raise ctypes.WinError(ctypes.get_last_error())
            if not kernel32.CloseHandle(self._handle):
                raise ctypes.WinError(ctypes.get_last_error())
            self._handle = 0


def create_windows_job() -> WindowsJob:
    if not hasattr(ctypes, "WinDLL"):
        raise RuntimeError("Windows Job Objects require Windows")
    kernel32 = _kernel32()
    handle = kernel32.CreateJobObjectW(None, None)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = _ExtendedLimitInformation()
    limits.basic_limit_information.limit_flags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel32.SetInformationJobObject(
        handle,
        _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
        ctypes.byref(limits),
        ctypes.sizeof(limits),
    ):
        kernel32.CloseHandle(handle)
        raise ctypes.WinError(ctypes.get_last_error())
    return WindowsJob(handle)


@dataclass(frozen=True, slots=True)
class RuntimeConfiguration:
    storyforge_root: Path
    storyforge_origin: str
    configuration_fingerprint: str
    storyforge_command: tuple[str, ...] = ("npm.cmd", "run", "dev")


@dataclass(slots=True)
class ManagedStoryforge:
    process: subprocess.Popen[bytes]
    job: WindowsJob
    identity: WindowsProcessIdentity
    configuration_fingerprint: str

    def close(self) -> None:
        self.job.close()


@dataclass(slots=True)
class ManagedEdge:
    process: subprocess.Popen[bytes]
    job: WindowsJob
    identity: WindowsProcessIdentity
    spec: EdgeLaunchSpec
    supervisor_nonce: str
    cdp_origin: str

    def close(self) -> None:
        self.job.close()
        if not release_edge_profile_lock(self.spec, owner_nonce=self.supervisor_nonce):
            raise RuntimeError("Edge profile lock ownership was lost")


@dataclass(slots=True)
class ManagedBrowserHarness:
    process: subprocess.Popen[bytes]
    job: WindowsJob
    identity: WindowsProcessIdentity

    def close(self) -> None:
        self.job.close()


@dataclass(slots=True)
class ManagedRuntimeSession:
    loopback: DashboardLoopbackRuntime
    storyforge: ManagedStoryforge
    edge: ManagedEdge
    browser_harness: ManagedBrowserHarness

    def close(self) -> None:
        try:
            self.browser_harness.close()
        finally:
            try:
                self.edge.close()
            finally:
                try:
                    self.storyforge.close()
                finally:
                    self.loopback.stop()


def load_runtime_configuration(path: Path) -> RuntimeConfiguration:
    configuration_bytes = path.read_bytes()
    configuration = json.loads(configuration_bytes)
    if not isinstance(configuration, dict) or set(configuration) != {
        "storyforgeRoot",
        "storyforgeOrigin",
    }:
        raise ValueError("runtime configuration has invalid keys")
    root = Path(configuration["storyforgeRoot"]).resolve(strict=True)
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    if (
        package.get("name") != "storyforge"
        or package.get("scripts", {}).get("dev") != STORYFORGE_DEV_ENTRY
    ):
        raise ValueError("Storyforge dev entry is not verified")
    return RuntimeConfiguration(
        storyforge_root=root,
        storyforge_origin=validate_storyforge_origin(configuration["storyforgeOrigin"]),
        configuration_fingerprint=hashlib.sha256(configuration_bytes).hexdigest(),
    )


def _supervisor_environment(supervisor_nonce: str) -> dict[str, str]:
    source_environment = {key.upper(): value for key, value in os.environ.items()}
    environment = {
        key: source_environment[key]
        for key in (
            "APPDATA",
            "COMSPEC",
            "LOCALAPPDATA",
            "PATH",
            "PATHEXT",
            "SYSTEMROOT",
            "TEMP",
            "TMP",
            "USERPROFILE",
            "WINDIR",
        )
        if key in source_environment
    }
    environment["WRITING_OPS_SUPERVISOR_NONCE"] = supervisor_nonce
    return environment


def launch_storyforge(
    configuration: RuntimeConfiguration, *, supervisor_nonce: str
) -> ManagedStoryforge:
    job = create_windows_job()
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(
            configuration.storyforge_command,
            cwd=configuration.storyforge_root,
            env=_supervisor_environment(supervisor_nonce),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        job.assign_pid(process.pid)
        return ManagedStoryforge(
            process=process,
            job=job,
            identity=get_windows_process_identity(process.pid),
            configuration_fingerprint=configuration.configuration_fingerprint,
        )
    except BaseException:
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        job.close()
        raise


def launch_edge(
    spec: EdgeLaunchSpec, *, handoff_url: str, supervisor_nonce: str
) -> ManagedEdge:
    command = spec.command_with_handoff(handoff_url)
    acquire_edge_profile_lock(spec, owner_nonce=supervisor_nonce)
    job: WindowsJob | None = None
    process: subprocess.Popen[bytes] | None = None
    try:
        job = create_windows_job()
        process = subprocess.Popen(
            command,
            cwd=spec.profile_dir,
            env=_supervisor_environment(supervisor_nonce),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        job.assign_pid(process.pid)
        return ManagedEdge(
            process=process,
            job=job,
            identity=get_windows_process_identity(process.pid),
            spec=spec,
            supervisor_nonce=supervisor_nonce,
            cdp_origin=_wait_for_edge_cdp_origin(spec.profile_dir),
        )
    except BaseException:
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        if job is not None:
            job.close()
        release_edge_profile_lock(spec, owner_nonce=supervisor_nonce)
        raise


def _browser_worker_command(worker_root: Path) -> tuple[str, ...]:
    executable = worker_root / ".venv" / "Scripts" / "python.exe"
    script = worker_root / "worker.py"
    if not executable.is_file() or not script.is_file():
        raise FileNotFoundError("isolated browser worker is unavailable")
    return str(executable), str(script), "--daemon"


def launch_browser_harness(
    *, worker_root: Path, runtime_root: Path, cdp_origin: str, supervisor_nonce: str
) -> ManagedBrowserHarness:
    job = create_windows_job()
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(
            _browser_worker_command(worker_root),
            cwd=worker_root,
            env=_supervisor_environment(supervisor_nonce)
            | {
                "WRITING_OPS_CDP_ORIGIN": cdp_origin,
                "WRITING_OPS_RUNTIME_ROOT": str(runtime_root.resolve()),
            },
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        job.assign_pid(process.pid)
        return ManagedBrowserHarness(
            process=process,
            job=job,
            identity=get_windows_process_identity(process.pid),
        )
    except BaseException:
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        job.close()
        raise


def _wait_for_edge_cdp_origin(profile_dir: Path) -> str:
    port_file = profile_dir / "DevToolsActivePort"
    for _ in range(50):
        try:
            port = int(port_file.read_text(encoding="utf-8").splitlines()[0])
        except (FileNotFoundError, IndexError, ValueError):
            time.sleep(0.1)
            continue
        if 1 <= port <= 65535:
            return f"http://127.0.0.1:{port}"
        break
    raise RuntimeError("Edge did not publish a valid loopback CDP port")


def launch_runtime_session(
    *,
    service: WritingOpsService,
    plugin_root: Path,
    configuration: RuntimeConfiguration,
    edge_spec: EdgeLaunchSpec,
    supervisor_nonce: str,
) -> ManagedRuntimeSession:
    loopback = start_dashboard_loopback(
        service,
        plugin_root=plugin_root,
        storyforge_origin=configuration.storyforge_origin,
    )
    storyforge: ManagedStoryforge | None = None
    edge: ManagedEdge | None = None
    browser_harness: ManagedBrowserHarness | None = None
    try:
        storyforge = launch_storyforge(configuration, supervisor_nonce=supervisor_nonce)
        edge = launch_edge(
            edge_spec,
            handoff_url=loopback.storyforge_url,
            supervisor_nonce=supervisor_nonce,
        )
        browser_harness = launch_browser_harness(
            worker_root=plugin_root / "browser-worker",
            runtime_root=edge_spec.profile_dir.parent,
            cdp_origin=edge.cdp_origin,
            supervisor_nonce=supervisor_nonce,
        )
        return ManagedRuntimeSession(
            loopback=loopback,
            storyforge=storyforge,
            edge=edge,
            browser_harness=browser_harness,
        )
    except BaseException:
        if browser_harness is not None:
            browser_harness.close()
        if edge is not None:
            edge.close()
        if storyforge is not None:
            storyforge.close()
        loopback.stop()
        raise
