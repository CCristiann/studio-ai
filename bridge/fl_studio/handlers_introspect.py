# bridge/fl_studio/handlers_introspect.py
"""FL Studio bridge — Tier 2 read-only project introspection.

Imported by device_studio_ai.py via:
    from handlers_introspect import INTROSPECT_HANDLERS

Capability detection (§5 of the design spec) gates every version-dependent
FL function. Permissive defaults survive cold-start race where FL modules
have not yet been populated.
"""
import re
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

# Hard caps per spec §6.2
MAX_CHANNELS_INTROSPECTED        = 256
MAX_PATTERNS                     = 256
MAX_PLAYLIST_TRACKS              = 256
MAX_RETAINED_INSERTS_FOR_ROUTING = 100


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


def _channel_plugin(idx):
    """Return {name, type, type_label} for a channel, or None on error."""
    import channels
    import plugins
    try:
        type_code = int(channels.getChannelType(idx))
    except Exception:
        return None
    try:
        plugin_name = plugins.getPluginName(idx, -1) or ""
    except Exception:
        plugin_name = ""
    return {
        "name":       plugin_name,
        "type":       type_code,
        "type_label": _CHANNEL_TYPE_LABELS.get(type_code, "unknown"),
    }


def _mixer_routes(src):
    """Return list of {to_index, level?} for outbound sends from src.

    Excludes self-route. Level is included only when caps.has_send_levels
    is true. Per-call exceptions are caught so a single bad pair doesn't
    abort the sweep.
    """
    import mixer
    caps = _probe_capabilities()
    sends = []
    track_count = mixer.trackCount()
    for dst in range(track_count):
        if dst == src:
            continue
        try:
            if not bool(mixer.getRouteSendActive(src, dst)):
                continue
        except Exception:
            continue
        entry = {"to_index": dst}
        if caps["has_send_levels"]:
            try:
                entry["level"] = round(float(mixer.getRouteToLevel(src, dst)), 3)
            except Exception:
                pass
        sends.append(entry)
    return sends


def _mixer_slot_count(track):
    """Return # of loaded effect slots on `track` (0..10).

    Uses `continue` (not `break`) on per-slot exceptions: a single
    misbehaving slot must not silently undercount the rest of the chain.
    """
    import plugins
    n = 0
    for slot in range(10):
        try:
            if bool(plugins.isValid(track, slot)):
                n += 1
        except Exception:
            continue
    return n


def _selection():
    """Return current selection state. Reads three FL functions sequentially
    without locking; per-field exceptions degrade individual fields to None.
    NOT a transactional snapshot — see spec §4.1 caveat.
    """
    import channels
    import patterns
    import mixer
    sel = {"channel_index": None, "pattern_index": None, "mixer_track_index": None}
    try:
        sel["channel_index"] = int(channels.selectedChannel())
    except Exception:
        pass
    try:
        sel["pattern_index"] = int(patterns.patternNumber())
    except Exception:
        pass
    try:
        sel["mixer_track_index"] = int(mixer.trackNumber())
    except Exception:
        pass
    return sel


# ────────────────────────────────────────────────────────────────────
# get_project_state — extended with plugin identity, routing, slot
# counts, pattern length, selection, capabilities.
# ────────────────────────────────────────────────────────────────────

def _is_default_mixer_name(name, idx):
    if not name:
        return True
    if idx == 0 and name == "Master":
        return False
    # Match exactly "Insert N" (digit-only suffix) — "Insert 1X" is a custom name.
    return bool(re.match(r"^Insert \d+$", name)) or name == "Current"


def _is_default_playlist_name(name):
    return not name or name.startswith("Track ")


def _is_default_pattern_name(name):
    return not name or name.startswith("Pattern ")


def _sample_default_color(getter, start, end, samples=5):
    """Sample the trailing slots to learn the per-theme 'untouched' color."""
    if end < start:
        return 0
    lo = max(start, end - samples + 1)
    counts = {}
    for i in range(lo, end + 1):
        try:
            c = getter(i) & 0xFFFFFF
            counts[c] = counts.get(c, 0) + 1
        except Exception:
            continue
    if not counts:
        return 0
    return max(counts.items(), key=lambda kv: kv[1])[0]


