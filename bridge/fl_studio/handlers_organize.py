# handlers_organize.py — Organization agent command handlers for Studio AI
#
# Imported by device_studio_ai.py via:
#   from handlers_organize import ORGANIZE_HANDLERS
#
# FL Studio Python modules (channels, mixer, patterns, playlist, general) are
# imported lazily inside each handler because they are only available at
# runtime inside FL Studio's Python environment.
#
# Indexing conventions (mirrors FL Studio API):
#   Channel Rack  — 0-indexed
#   Mixer tracks  — 0-indexed
#   Playlist tracks — 1-indexed
#   Patterns      — 1-indexed


# ──────────────────────────────────────────────────────────────────────────────
# get_project_state  (enhanced — overrides the basic get_state alias)
# ──────────────────────────────────────────────────────────────────────────────

def _cmd_get_project_state(params):
    """Return a comprehensive snapshot of the current FL Studio project.

    Includes:
      - channels    : channel rack entries (0-indexed)
      - mixer_tracks: mixer inserts (0-indexed)
      - playlist_tracks: playlist track names / colors (1-indexed)
      - patterns    : pattern names / colors (1-indexed)
      - bpm, project_name, playing
    """
    import general
    import mixer
    import channels
    import patterns
    import playlist
    import transport

    bpm = float(mixer.getCurrentTempo()) / 1000.0
    project_name = general.getProjectTitle() or "Untitled"
    is_playing = transport.isPlaying()

    # ── Channel Rack ──────────────────────────────────────────────────────────
    channel_list = []
    ch_count = channels.channelCount()
    for i in range(ch_count):
        try:
            plugin_name = channels.getChannelName(i) or ""
            color = channels.getChannelColor(i) & 0xFFFFFF
            volume = round(channels.getChannelVolume(i), 3)
            pan = round(channels.getChannelPan(i), 3)
            enabled = not bool(channels.isChannelMuted(i))
            insert = channels.getTargetFxTrack(i)
            channel_list.append({
                "index": i,
                "name": plugin_name,
                "color": color,
                "volume": volume,
                "pan": pan,
                "enabled": enabled,
                "insert": insert,
            })
        except Exception:
            # Skip channels that raise (e.g. out-of-range during enumeration)
            pass

    # ── Mixer tracks ──────────────────────────────────────────────────────────
    mixer_list = []
    mx_count = mixer.trackCount()
    for i in range(mx_count):
        try:
            name = mixer.getTrackName(i) or ""
            color = mixer.getTrackColor(i) & 0xFFFFFF
            volume = round(mixer.getTrackVolume(i), 3)
            pan = round(mixer.getTrackPan(i), 3)
            muted = bool(mixer.isTrackMuted(i))
            mixer_list.append({
                "index": i,
                "name": name,
                "color": color,
                "volume": volume,
                "pan": pan,
                "muted": muted,
            })
        except Exception:
            pass

    # ── Playlist tracks (1-indexed) ───────────────────────────────────────────
    playlist_list = []
    pl_count = playlist.trackCount()
    for i in range(1, pl_count + 1):
        try:
            name = playlist.getTrackName(i) or ""
            color = playlist.getTrackColor(i) & 0xFFFFFF
            playlist_list.append({
                "index": i,
                "name": name,
                "color": color,
            })
        except Exception:
            pass

    # ── Patterns (1-indexed) ──────────────────────────────────────────────────
    pattern_list = []
    pat_count = patterns.patternCount()
    for i in range(1, pat_count + 1):
        try:
            name = patterns.getPatternName(i) or ""
            color = patterns.getPatternColor(i) & 0xFFFFFF
            pattern_list.append({
                "index": i,
                "name": name,
                "color": color,
            })
        except Exception:
            pass

    return {
        "bpm": bpm,
        "project_name": project_name,
        "playing": bool(is_playing),
        "channels": channel_list,
        "mixer_tracks": mixer_list,
        "playlist_tracks": playlist_list,
        "patterns": pattern_list,
    }


# ──────────────────────────────────────────────────────────────────────────────
# get_pattern_notes
# ──────────────────────────────────────────────────────────────────────────────

