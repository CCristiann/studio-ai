# bridge/fl_studio/tests/test_ipc_transport.py
"""Tests for ipc_transport.py (Unix backend).

We focus on `_UnixTransport.write_response` because a silent partial-write
is one of the two plausible explanations for 'handler prints timing log in
3 ms but plugin still times out after 20 s' — `os.write` on a blocking
pipe can legally return fewer bytes than requested (EINTR, kernel buffer
pressure), and the old implementation just called it once and dropped the
return value.

If the last byte of a response — the newline delimiter the plugin scans
for — never makes it through, the plugin waits for it until the 20 s
deadline. Test first, then fix the transport.
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import ipc_transport  # noqa: E402


@unittest.skipIf(sys.platform == "win32", "Unix transport path only")
class UnixTransportWriteResponseTests(unittest.TestCase):
    def setUp(self):
        self.transport = ipc_transport._UnixTransport()

    def test_writes_all_bytes_when_os_write_returns_partial(self):
        """os.write on a blocking pipe can return fewer bytes than requested.
        The transport must retry with the remaining slice until all bytes
        are written; otherwise the plugin never sees the terminating '\\n'
        and blocks until timeout."""
        data = b"Hello, World!\n"  # 14 bytes
        written = []
        # Successive return values: 5, 5, rest — simulates chunked drain.
        chunks = iter([5, 5, 99])

        def fake_write(fd, buf):
            n = min(next(chunks), len(buf))
            written.append(bytes(buf[:n]))
            return n

        with patch("ipc_transport.os.write", side_effect=fake_write):
            self.transport.write_response(data)

        self.assertEqual(b"".join(written), data)

    def test_retry_advances_buffer_offset(self):
        """A common bug in retry loops is re-writing the same prefix. The
        transport must advance past already-written bytes on each retry."""
        data = b"abcdefghij"  # 10 bytes, no '\n' (test-only)
        seen = []

        def fake_write(fd, buf):
            # Write exactly 3 bytes each call.
            b = bytes(buf[:3])
            seen.append(b)
            return len(b)

        with patch("ipc_transport.os.write", side_effect=fake_write):
            self.transport.write_response(data)

        # Must see disjoint, ordered slices covering the whole payload.
        self.assertEqual(b"".join(seen), data)
        # And the first chunk is the start, not a repeat.
        self.assertEqual(seen[0], b"abc")

    def test_raises_when_os_write_raises(self):
        """If os.write raises (BrokenPipeError etc.), the caller needs to
        see the exception so it can log 'pipe write failed' instead of
        silently dropping the response."""
        with patch("ipc_transport.os.write", side_effect=BrokenPipeError("pipe gone")):
            with self.assertRaises(BrokenPipeError):
                self.transport.write_response(b"x\n")

    def test_single_call_when_os_write_writes_everything(self):
        """Happy path: when the kernel buffer has room, one call suffices.
        Don't spin the loop unnecessarily."""
        data = b"ok\n"
        with patch("ipc_transport.os.write", return_value=len(data)) as mock_w:
            self.transport.write_response(data)
        self.assertEqual(mock_w.call_count, 1)


if __name__ == "__main__":
    unittest.main()
