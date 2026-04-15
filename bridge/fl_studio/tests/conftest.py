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

    def saveUndo(label, flags=0):
        mod.calls.append(("saveUndo", label, flags))
        if mod._save_undo_should_raise:
            raise RuntimeError("simulated FL refusal")

    def undoUp():
        mod.calls.append(("undoUp",))

    def saveProject(mode):
        mod.calls.append(("saveProject", mode))

    def getProjectTitle():
        return "TestProject"

    def processRECEvent(event_id, value, flags):
        mod.calls.append(("processRECEvent", event_id, value, flags))

    mod.saveUndo = saveUndo
    mod.undoUp = undoUp
    mod.saveProject = saveProject
    mod.getProjectTitle = getProjectTitle
    mod.processRECEvent = processRECEvent
    return mod


def _make_channels_mock():
    mod = types.ModuleType("channels")
    mod.names = {}        # {index: name}
    mod.colors = {}       # {index: int}
    mod.inserts = {}      # {index: int}
    mod.muted = {}        # {index: bool}
    mod.calls = []

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
    return mod


def _make_mixer_mock():
    mod = types.ModuleType("mixer")
    mod.names = {}
    mod.colors = {}
    mod.calls = []
    mod._track_count = 127  # FL 20+ default

    def trackCount():
        return mod._track_count

    def getTrackName(i):
        return mod.names.get(i, "")

    def setTrackName(i, name):
        mod.calls.append(("setTrackName", i, name))
        mod.names[i] = name

    def getTrackColor(i):
        return mod.colors.get(i, 0)

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
    return mod


def _make_playlist_mock():
    mod = types.ModuleType("playlist")
    mod.names = {}        # 1-indexed
    mod.colors = {}       # 1-indexed
    mod.calls = []
    mod._track_count = 500

    def trackCount():
        return mod._track_count

    def getTrackName(i):
        return mod.names.get(i, "")

    def setTrackName(i, name):
        mod.calls.append(("setTrackName", i, name))
        mod.names[i] = name

    def getTrackColor(i):
        return mod.colors.get(i, 0)

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

    def patternCount():
        return mod._pattern_count

    def getPatternName(i):
        return mod.names.get(i, "")

    def setPatternName(i, name):
        mod.calls.append(("setPatternName", i, name))
        mod.names[i] = name

    def getPatternColor(i):
        return mod.colors.get(i, 0)

    def setPatternColor(i, color):
        mod.calls.append(("setPatternColor", i, color))
        mod.colors[i] = color

    mod.patternCount = patternCount
    mod.getPatternName = getPatternName
    mod.setPatternName = setPatternName
    mod.getPatternColor = getPatternColor
    mod.setPatternColor = setPatternColor
    return mod


def install_fl_mocks():
    """Install fresh FL module mocks for one test. Returns dict for assertions."""
    mocks = {
        "general": _make_general_mock(),
        "channels": _make_channels_mock(),
        "mixer": _make_mixer_mock(),
        "playlist": _make_playlist_mock(),
        "patterns": _make_patterns_mock(),
    }
    for name, mod in mocks.items():
        sys.modules[name] = mod
    # Also a stub midi module since handlers_organize uses it
    midi_mod = types.ModuleType("midi")
    midi_mod.REC_MainPitch = 0
    midi_mod.REC_Tempo = 1
    midi_mod.REC_Control = 2
    midi_mod.REC_UpdateControl = 4
    sys.modules["midi"] = midi_mod
    sys.modules["transport"] = types.ModuleType("transport")
    sys.modules["transport"].isPlaying = lambda: False
    return mocks


def uninstall_fl_mocks():
    """Remove all FL module mocks (and stubs) from sys.modules."""
    for name in ("general", "channels", "mixer", "playlist", "patterns", "midi", "transport"):
        sys.modules.pop(name, None)
