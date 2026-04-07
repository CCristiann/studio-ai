"""Cross-platform IPC transport for the Studio AI FL Studio bridge.

This module hides the platform difference between the Unix and Windows
backends of the Studio AI plugin. The MIDI script imports a single API:

    from ipc_transport import transport
    transport.try_connect()          # call from OnInit / OnIdle until True
    if transport.is_ready():
        chunk = transport.read_available()  # bytes, possibly empty
        ...
        transport.write_response(line)      # bytes, terminated by '\\n'

Backends
========

Unix
    The Rust plugin creates an anonymous pipe pair and `dup2`s the
    FL-facing ends onto fds 20 (commands) and 21 (responses) before this
    script loads. We poll fd 20 with `select.select` and read with
    `os.read`. Writes go to fd 21 with `os.write`.

Windows
    The plugin runs a named-pipe server (`\\\\.\\pipe\\studio-ai-<pid>-cmd`
    and `...-resp`) and writes a small rendezvous file at
    `%LOCALAPPDATA%\\Studio AI\\ipc.json` describing the pipe names. This
    module polls for that file, opens both pipes via `ctypes.CreateFileW`,
    then uses `PeekNamedPipe` for non-blocking polling and `ReadFile` /
    `WriteFile` for the actual I/O. We deliberately avoid `os.read` /
    `os.write` on a `_open_osfhandle` fd because the CRT identity between
    Rust and FL Studio's embedded Python is not guaranteed.

The two backends share the buffering / line-splitting logic in the
caller (`device_studio_ai.py`). They only differ in how raw bytes get
across the process boundary.
"""

import os
import sys

# Platform detection happens at import time so the rest of the file can
# stay branch-free at the call sites.
_IS_WINDOWS = sys.platform == "win32"


# ────────────────────────── Unix backend ──────────────────────────

if not _IS_WINDOWS:
    import select

    _CMD_FD = 20
    _RESP_FD = 21

    class _UnixTransport:
        """Anonymous-pipe-on-fd transport (macOS / Linux)."""

        def __init__(self):
            self._ready = False

        def try_connect(self) -> bool:
            """Probe for the inherited fds. Idempotent."""
            if self._ready:
                return True
            try:
                os.fstat(_CMD_FD)
                os.fstat(_RESP_FD)
            except OSError:
                return False
            self._ready = True
            return True

        def is_ready(self) -> bool:
            return self._ready

        def read_available(self) -> bytes:
            """Non-blocking read. Returns whatever is currently buffered."""
            # select with a 0 timeout is the cleanest way to ask "is there
            # anything to read?" without relying on EAGAIN semantics.
            r, _, _ = select.select([_CMD_FD], [], [], 0)
            if not r:
                return b""
            try:
                return os.read(_CMD_FD, 65536)
            except OSError:
                return b""

        def write_response(self, data: bytes) -> None:
            os.write(_RESP_FD, data)

    transport = _UnixTransport()


# ────────────────────────── Windows backend ──────────────────────────

