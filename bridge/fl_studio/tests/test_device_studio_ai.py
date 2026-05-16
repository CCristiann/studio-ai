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
    """OnInit's log must reflect reality at the moment it fires.

    - macOS, plugin already up:  "pipe transport"
    - macOS, plugin not yet up:  "waiting for plugin to open pipe"
    - Windows:                    "MIDI SysEx transport"

    Older code printed "MIDI SysEx" unconditionally when _USE_PIPE was
    False, which hid the macOS startup race: a fresh FL launch sees
    _USE_PIPE=False because the VST plugin hasn't opened fds 20/21 yet,
    so the bridge falsely reported SysEx even though pipe was the right
    transport once the plugin loaded.
    """

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
        # Tests poke _IS_WIN directly — capture original to restore.
        self._orig_is_win = self.mod._IS_WIN

    def tearDown(self):
        self.mod._IS_WIN = self._orig_is_win
        _uninstall_device_mock()
        uninstall_fl_mocks()

    def _call_oninit(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.mod.OnInit()
        return buf.getvalue()

    def test_logs_pipe_when_use_pipe_true(self):
        self.mod._IS_WIN = False
        self.mod._USE_PIPE = True
        out = self._call_oninit()
        self.assertIn("pipe", out.lower())
        self.assertNotIn("sysex", out.lower())

    def test_logs_sysex_when_on_windows(self):
        self.mod._IS_WIN = True
        self.mod._USE_PIPE = False
        out = self._call_oninit()
        self.assertIn("sysex", out.lower())

    def test_logs_waiting_when_unix_and_pipe_not_ready(self):
        """The regression we're fixing: macOS + pipe not yet open must
        not lie about SysEx. The bridge should say it's still waiting,
        so debugging starts from "is the plugin loaded?" instead of
        "why is macOS on the Windows path?"."""
        self.mod._IS_WIN = False
        self.mod._USE_PIPE = False
        fake = _FakeTransport()
        fake.try_connect = lambda: False  # pipe FDs not ready
        self.mod._transport = fake
        out = self._call_oninit()
        self.assertIn("waiting", out.lower())
        self.assertNotIn("sysex", out.lower())


class PipeReadyRetryTests(unittest.TestCase):
    """The whole point of the macOS fix: when the plugin loads AFTER the
    script (the typical flow — script loads at FL startup, plugin loads
    when a project opens), OnIdle must pick up the pipe transport as
    soon as it becomes ready, with no manual script reload."""

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
        self._orig_is_win = self.mod._IS_WIN
        self.mod._IS_WIN = False
        self.mod._USE_PIPE = False

    def tearDown(self):
        self.mod._IS_WIN = self._orig_is_win
        _uninstall_device_mock()
        uninstall_fl_mocks()

    def test_onidle_activates_pipe_when_transport_becomes_ready(self):
        fake = _FakeTransport()
        attempts = {"n": 0}

        def try_connect():
            attempts["n"] += 1
            return attempts["n"] >= 3  # ready on third try

        fake.try_connect = try_connect
        self.mod._transport = fake

        buf = io.StringIO()
        with redirect_stdout(buf):
            self.mod.OnIdle()  # attempt 1 — not ready
            self.assertFalse(self.mod._USE_PIPE)
            self.mod.OnIdle()  # attempt 2 — not ready
            self.assertFalse(self.mod._USE_PIPE)
            self.mod.OnIdle()  # attempt 3 — ready → activate + log
            self.assertTrue(self.mod._USE_PIPE)

        self.assertIn("pipe transport active", buf.getvalue().lower())

    def test_ensure_pipe_ready_is_noop_after_activation(self):
        """Once active, don't keep calling try_connect every tick."""
        fake = _FakeTransport()
        calls = {"n": 0}

        def try_connect():
            calls["n"] += 1
            return True

        fake.try_connect = try_connect
        self.mod._transport = fake
        self.mod._ensure_pipe_ready()  # first call activates
        self.assertTrue(self.mod._USE_PIPE)
        self.assertEqual(calls["n"], 1)

        for _ in range(5):
            self.mod._ensure_pipe_ready()
        self.assertEqual(calls["n"], 1)  # still 1, not retried

    def test_ensure_pipe_ready_is_noop_on_windows(self):
        self.mod._IS_WIN = True
        fake = _FakeTransport()
        calls = {"n": 0}
        fake.try_connect = lambda: (calls.update(n=calls["n"] + 1) or True)
        self.mod._transport = fake
        self.mod._ensure_pipe_ready()
        self.assertFalse(self.mod._USE_PIPE)
        self.assertEqual(calls["n"], 0)


if __name__ == "__main__":
    unittest.main()
