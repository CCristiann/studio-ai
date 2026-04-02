"""FL Studio action handlers."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def handle_set_bpm(params: dict[str, Any]) -> dict[str, Any]:
    import general
    bpm = params.get("bpm")
    if bpm is None or not (10 <= bpm <= 999):
        raise ValueError(f"Invalid BPM value: {bpm}")
    general.setTempo(int(bpm * 1000))
    return {"bpm": bpm}


async def handle_get_state(params: dict[str, Any]) -> dict[str, Any]:
    import general
    import channels
    import mixer
    import transport
    bpm = general.getTempo() / 1000.0
    tracks = []
    for i in range(mixer.trackCount()):
        name = mixer.getTrackName(i)
        if not name or name == "(instrument)":
            continue
        tracks.append({
            "index": i, "name": name, "type": "audio",
            "muted": bool(mixer.isTrackMuted(i)),
            "solo": bool(mixer.isTrackSolo(i)),
            "volume": round(mixer.getTrackVolume(i), 3),
            "pan": round(mixer.getTrackPan(i), 3),
        })
    project_name = general.getProjectTitle() or "Untitled"
    return {"bpm": bpm, "tracks": tracks, "project_name": project_name}


async def handle_add_track(params: dict[str, Any]) -> dict[str, Any]:
    import channels
    name = params.get("name", "New Track")
    idx = channels.channelCount()
    channels.setChannelName(idx, name)
    return {"index": idx, "name": name}


async def handle_play(params: dict[str, Any]) -> dict[str, Any]:
    import transport
    transport.start()
    return {"playing": True}


async def handle_stop(params: dict[str, Any]) -> dict[str, Any]:
    import transport
    transport.stop()
    return {"playing": False}


async def handle_record(params: dict[str, Any]) -> dict[str, Any]:
    import transport
    transport.record()
    return {"recording": True}


async def handle_set_track_volume(params: dict[str, Any]) -> dict[str, Any]:
    import mixer
    index = params.get("index", 0)
    volume = params.get("volume", 0.8)
    mixer.setTrackVolume(index, volume)
    return {"index": index, "volume": volume}


async def handle_set_track_pan(params: dict[str, Any]) -> dict[str, Any]:
    import mixer
    index = params.get("index", 0)
    pan = params.get("pan", 0.0)
    mixer.setTrackPan(index, pan)
    return {"index": index, "pan": pan}


async def handle_set_track_mute(params: dict[str, Any]) -> dict[str, Any]:
    import mixer
    index = params.get("index", 0)
    muted = params.get("muted", True)
    mixer.muteTrack(index)
    return {"index": index, "muted": muted}


async def handle_set_track_solo(params: dict[str, Any]) -> dict[str, Any]:
    import mixer
    index = params.get("index", 0)
    solo = params.get("solo", True)
    mixer.soloTrack(index)
    return {"index": index, "solo": solo}


async def handle_rename_track(params: dict[str, Any]) -> dict[str, Any]:
    import mixer
    index = params.get("index", 0)
    name = params.get("name", "")
    mixer.setTrackName(index, name)
    return {"index": index, "name": name}


def register_fl_handlers(router) -> None:
    router.register("set_bpm", handle_set_bpm)
    router.register("get_state", handle_get_state)
    router.register("add_track", handle_add_track)
    router.register("play", handle_play)
    router.register("stop", handle_stop)
    router.register("record", handle_record)
    router.register("set_track_volume", handle_set_track_volume)
    router.register("set_track_pan", handle_set_track_pan)
    router.register("set_track_mute", handle_set_track_mute)
    router.register("set_track_solo", handle_set_track_solo)
    router.register("rename_track", handle_rename_track)
