"""Cross-platform IPC transport for the Studio AI FL Studio bridge.

    from ipc_transport import transport
    transport.try_connect()
    if transport.is_ready():
        chunk = transport.read_available()   # bytes, possibly empty
        transport.write_response(line)       # bytes, terminated by '\\n'

Backends
========

Unix
    Anonymous pipes on fds 20/21, polled with select.select.

Windows
    Named pipes discovered via %LOCALAPPDATA%\\Studio AI\\ipc.json.
    Uses _winapi (CPython built-in) for all Win32 calls instead of ctypes.
    _ctypes cannot be loaded in FL Studio's Python subinterpreter (Python
    3.12 restriction), but _winapi is a built-in and works fine — FL Bridge
    uses the same approach.
"""

import os
import sys

_IS_WINDOWS = sys.platform == "win32"


# ────────────────────────── Unix backend ──────────────────────────

if not _IS_WINDOWS:
    import select

    _CMD_FD  = 20
    _RESP_FD = 21

    class _UnixTransport:
        def __init__(self):
            self._ready = False

        def try_connect(self):
            if self._ready:
                return True
            try:
                os.fstat(_CMD_FD)
                os.fstat(_RESP_FD)
            except OSError:
                return False
            self._ready = True
            return True

        def is_ready(self):
            return self._ready

        def read_available(self):
            r, _, _ = select.select([_CMD_FD], [], [], 0)
            if not r:
                return b""
            try:
                return os.read(_CMD_FD, 65536)
            except OSError:
                return b""

        def write_response(self, data):
            os.write(_RESP_FD, data)

    transport = _UnixTransport()


# ────────────────────────── Windows backend ──────────────────────────

else:
    import _winapi
    import time

    # Win32 constants — hardcoded, not from _winapi, to match FL Bridge's
    # approach (FL Studio's _winapi may not export all constants reliably).
    _GENERIC_READ   = 0x80000000
    _GENERIC_WRITE  = 0x40000000
    _OPEN_EXISTING  = 3
    _INVALID_HANDLE = 0xFFFFFFFFFFFFFFFF  # FL Studio returns this, doesn't raise

    def _open_pipe(name, access):
        """Open a named pipe. FL Studio's _winapi.CreateFile returns
        0xFFFFFFFFFFFFFFFF on failure instead of raising OSError."""
        try:
            h = _winapi.CreateFile(name, access, 0, 0, _OPEN_EXISTING, 0, 0)
        except Exception as e:
            print("[Studio AI] _open_pipe exception (" + name + "): " + str(e))
            return None
        if h == _INVALID_HANDLE:
            return None
        return h

    class _WindowsTransport:
        """Named-pipe transport via _winapi.

        Pipe names are PID-based (studio-ai-cmd-<pid> / studio-ai-resp-<pid>).
        Python uses os.getpid() to reconstruct the names — no file I/O needed
        because the plugin and MIDI script share the same FL Studio process.
        This is identical to the FL Bridge approach.
        """

        def __init__(self):
            self._ready = False
            self._cmd  = None
            self._resp = None
            self._last_attempt = 0.0

        def try_connect(self):
            if self._ready:
                return True

            now = time.monotonic()
            if now - self._last_attempt < 1.0:
                return False
            self._last_attempt = now

            pid = os.getpid()

            # Diagnostic: test if CreateNamedPipe works (no PySys_Audit call)
            _PIPE_ACCESS_DUPLEX    = 0x00000003
            _FILE_FLAG_OVERLAPPED  = 0x40000000
            _PIPE_TYPE_BYTE        = 0x00000000
            _PIPE_WAIT             = 0x00000000
            test_name = "\\\\.\\pipe\\studio-ai-test-" + str(pid)
            try:
                th = _winapi.CreateNamedPipe(
                    test_name,
                    _PIPE_ACCESS_DUPLEX,
                    _PIPE_TYPE_BYTE | _PIPE_WAIT,
                    1, 65536, 65536, 0, 0
                )
                if th == _INVALID_HANDLE:
                    err = _winapi.GetLastError()
                    print("[Studio AI] CreateNamedPipe FAILED err=" + str(err))
                else:
                    print("[Studio AI] CreateNamedPipe OK handle=" + str(th))
                    _winapi.CloseHandle(th)
            except Exception as e:
                print("[Studio AI] CreateNamedPipe exception: " + str(e))

            # Also try anonymous pipe (no audit call, no name)
            try:
                r, w = _winapi.CreatePipe(None, 0)
                print("[Studio AI] CreatePipe OK r=" + str(r) + " w=" + str(w))
                _winapi.CloseHandle(r)
                _winapi.CloseHandle(w)
            except Exception as ep:
                print("[Studio AI] CreatePipe exception: " + str(ep))

            cmd_name  = "\\\\.\\pipe\\studio-ai-cmd-"  + str(pid)
            resp_name = "\\\\.\\pipe\\studio-ai-resp-" + str(pid)
            cmd = _open_pipe(cmd_name, _GENERIC_READ)
            if cmd is None:
                return False

            resp = _open_pipe(resp_name, _GENERIC_WRITE)
            if resp is None:
                _winapi.CloseHandle(cmd)
                return False

            self._cmd  = cmd
            self._resp = resp
            self._ready = True
            return True

        def is_ready(self):
            return self._ready

        # ── I/O ──────────────────────────────────────────────────────

        def read_available(self):
            if not self._ready or self._cmd is None:
                return b""
            try:
                # PeekNamedPipe: (data, nAvailBytes, nBytesLeftThisMsg)
                _, avail, _ = _winapi.PeekNamedPipe(self._cmd, 0)
                if avail == 0:
                    return b""
                data, nread = _winapi.ReadFile(self._cmd, min(avail, 65536))
                return data[:nread] if nread > 0 else b""
            except OSError:
                self._mark_disconnected()
                return b""

        def write_response(self, data):
            if not self._ready or self._resp is None:
                return
            try:
                _winapi.WriteFile(self._resp, data)
            except OSError:
                self._mark_disconnected()

        # ── helpers ──────────────────────────────────────────────────

        def _mark_disconnected(self):
            for h in (self._cmd, self._resp):
                if h is not None:
                    try:
                        _winapi.CloseHandle(h)
                    except OSError:
                        pass
            self._cmd  = None
            self._resp = None
            self._ready = False

    transport = _WindowsTransport()
