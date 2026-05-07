# bridge/fl_studio/tests/conftest.py
"""Shared test scaffolding: fake FL Studio modules.

Imported automatically by pytest. Even if you run unittest directly,
import this file at the top of each test module.

Each fake exposes the subset of the real FL API that handlers_bulk.py
and handlers_organize.py call. Tests can replace any attribute on the
fake to simulate specific FL state or to assert calls.
"""
import sys
import types


def _make_general_mock():
    mod = types.ModuleType("general")
    mod.calls = []  # ordered call log
    mod._save_undo_supported = True
    mod._save_undo_should_raise = False
    mod._api_version = 36   # FL 2024 default for tests

    def saveUndo(label, flags=0):
        mod.calls.append(("saveUndo", label, flags))
        if mod._save_undo_should_raise:
            raise RuntimeError("simulated FL refusal")

    def undoUp():
        mod.calls.append(("undoUp",))

    def getProjectTitle():
        return "TestProject"

    def processRECEvent(event_id, value, flags):
        mod.calls.append(("processRECEvent", event_id, value, flags))

    def getVersion():
        return int(mod._api_version)

    mod.saveUndo = saveUndo
    mod.undoUp = undoUp
    mod.getProjectTitle = getProjectTitle
    mod.processRECEvent = processRECEvent
    mod.getVersion = getVersion
    return mod


def _make_channels_mock():
    mod = types.ModuleType("channels")
    mod.names = {}        # {index: name}
    mod.colors = {}       # {index: int}
    mod.inserts = {}      # {index: int}
    mod.muted = {}        # {index: bool}
    mod.calls = []
    mod.types = {}              # {index: int channel-type code}
    mod._selected_channel = 0

    def channelCount():
        return len(mod.names)

    def getChannelName(i):
        return mod.names.get(i, "")

    def setChannelName(i, name):
        mod.calls.append(("setChannelName", i, name))
        mod.names[i] = name

    def getChannelColor(i):
        return mod.colors.get(i, 0)

    def setChannelColor(i, color):
        mod.calls.append(("setChannelColor", i, color))
        mod.colors[i] = color

    def setTargetFxTrack(i, insert):
        mod.calls.append(("setTargetFxTrack", i, insert))
        mod.inserts[i] = insert

    def getTargetFxTrack(i):
        return mod.inserts.get(i, 0)

    def isChannelMuted(i):
        return mod.muted.get(i, False)

    def muteChannel(i):
        mod.calls.append(("muteChannel", i))
        mod.muted[i] = not mod.muted.get(i, False)

    def getChannelVolume(i):
        return 0.78

    def setChannelVolume(i, v):
        mod.calls.append(("setChannelVolume", i, v))

    def getChannelPan(i):
        return 0.0

    def setChannelPan(i, p):
        mod.calls.append(("setChannelPan", i, p))

    def getGridBit(i, step):
        return 0

    def getGridBitWithoutCache(i, step):
        return 0

    def getChannelType(i):
        return int(mod.types.get(i, 2))   # default to "vst"

    def selectedChannel():
        return int(mod._selected_channel)

    mod.channelCount = channelCount
    mod.getChannelName = getChannelName
    mod.setChannelName = setChannelName
    mod.getChannelColor = getChannelColor
    mod.setChannelColor = setChannelColor
    mod.setTargetFxTrack = setTargetFxTrack
    mod.getTargetFxTrack = getTargetFxTrack
    mod.isChannelMuted = isChannelMuted
    mod.muteChannel = muteChannel
    mod.getChannelVolume = getChannelVolume
    mod.setChannelVolume = setChannelVolume
    mod.getChannelPan = getChannelPan
    mod.setChannelPan = setChannelPan
    mod.getGridBit = getGridBit
    mod.getGridBitWithoutCache = getGridBitWithoutCache
    mod.getChannelType  = getChannelType
    mod.selectedChannel = selectedChannel
    return mod


