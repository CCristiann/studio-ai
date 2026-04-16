# bridge/fl_studio/tests/test_device_studio_ai.py
"""Unit tests for device_studio_ai.py bridge glue.

Why this file exists
--------------------
We observed a reproducible failure on macOS where:
  1. handlers_organize._cmd_get_project_state logs total=0.003 s (handler is fast)
  2. The plugin nonetheless times out after 20 s waiting for a response.

All the code between "handler returns" and "bytes reach the plugin" lives in
`_send_pipe_response`. If that call fails silently — or succeeds but writes
fewer bytes than expected — the plugin sits blocked on the read side until
the deadline fires. Making _send_pipe_response's I/O observable in Script
Output is the only way to narrow this down the next time it reproduces.
"""
import io
import json
import os
import sys
import types
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from conftest import install_fl_mocks, uninstall_fl_mocks  # noqa: E402


def _install_device_mock():
    """device_studio_ai imports `device` at module top-level. Fake it."""
    dev = types.ModuleType("device")
    dev.midiOutSysex = lambda _payload: None
    sys.modules["device"] = dev


def _uninstall_device_mock():
    sys.modules.pop("device", None)


class _FakeTransport:
    """Spy transport: records write_response calls and can simulate failures."""

    def __init__(self):
        self.writes = []
        self.raise_on_write = None  # set to an exception instance to raise

    def try_connect(self):
        return True

    def is_ready(self):
        return True

    def read_available(self):
        return b""

    def write_response(self, data):
        self.writes.append(bytes(data))
        if self.raise_on_write is not None:
            raise self.raise_on_write


class SendPipeResponseTests(unittest.TestCase):
    def setUp(self):
        self.fl_mocks = install_fl_mocks()
        _install_device_mock()
        import importlib
        # Reload the module chain so mocks are observed.
        for m in ("_protocol", "ipc_transport", "handlers_organize",
                  "handlers_bulk", "device_studio_ai"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import device_studio_ai
        self.mod = device_studio_ai
        self.transport = _FakeTransport()
        self.mod._transport = self.transport  # swap in the spy

    def tearDown(self):
        _uninstall_device_mock()
        uninstall_fl_mocks()

    def _call_send(self, cmd_id, success, data):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.mod._send_pipe_response(cmd_id, success, data)
        return buf.getvalue()

    # ── diagnostic log contract ────────────────────────────────────────────

    def test_logs_payload_size(self):
        """Without the size logged, we can't tell on the next reproducer
        whether the payload was ~22 KB (expected) or 500 KB (filter bug)."""
        out = self._call_send("abc-123", True, {"k": "v"})
        self.assertRegex(out, r"size=\d+B")

    def test_logs_ok_after_successful_write(self):
        """If we don't log success, 'plugin timeout with no bridge log'
        is ambiguous: did the write succeed silently, or did the handler
        never reach _send_pipe_response at all?"""
        out = self._call_send("abc-123", True, {"k": "v"})
        self.assertIn("pipe write OK", out)

    def test_logs_failure_when_transport_raises(self):
        """Exceptions from write_response must surface in Script Output,
        with the exception string, or we have no explanation for
        'handler completes but plugin times out'."""
        self.transport.raise_on_write = BrokenPipeError("plugin detached")
        out = self._call_send("abc-123", True, {"k": "v"})
        self.assertIn("pipe write failed", out)
        self.assertIn("plugin detached", out)

    def test_does_not_log_ok_when_write_failed(self):
        """Don't print success + failure for the same call — that would
        make Script Output actively misleading."""
        self.transport.raise_on_write = BrokenPipeError("x")
        out = self._call_send("abc-123", True, {"k": "v"})
        self.assertNotIn("pipe write OK", out)

    # ── payload format regression ──────────────────────────────────────────

    def test_payload_ends_with_newline(self):
        """Plugin's read loop frames responses on '\\n'. A missing newline
        means the plugin waits forever."""
        self._call_send("abc-123", True, {"k": "v"})
        self.assertEqual(len(self.transport.writes), 1)
        self.assertTrue(self.transport.writes[0].endswith(b"\n"))

    def test_payload_is_valid_json_with_expected_fields(self):
        self._call_send("abc-123", True, {"k": "v"})
        line = self.transport.writes[0].rstrip(b"\n").decode("utf-8")
        obj = json.loads(line)
        self.assertEqual(obj["id"], "abc-123")
        self.assertEqual(obj["success"], True)
        self.assertEqual(obj["data"], {"k": "v"})


class OnInitTransportLabelTests(unittest.TestCase):
    """OnInit used to print 'MIDI SysEx transport' unconditionally, which
    is wrong on macOS (pipe transport is active there). A stale label
    hides the most basic diagnostic: 'which transport am I actually on?'."""

    def setUp(self):
        install_fl_mocks()
        _install_device_mock()
        import importlib
        for m in ("_protocol", "ipc_transport", "handlers_organize",
                  "handlers_bulk", "device_studio_ai"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import device_studio_ai
        self.mod = device_studio_ai

    def tearDown(self):
        _uninstall_device_mock()
        uninstall_fl_mocks()

    def _call_oninit(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.mod.OnInit()
        return buf.getvalue()

    def test_logs_pipe_when_use_pipe_true(self):
        self.mod._USE_PIPE = True
        out = self._call_oninit()
        self.assertIn("pipe", out.lower())
        self.assertNotIn("sysex", out.lower())

    def test_logs_sysex_when_use_pipe_false(self):
        self.mod._USE_PIPE = False
        out = self._call_oninit()
        self.assertIn("sysex", out.lower())
        self.assertNotIn("pipe", out.lower())


if __name__ == "__main__":
    unittest.main()
