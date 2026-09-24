"""Small fcntl.flock compatibility layer for the exported Windows package."""

from __future__ import annotations

import os

LOCK_SH = 1
LOCK_EX = 2
LOCK_NB = 4
LOCK_UN = 8


if os.name != "nt":
    from fcntl import flock as flock
else:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    _LOCKFILE_FAIL_IMMEDIATELY = 0x00000001
    _LOCKFILE_EXCLUSIVE_LOCK = 0x00000002
    _MAX_DWORD = 0xFFFFFFFF

    class _OVERLAPPED(ctypes.Structure):
        _fields_ = [
            ("Internal", ctypes.c_void_p),
            ("InternalHigh", ctypes.c_void_p),
            ("Offset", wintypes.DWORD),
            ("OffsetHigh", wintypes.DWORD),
            ("hEvent", wintypes.HANDLE),
        ]

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _lock_file_ex = _kernel32.LockFileEx
    _lock_file_ex.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(_OVERLAPPED),
    ]
    _lock_file_ex.restype = wintypes.BOOL

    _unlock_file_ex = _kernel32.UnlockFileEx
    _unlock_file_ex.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(_OVERLAPPED),
    ]
    _unlock_file_ex.restype = wintypes.BOOL

    def _handle(fd: int) -> int:
        if hasattr(fd, "fileno"):
            fd = fd.fileno()
        return msvcrt.get_osfhandle(fd)

    def flock(fd: int, operation: int) -> None:
        """Lock the full file, matching the flock operations used by the API."""
        overlapped = _OVERLAPPED()
        handle = _handle(fd)

        if operation & LOCK_UN:
            if not _unlock_file_ex(
                handle, 0, _MAX_DWORD, _MAX_DWORD, ctypes.byref(overlapped)
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            return

        flags = 0
        if operation & LOCK_EX:
            flags |= _LOCKFILE_EXCLUSIVE_LOCK
        elif not operation & LOCK_SH:
            raise ValueError(f"Unsupported flock operation: {operation}")
        if operation & LOCK_NB:
            flags |= _LOCKFILE_FAIL_IMMEDIATELY

        if not _lock_file_ex(
            handle, flags, 0, _MAX_DWORD, _MAX_DWORD, ctypes.byref(overlapped)
        ):
            error = ctypes.get_last_error()
            if error in (32, 33):
                raise BlockingIOError(error, os.strerror(error))
            raise ctypes.WinError(error)