def _cmd_get_project_state(params):
    """Extended project state with plugin identity, routing, slot counts,
    pattern length, selection state, and capabilities.

    Params:
      include_routing (bool, default True): if false, skip mixer routing
        sweep entirely (routes_to: [] for every track).

    Hard caps (see spec §6.2):
      MAX_CHANNELS_INTROSPECTED, MAX_PATTERNS, MAX_PLAYLIST_TRACKS,
      MAX_RETAINED_INSERTS_FOR_ROUTING. Truncation surfaces in
      `truncated_sections`.
    """
    caps = _probe_capabilities()
    if not caps["_has_floor_core"]:
        return {
            "success": False,
            "error":   "FL_VERSION_UNSUPPORTED",
            "fl_version":  caps["fl_version"],
            "api_version": caps["api_version"],
        }

    include_routing = bool((params or {}).get("include_routing", True))

    import general
    import mixer
    import channels
    import patterns
    import playlist
    import transport

    truncated_sections = []
    routing_swept_through = None

    t0 = time.time()
    bpm = float(mixer.getCurrentTempo()) / 1000.0
    project_name = general.getProjectTitle() or "Untitled"
    is_playing = bool(transport.isPlaying())

    # ── Channels (cap at MAX_CHANNELS_INTROSPECTED) ───────────────
    channel_list = []
    ch_count_total = channels.channelCount()
    ch_count = min(ch_count_total, MAX_CHANNELS_INTROSPECTED)
    for i in range(ch_count):
        try:
            channel_list.append({
                "index":   i,
                "name":    channels.getChannelName(i) or "",
                "color":   channels.getChannelColor(i) & 0xFFFFFF,
                "volume":  round(channels.getChannelVolume(i), 3),
                "pan":     round(channels.getChannelPan(i), 3),
                "enabled": not bool(channels.isChannelMuted(i)),
                "insert":  channels.getTargetFxTrack(i),
                "plugin":  _channel_plugin(i),
            })
        except Exception:
            pass
    if ch_count_total > ch_count:
        truncated_sections.append("channels")

    # ── Mixer: pass 1 — filter retain set without routing ─────────
    mixer_list = []
    mx_count = mixer.trackCount()
    mx_default_color = _sample_default_color(
        mixer.getTrackColor, 1, mx_count - 1
    ) if mx_count > 1 else 0
    retained_for_routing = []   # cheap-retained tracks; cap applies here
    route_only_candidates = []  # bare tracks (no name/color/slots); checked for
                                # outbound routes regardless of cap
    track_data = {}             # {index: {entry dict}} for pass-2 augmentation
    for i in range(mx_count):
        try:
            name = mixer.getTrackName(i) or ""
            color = mixer.getTrackColor(i) & 0xFFFFFF
            slot_count = _mixer_slot_count(i)
            # Retain decision uses cheap signals first; routing-based retention
            # is computed in pass 2 if include_routing.
            retain_by_cheap = (
                i == 0  # Master always
                or not _is_default_mixer_name(name, i)
                or color not in (0, mx_default_color)
                or slot_count > 0
            )
            entry = {
                "index":      i,
                "name":       name,
                "color":      color,
                "volume":     round(mixer.getTrackVolume(i), 3),
                "pan":        round(mixer.getTrackPan(i), 3),
                "muted":      bool(mixer.isTrackMuted(i)),
                "slot_count": slot_count,
                "routes_to":  [],   # filled in pass 2
            }
            track_data[i] = entry
            if retain_by_cheap:
                mixer_list.append(entry)
                retained_for_routing.append(i)
            elif include_routing and i != 0:
                # Bare track: could still be retained if it has outbound routes.
                # Add as a route-only candidate (checked in pass 2 separately
                # from the cap, since these tracks have no other retention reason).
                route_only_candidates.append(i)
        except Exception:
            pass

    # ── Mixer: pass 2 — routing sweep (if enabled, with cap) ──────
    if include_routing:
        # Cap applies to cheap-retained tracks only.
        if len(retained_for_routing) > MAX_RETAINED_INSERTS_FOR_ROUTING:
            truncated_sections.append("routing")
            sweep_indices = retained_for_routing[:MAX_RETAINED_INSERTS_FOR_ROUTING]
            routing_swept_through = sweep_indices[-1] if sweep_indices else None
        else:
            sweep_indices = retained_for_routing
        sweep_set = set(sweep_indices)
        for entry in mixer_list:
            if entry["index"] in sweep_set:
                entry["routes_to"] = _mixer_routes(entry["index"])
        # Second filter pass: a track that passed pass-1 by being non-default
        # but had no routing/slots/name/color may now have outbound routes that
        # the user explicitly set up. We keep tracks whose retained reason is
        # any of: master, custom name, custom color, slots, or routes.
        survivors = []
        for entry in mixer_list:
            if (entry["index"] == 0
                    or not _is_default_mixer_name(entry["name"], entry["index"])
                    or entry["color"] not in (0, mx_default_color)
                    or entry["slot_count"] > 0
                    or len(entry["routes_to"]) > 0):
                survivors.append(entry)
        mixer_list = survivors
        # Route-only candidates: check routes and add to mixer_list if non-empty.
        for i in route_only_candidates:
            try:
                routes = _mixer_routes(i)
                if routes:
                    entry = track_data[i]
                    entry["routes_to"] = routes
                    mixer_list.append(entry)
            except Exception:
                pass
        # Re-sort mixer_list by index (route-only additions may be out of order).
        mixer_list.sort(key=lambda e: e["index"])

    # ── Playlist tracks ──────────────────────────────────────────
    playlist_list = []
    pl_count = playlist.trackCount()
    pl_default_color = _sample_default_color(playlist.getTrackColor, 1, pl_count)
    for i in range(1, pl_count + 1):
        if len(playlist_list) >= MAX_PLAYLIST_TRACKS:
            truncated_sections.append("playlist_tracks")
            break
        try:
            name = playlist.getTrackName(i) or ""
            color = playlist.getTrackColor(i) & 0xFFFFFF
            if _is_default_playlist_name(name) and color in (0, pl_default_color):
                continue
            playlist_list.append({"index": i, "name": name, "color": color})
        except Exception:
            pass

    # ── Patterns ─────────────────────────────────────────────────
    pattern_list = []
    pat_count = patterns.patternCount()
    pat_default_color = _sample_default_color(patterns.getPatternColor, 1, pat_count)
    for i in range(1, pat_count + 1):
        if len(pattern_list) >= MAX_PATTERNS:
            truncated_sections.append("patterns")
            break
        try:
            name = patterns.getPatternName(i) or ""
            color = patterns.getPatternColor(i) & 0xFFFFFF
            if _is_default_pattern_name(name) and color in (0, pat_default_color):
                continue
            entry = {"index": i, "name": name, "color": color}
            if caps["has_pattern_length"]:
                try:
                    entry["length_beats"] = int(patterns.getPatternLength(i))
                except Exception:
                    pass
            pattern_list.append(entry)
        except Exception:
            pass

    elapsed = time.time() - t0
    marker = ""
    if elapsed > 18.0:
        marker = " !!! NEAR-TIMEOUT"
    elif elapsed > 10.0:
        marker = " !! SLOW"
    print(
        "[Studio AI] get_project_state: "
        "channels={} mixer={} playlist={} patterns={} "
        "elapsed={:.3f}s{}".format(
            len(channel_list), len(mixer_list),
            len(playlist_list), len(pattern_list),
            elapsed, marker,
        )
    )

    response = {
        "bpm":             bpm,
        "project_name":    project_name,
        "playing":         is_playing,
        "channels":        channel_list,
        "mixer_tracks":    mixer_list,
        "playlist_tracks": playlist_list,
        "patterns":        pattern_list,
        "selection":       _selection(),
        "capabilities":    {k: v for k, v in caps.items() if not k.startswith("_")},
        "snapshot_at":     int(time.time()),
    }
    if truncated_sections:
        response["truncated_sections"] = sorted(set(truncated_sections))
    if routing_swept_through is not None:
        response["routing_swept_through"] = routing_swept_through
    return response


# Handler registry — get_project_state registered by Task 9.
# The capabilities probe is internal-only (not in the registry).
INTROSPECT_HANDLERS = {}

# Register so device_studio_ai.py picks it up after Task 14 wires the dict.
INTROSPECT_HANDLERS["get_project_state"] = _cmd_get_project_state