else:
    import ctypes
    import json
    import time
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    # ── Win32 constant prototypes ────────────────────────────────────
    GENERIC_READ = 0x80000000
    GENERIC_WRITE = 0x40000000
    OPEN_EXISTING = 3
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
    ERROR_PIPE_BUSY = 231

    # ── Function signatures (typed for safety) ───────────────────────
    _CreateFileW = _kernel32.CreateFileW
    _CreateFileW.argtypes = [
        wintypes.LPCWSTR,         # lpFileName
        wintypes.DWORD,           # dwDesiredAccess
        wintypes.DWORD,           # dwShareMode
        ctypes.c_void_p,          # lpSecurityAttributes
        wintypes.DWORD,           # dwCreationDisposition
        wintypes.DWORD,           # dwFlagsAndAttributes
        wintypes.HANDLE,          # hTemplateFile
    ]
    _CreateFileW.restype = wintypes.HANDLE

    _CloseHandle = _kernel32.CloseHandle
    _CloseHandle.argtypes = [wintypes.HANDLE]
    _CloseHandle.restype = wintypes.BOOL

    _PeekNamedPipe = _kernel32.PeekNamedPipe
    _PeekNamedPipe.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
    ]
    _PeekNamedPipe.restype = wintypes.BOOL

    _ReadFile = _kernel32.ReadFile
    _ReadFile.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,          # lpBuffer
        wintypes.DWORD,           # nNumberOfBytesToRead
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,          # lpOverlapped
    ]
    _ReadFile.restype = wintypes.BOOL

    _WriteFile = _kernel32.WriteFile
    _WriteFile.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,          # lpBuffer
        wintypes.DWORD,           # nNumberOfBytesToWrite
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,          # lpOverlapped
    ]
    _WriteFile.restype = wintypes.BOOL

    def _rendezvous_path() -> str:
        local = os.environ.get("LOCALAPPDATA")
        if not local:
            local = os.path.expanduser(r"~\AppData\Local")
            return os.path.join(local, "Studio AI", "ipc.json")
        return os.path.join(local, "Studio AI", "ipc.json")

    class _WindowsTransport:
        """Named-pipe transport (Windows)."""

        def __init__(self):
            self._ready = False
            self._cmd = None    # HANDLE for reading commands (or None)
            self._resp = None   # HANDLE for writing responses (or None)
            self._last_attempt = 0.0

        # ── lifecycle ────────────────────────────────────────────────

        def try_connect(self) -> bool:
            """Read the rendezvous file and open both pipes. Throttled."""
            if self._ready:
                return True

            # Throttle to ~once per second so OnIdle stays cheap.
            now = time.monotonic()
            if now - self._last_attempt < 1.0:
                return False
            self._last_attempt = now

            path = _rendezvous_path()
            try:
                with open(path, "r", encoding="utf-8") as f:
                    info = json.load(f)
            except (OSError, ValueError):
                return False

            cmd_name = info.get("cmd_pipe")
            resp_name = info.get("resp_pipe")
            if not cmd_name or not resp_name:
                return False

            cmd = self._open_pipe(cmd_name)
            if cmd is None:
                return False
            resp = self._open_pipe(resp_name)
            if resp is None:
                _CloseHandle(cmd)
                return False

            self._cmd = cmd
            self._resp = resp
            self._ready = True
            return True

        def is_ready(self) -> bool:
            return self._ready

        # ── I/O ──────────────────────────────────────────────────────

        def read_available(self) -> bytes:
            if not self._ready or self._cmd is None:
                return b""

            # PeekNamedPipe tells us how many bytes are queued without
            # blocking. We then ReadFile exactly that many.
            available = wintypes.DWORD(0)
            ok = _PeekNamedPipe(
                self._cmd, None, 0, None, ctypes.byref(available), None
            )
            if not ok:
                self._mark_disconnected()
                return b""
            n = available.value
            if n == 0:
                return b""

            buf = ctypes.create_string_buffer(n)
            read = wintypes.DWORD(0)
            ok = _ReadFile(self._cmd, buf, n, ctypes.byref(read), None)
            if not ok or read.value == 0:
                self._mark_disconnected()
                return b""
            return buf.raw[: read.value]

        def write_response(self, data: bytes) -> None:
            if not self._ready or self._resp is None:
                return
            written = wintypes.DWORD(0)
            ok = _WriteFile(
                self._resp, data, len(data), ctypes.byref(written), None
            )
            if not ok:
                self._mark_disconnected()

        # ── helpers ──────────────────────────────────────────────────

        @staticmethod
        def _open_pipe(name: str):
            handle = _CreateFileW(
                name,
                GENERIC_READ | GENERIC_WRITE,
                0,        # no sharing
                None,     # default security
                OPEN_EXISTING,
                0,        # no special flags (synchronous)
                None,
            )
            if handle == INVALID_HANDLE_VALUE or handle is None:
                return None
            return handle

        def _mark_disconnected(self) -> None:
            if self._cmd is not None:
                _CloseHandle(self._cmd)
                self._cmd = None
            if self._resp is not None:
                _CloseHandle(self._resp)
                self._resp = None
            self._ready = False

    transport = _WindowsTransport()