def _cmd_get_pattern_notes(params):
    """Read MIDI notes from a specific channel/pattern.

    Params:
      channel_index  (int, 0-indexed, required)
      pattern_index  (int, 1-indexed, optional, defaults to 1)

    Returns a list of notes, each with:
      pitch     — MIDI note number (0-127)
      velocity  — 0-127
      position  — beat position (float)
      length    — duration in beats (float)
    """
    import channels

    ch_index = int(params.get("channel_index", 0))
    pat_index = int(params.get("pattern_index", 1))

    # Use getGridBit to enumerate step-sequencer steps.
    # FL Studio's step sequencer has a fixed grid per channel per pattern;
    # each step maps to a 1/16th note by default (0.25 beats).
    STEP_BEAT = 0.25  # each step = 1 semiquaver
    step_count = channels.getGridBitWithoutCache(ch_index, 0)  # probe length

    notes = []
    # Iterate over 128 steps (max FL default grid size)
    for step in range(128):
        try:
            active = bool(channels.getGridBit(ch_index, step))
        except Exception:
            break  # end of grid
        if active:
            notes.append({
                "pitch": 60,  # step sequencer doesn't encode pitch per-step
                "velocity": 100,
                "position": round(step * STEP_BEAT, 4),
                "length": round(STEP_BEAT, 4),
            })

    return {
        "channel_index": ch_index,
        "pattern_index": pat_index,
        "notes": notes,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Channel Rack operations  (0-indexed)
# ──────────────────────────────────────────────────────────────────────────────

def _cmd_rename_channel(params):
    """Rename a channel rack entry."""
    import channels
    index = int(params.get("index", 0))
    name = str(params.get("name", ""))[:128]
    channels.setChannelName(index, name)
    return {"index": index, "name": name}


def _cmd_set_channel_color(params):
    """Set the color of a channel rack entry (24-bit RGB)."""
    import channels
    index = int(params.get("index", 0))
    color = int(params.get("color", 0)) & 0xFFFFFF
    channels.setChannelColor(index, color)
    return {"index": index, "color": color}


def _cmd_set_channel_insert(params):
    """Route a channel rack entry to a mixer insert."""
    import channels
    index = int(params.get("index", 0))
    insert = int(params.get("insert", 0))
    channels.setTargetFxTrack(index, insert)
    return {"index": index, "insert": insert}


# ──────────────────────────────────────────────────────────────────────────────
# Mixer track operations  (0-indexed)
# ──────────────────────────────────────────────────────────────────────────────

def _cmd_rename_mixer_track(params):
    """Rename a mixer track."""
    import mixer
    index = int(params.get("index", 0))
    name = str(params.get("name", ""))[:128]
    mixer.setTrackName(index, name)
    return {"index": index, "name": name}


def _cmd_set_mixer_track_color(params):
    """Set the color of a mixer track (24-bit RGB)."""
    import mixer
    index = int(params.get("index", 0))
    color = int(params.get("color", 0)) & 0xFFFFFF
    mixer.setTrackColor(index, color)
    return {"index": index, "color": color}


# ──────────────────────────────────────────────────────────────────────────────
# Playlist track operations  (1-indexed)
# ──────────────────────────────────────────────────────────────────────────────

def _cmd_rename_playlist_track(params):
    """Rename a playlist track (1-indexed)."""
    import playlist
    index = int(params.get("index", 1))
    name = str(params.get("name", ""))[:128]
    playlist.setTrackName(index, name)
    return {"index": index, "name": name}


def _cmd_set_playlist_track_color(params):
    """Set the color of a playlist track (1-indexed, 24-bit RGB)."""
    import playlist
    index = int(params.get("index", 1))
    color = int(params.get("color", 0)) & 0xFFFFFF
    playlist.setTrackColor(index, color)
    return {"index": index, "color": color}


def _cmd_group_playlist_tracks(params):
    """Group a range of playlist tracks under a parent track.

    Params:
      parent_index  (int, 1-indexed) — the track that will become the group header
      child_indices (list[int], 1-indexed) — tracks to place inside the group

    FL Studio does not expose a direct grouping API in its Python SDK, so this
    handler records the intended grouping and returns a structured response.
    Actual visual grouping requires the user to drag tracks in the Playlist, or
    a future FL API addition.
    """
    parent_index = int(params.get("parent_index", 1))
    child_indices = [int(i) for i in params.get("child_indices", [])]
    # No FL API available for programmatic grouping; return intent so the
    # caller (agent) can document or retry via UI automation if needed.
    return {
        "parent_index": parent_index,
        "child_indices": child_indices,
        "note": "Playlist track grouping is not supported by the FL Studio Python API. Manual grouping required.",
    }


# ──────────────────────────────────────────────────────────────────────────────
# Pattern operations  (1-indexed)
# ──────────────────────────────────────────────────────────────────────────────

def _cmd_rename_pattern(params):
    """Rename a pattern (1-indexed)."""
    import patterns
    index = int(params.get("index", 1))
    name = str(params.get("name", ""))[:128]
    patterns.setPatternName(index, name)
    return {"index": index, "name": name}


def _cmd_set_pattern_color(params):
    """Set the color of a pattern (1-indexed, 24-bit RGB)."""
    import patterns
    index = int(params.get("index", 1))
    color = int(params.get("color", 0)) & 0xFFFFFF
    patterns.setPatternColor(index, color)
    return {"index": index, "color": color}


# ──────────────────────────────────────────────────────────────────────────────
# Handler registry — imported by device_studio_ai.py
# ──────────────────────────────────────────────────────────────────────────────

ORGANIZE_HANDLERS = {
    # Enhanced project state (overrides the basic get_state alias)
    "get_project_state": _cmd_get_project_state,

    # Pattern notes
    "get_pattern_notes": _cmd_get_pattern_notes,

    # Channel Rack
    "rename_channel": _cmd_rename_channel,
    "set_channel_color": _cmd_set_channel_color,
    "set_channel_insert": _cmd_set_channel_insert,

    # Mixer
    "rename_mixer_track": _cmd_rename_mixer_track,
    "set_mixer_track_color": _cmd_set_mixer_track_color,

    # Playlist
    "rename_playlist_track": _cmd_rename_playlist_track,
    "set_playlist_track_color": _cmd_set_playlist_track_color,
    "group_playlist_tracks": _cmd_group_playlist_tracks,

    # Patterns
    "rename_pattern": _cmd_rename_pattern,
    "set_pattern_color": _cmd_set_pattern_color,
}