def _make_mixer_mock():
    mod = types.ModuleType("mixer")
    mod.names = {}
    mod.colors = {}
    mod.calls = []
    mod._track_count = 127  # FL 20+ default
    # Real FL returns the theme's default color (a signed int like -10261391 =
    # 0xFF636C71) for uncolored tracks — not 0. Tests override this to simulate
    # the bug reproduction; default stays 0 for backward compatibility with
    # pre-existing tests that assume mask-to-zero for untouched slots.
    mod._default_color = 0
    mod.routes = {}           # {(src, dst): bool}
    mod.route_levels = {}     # {(src, dst): float}
    mod.eq = {}               # {(track, band): {"gain": f, "freq": f, "bw": f}}
    mod.slot_colors = {}      # {(track, slot): int}
    mod.slots_enabled = {}    # {track: bool}
    mod._selected_track = 0

    def trackCount():
        return mod._track_count

    def getTrackName(i):
        return mod.names.get(i, "")

    def setTrackName(i, name):
        mod.calls.append(("setTrackName", i, name))
        mod.names[i] = name

    def getTrackColor(i):
        return mod.colors.get(i, mod._default_color)

    def setTrackColor(i, color):
        mod.calls.append(("setTrackColor", i, color))
        mod.colors[i] = color

    def getCurrentTempo():
        return 128000

    def isTrackMuted(i):
        return False

    def isTrackSolo(i):
        return False

    def getTrackVolume(i):
        return 0.8

    def getTrackPan(i):
        return 0.0

    def setRouteTo(a, b, on):
        mod.calls.append(("setRouteTo", a, b, on))

    def setTrackEQGain(*args):
        mod.calls.append(("setTrackEQGain",) + args)

    def setTrackEQFreq(*args):
        mod.calls.append(("setTrackEQFreq",) + args)

    def setTrackEQBW(*args):
        mod.calls.append(("setTrackEQBW",) + args)

    def getRouteSendActive(src, dst):
        return bool(mod.routes.get((src, dst), False))

    def getRouteToLevel(src, dst):
        return float(mod.route_levels.get((src, dst), 0.8))

    def getEqGain(track, band):
        return float(mod.eq.get((track, band), {"gain": 0.5}).get("gain", 0.5))

    def getEqFrequency(track, band):
        return float(mod.eq.get((track, band), {"freq": 0.5}).get("freq", 0.5))

    def getEqBandwidth(track, band):
        return float(mod.eq.get((track, band), {"bw": 0.5}).get("bw", 0.5))

    def getSlotColor(track, slot):
        return int(mod.slot_colors.get((track, slot), 0))

    def isTrackSlotsEnabled(track):
        return bool(mod.slots_enabled.get(track, True))

    def trackNumber():
        return int(mod._selected_track)

    mod.trackCount = trackCount
    mod.getTrackName = getTrackName
    mod.setTrackName = setTrackName
    mod.getTrackColor = getTrackColor
    mod.setTrackColor = setTrackColor
    mod.getCurrentTempo = getCurrentTempo
    mod.isTrackMuted = isTrackMuted
    mod.isTrackSolo = isTrackSolo
    mod.getTrackVolume = getTrackVolume
    mod.getTrackPan = getTrackPan
    mod.setRouteTo = setRouteTo
    mod.setTrackEQGain = setTrackEQGain
    mod.setTrackEQFreq = setTrackEQFreq
    mod.setTrackEQBW = setTrackEQBW
    mod.getRouteSendActive   = getRouteSendActive
    mod.getRouteToLevel      = getRouteToLevel
    mod.getEqGain            = getEqGain
    mod.getEqFrequency       = getEqFrequency
    mod.getEqBandwidth       = getEqBandwidth
    mod.getSlotColor         = getSlotColor
    mod.isTrackSlotsEnabled  = isTrackSlotsEnabled
    mod.trackNumber          = trackNumber
    return mod


def _make_playlist_mock():
    mod = types.ModuleType("playlist")
    mod.names = {}        # 1-indexed
    mod.colors = {}       # 1-indexed
    mod.calls = []
    mod._track_count = 500
    # See _make_mixer_mock comment: FL returns a theme-default signed int, not 0.
    mod._default_color = 0

    def trackCount():
        return mod._track_count

    def getTrackName(i):
        return mod.names.get(i, "")

    def setTrackName(i, name):
        mod.calls.append(("setTrackName", i, name))
        mod.names[i] = name

    def getTrackColor(i):
        return mod.colors.get(i, mod._default_color)

    def setTrackColor(i, color):
        mod.calls.append(("setTrackColor", i, color))
        mod.colors[i] = color

    mod.trackCount = trackCount
    mod.getTrackName = getTrackName
    mod.setTrackName = setTrackName
    mod.getTrackColor = getTrackColor
    mod.setTrackColor = setTrackColor
    return mod


