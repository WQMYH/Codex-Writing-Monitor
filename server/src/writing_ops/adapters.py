from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class EdgeLaunchSpec:
    edge_executable: Path
    profile_dir: Path
    profile_lock: Path
    storyforge_origin: str
    command: tuple[str, ...]

    def command_with_handoff(self, handoff_url: str) -> tuple[str, ...]:
        handoff = urlsplit(handoff_url)
        if (
            f"{handoff.scheme}://{handoff.netloc}" != self.storyforge_origin
            or handoff.path != "/writing-ops"
            or handoff.query
            or not handoff.fragment
        ):
            raise ValueError("Edge handoff must use the configured Storyforge origin")
        return self.command + (handoff_url,)


@dataclass(frozen=True, slots=True)
class WindowsProcessIdentity:
    pid: int
    created_at_100ns: int


def get_windows_process_identity(pid: int) -> WindowsProcessIdentity:
    if os.name != "nt":
        raise RuntimeError("Windows process identity is unavailable on this host")
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetProcessTimes.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    )
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        created = wintypes.FILETIME()
        unused = wintypes.FILETIME()
        if not kernel32.GetProcessTimes(
            handle,
            ctypes.byref(created),
            ctypes.byref(unused),
            ctypes.byref(unused),
            ctypes.byref(unused),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel32.CloseHandle(handle)
    return WindowsProcessIdentity(
        pid=pid,
        created_at_100ns=(created.dwHighDateTime << 32) | created.dwLowDateTime,
    )


def windows_process_identity_matches(identity: WindowsProcessIdentity) -> bool:
    try:
        return get_windows_process_identity(identity.pid) == identity
    except OSError:
        return False


def build_edge_launch_spec(
    *, edge_executable: Path, runtime_root: Path, storyforge_origin: str
) -> EdgeLaunchSpec:
    from writing_ops.loopback import validate_storyforge_origin

    edge = edge_executable.resolve(strict=True)
    if not edge.is_file() or edge.name.lower() != "msedge.exe":
        raise ValueError("Edge executable must be an existing msedge.exe file")
    root = runtime_root.resolve()
    profile_dir = root / "edge-profile"
    return EdgeLaunchSpec(
        edge_executable=edge,
        profile_dir=profile_dir,
        profile_lock=root / "edge-profile.lock",
        storyforge_origin=validate_storyforge_origin(storyforge_origin),
        command=(
            str(edge),
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--remote-debugging-address=127.0.0.1",
            "--remote-debugging-port=0",
        ),
    )


def acquire_edge_profile_lock(spec: EdgeLaunchSpec, *, owner_nonce: str) -> Path:
    spec.profile_dir.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(spec.profile_lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError as error:
        raise FileExistsError(f"Edge profile lock already exists: {spec.profile_lock}") from error
    with os.fdopen(descriptor, "w", encoding="utf-8") as lock:
        lock.write(owner_nonce)
    return spec.profile_lock


def release_edge_profile_lock(spec: EdgeLaunchSpec, *, owner_nonce: str) -> bool:
    try:
        if spec.profile_lock.read_text(encoding="utf-8") != owner_nonce:
            return False
        spec.profile_lock.unlink()
    except FileNotFoundError:
        return False
    return True


class WritingHostAdapter(Protocol):
    def runtime_status(self) -> dict[str, Any]: ...


class FakeWritingHostAdapter:
    def runtime_status(self) -> dict[str, Any]:
        return {
            "adapter": "fake",
            "storyforge": "not_started",
            "writing_mcp": "not_started",
            "edge": "not_started",
            "browser_worker": "not_started",
            "human_review_status": "pending",
        }
