# bridge/fl_studio/handlers_introspect.py
"""FL Studio bridge — Tier 2 read-only project introspection.

Imported by device_studio_ai.py via:
    from handlers_introspect import INTROSPECT_HANDLERS

Capability detection (§5 of the design spec) gates every version-dependent
FL function. Permissive defaults survive cold-start race where FL modules
have not yet been populated.
"""
import time

# Module-level capability cache. None = unprobed; api_version=0 = probe failed
# (re-probe on next call); api_version>0 = good cache.
_CAPS = None

# Channel-type label map. Codes are stable across FL versions.
_CHANNEL_TYPE_LABELS = {
    0: "sampler",
    1: "hybrid",
    2: "vst",
    3: "midi_out",
    4: "automation",
    5: "layer",
}


def _probe_capabilities():
    """Probe FL Studio module surface once. Returns cached result on
    subsequent calls. On any failure, returns permissive defaults rather
    than raising — the bridge stays up and the agent sees an honest
    'minimal capabilities' view.
    """
    global _CAPS
    if _CAPS is not None and _CAPS.get("api_version", 0) > 0:
        return _CAPS

    fl_version = "unknown"
    api_version = 0
    has = {
        # Floor core (FL 20.7+, API >= 19)
        "channels.getChannelType":    False,
        "plugins.getPluginName":      False,
        "plugins.isValid":            False,
        "mixer.getRouteSendActive":   False,
        "channels.selectedChannel":   False,
        "patterns.patternNumber":     False,
        "mixer.trackNumber":          False,
        # FL 2024+ additions
        "mixer.getRouteToLevel":      False,
        "mixer.getEqGain":            False,
        "mixer.getSlotColor":         False,
        # Other gating
        "general.saveUndo":           False,
        "patterns.getPatternLength":  False,
        "ui.getVersion":              False,
    }
    try:
        import channels
        import mixer
        import patterns
        import plugins
        import general
        import ui
        mods = {"channels": channels, "mixer": mixer, "patterns": patterns,
                "plugins": plugins, "general": general, "ui": ui}
        for key in has:
            # split(".", 1) tolerates future submodule keys like
            # "ui.windows.getVisible"; current keys are all one-dot.
            mod_name, fn_name = key.split(".", 1)
            has[key] = hasattr(mods[mod_name], fn_name)
        try:
            api_version = int(general.getVersion())
        except Exception:
            api_version = 0
        try:
            ver_tuple = ui.getVersion(0) if has["ui.getVersion"] else None
            if isinstance(ver_tuple, (list, tuple)):
                fl_version = ".".join(str(x) for x in ver_tuple)
            else:
                fl_version = str(ver_tuple) if ver_tuple else "unknown"
        except Exception:
            pass
    except Exception:
        # Permissive defaults; everything stays False.
        pass

    _CAPS = {
        "fl_version":         fl_version,
        "api_version":        api_version,
        "has_send_levels":    has["mixer.getRouteToLevel"],
        "has_eq_getters":     has["mixer.getEqGain"],
        "has_save_undo":      has["general.saveUndo"],
        "has_pattern_length": has["patterns.getPatternLength"],
        "has_slot_color":     has["mixer.getSlotColor"],
        "_has_floor_core":    all(has[k] for k in (
            "channels.getChannelType", "plugins.getPluginName",
            "plugins.isValid", "mixer.getRouteSendActive",
            "channels.selectedChannel", "patterns.patternNumber",
            "mixer.trackNumber",
        )),
    }
    return _CAPS


def _cmd_get_capabilities(_params):
    """Internal probe handler. Not exposed as an AI tool — see §4.5 of spec."""
    return _probe_capabilities()


# Handler registry — populated as later tasks add commands.
INTROSPECT_HANDLERS = {
    # Note: get_project_state is NOT yet registered here. Task 9 adds it.
    # The capabilities probe is internal-only (not in the registry).
}
