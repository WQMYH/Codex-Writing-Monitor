from __future__ import annotations

import ctypes
import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from writing_ops.adapters import WindowsProcessIdentity, get_windows_process_identity
from writing_ops.loopback import validate_storyforge_origin

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


def launch_storyforge(
    configuration: RuntimeConfiguration, *, supervisor_nonce: str
) -> ManagedStoryforge:
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
    job = create_windows_job()
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(
            configuration.storyforge_command,
            cwd=configuration.storyforge_root,
            env=environment,
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