def _make_patterns_mock():
    mod = types.ModuleType("patterns")
    mod.names = {}        # 1-indexed
    mod.colors = {}       # 1-indexed
    mod.calls = []
    mod._pattern_count = 999
    # See _make_mixer_mock comment: FL returns a theme-default signed int, not 0.
    mod._default_color = 0
    mod.lengths = {}           # {index: int beats}
    mod._selected_pattern = 1

    def patternCount():
        return mod._pattern_count

    def getPatternName(i):
        return mod.names.get(i, "")

    def setPatternName(i, name):
        mod.calls.append(("setPatternName", i, name))
        mod.names[i] = name

    def getPatternColor(i):
        return mod.colors.get(i, mod._default_color)

    def setPatternColor(i, color):
        mod.calls.append(("setPatternColor", i, color))
        mod.colors[i] = color

    def getPatternLength(i):
        return int(mod.lengths.get(i, 0))

    def patternNumber():
        return int(mod._selected_pattern)

    mod.patternCount = patternCount
    mod.getPatternName = getPatternName
    mod.setPatternName = setPatternName
    mod.getPatternColor = getPatternColor
    mod.setPatternColor = setPatternColor
    mod.getPatternLength = getPatternLength
    mod.patternNumber    = patternNumber
    return mod


def _make_plugins_mock():
    """Mock for FL's `plugins` module: tracks per-(target, slot) state.

    Address conventions (matching real FL):
      - Mixer slot plugin: target = mixer track index, slot in 0..9
      - Channel rack plugin: target = channel index, slot = -1
    `valid` defaults to {}, so isValid returns False unless explicitly set.
    """
    mod = types.ModuleType("plugins")
    mod.valid = {}        # {(target, slot): bool}
    mod.names = {}        # {(target, slot): str}
    mod.param_counts = {} # {(target, slot): int}
    mod.param_names = {}  # {(target, slot, param_idx): str}
    mod.param_values = {} # {(target, slot, param_idx): float}
    mod.param_value_strings = {}  # {(target, slot, param_idx): str}
    mod._raise_on_param = set()   # {(target, slot, param_idx)}
    mod._sleep_per_param_s = 0.0  # for time-budget tests
    mod.calls = []

    def isValid(target, slot, useGlobalIndex=False):
        return bool(mod.valid.get((target, slot), False))

    def getPluginName(target, slot, useGlobalIndex=False):
        return mod.names.get((target, slot), "")

    def getParamCount(target, slot, useGlobalIndex=False):
        return int(mod.param_counts.get((target, slot), 0))

    def getParamName(param_idx, target, slot, useGlobalIndex=False):
        if (target, slot, param_idx) in mod._raise_on_param:
            raise RuntimeError("simulated FL param error")
        return mod.param_names.get((target, slot, param_idx), "")

    def getParamValue(param_idx, target, slot, useGlobalIndex=False):
        if mod._sleep_per_param_s:
            import time as _time
            _time.sleep(mod._sleep_per_param_s)
        return float(mod.param_values.get((target, slot, param_idx), 0.0))

    def getParamValueString(param_idx, target, slot, useGlobalIndex=False):
        return mod.param_value_strings.get((target, slot, param_idx), "")

    mod.isValid = isValid
    mod.getPluginName = getPluginName
    mod.getParamCount = getParamCount
    mod.getParamName = getParamName
    mod.getParamValue = getParamValue
    mod.getParamValueString = getParamValueString
    return mod


def _make_ui_mock():
    mod = types.ModuleType("ui")
    mod._fl_version_tuple = (21, 2, 3, 4321)

    def getVersion(mode=0):
        return tuple(mod._fl_version_tuple)

    mod.getVersion = getVersion
    return mod


def install_fl_mocks():
    """Install fresh FL module mocks for one test. Returns dict for assertions."""
    mocks = {
        "general":  _make_general_mock(),
        "channels": _make_channels_mock(),
        "mixer":    _make_mixer_mock(),
        "playlist": _make_playlist_mock(),
        "patterns": _make_patterns_mock(),
        "plugins":  _make_plugins_mock(),
        "ui":       _make_ui_mock(),
    }
    for name, mod in mocks.items():
        sys.modules[name] = mod
    midi_mod = types.ModuleType("midi")
    midi_mod.REC_MainPitch     = 0
    midi_mod.REC_Tempo         = 1
    midi_mod.REC_Control       = 2
    midi_mod.REC_UpdateControl = 4
    sys.modules["midi"] = midi_mod
    sys.modules["transport"] = types.ModuleType("transport")
    sys.modules["transport"].isPlaying = lambda: False
    return mocks


def uninstall_fl_mocks():
    """Remove all FL module mocks (and stubs) from sys.modules."""
    for name in ("general", "channels", "mixer", "playlist", "patterns",
                 "plugins", "ui", "midi", "transport"):
        sys.modules.pop(name, None)
