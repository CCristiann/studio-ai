# bridge/fl_studio/handlers_bulk.py
"""Bulk apply, undo, find-by-name handlers for Studio AI.

Imported by device_studio_ai.py via:
    from handlers_bulk import BULK_HANDLERS

FL Studio Python modules are imported lazily inside each handler because
they're only available at runtime inside FL Studio's Python environment.
"""
import difflib

from handlers_organize import (
    _cmd_rename_channel, _cmd_set_channel_color, _cmd_set_channel_insert,
    _cmd_rename_mixer_track, _cmd_set_mixer_track_color,
    _cmd_rename_playlist_track, _cmd_set_playlist_track_color,
    _cmd_rename_pattern, _cmd_set_pattern_color,
)

UNDO_LABEL = "Studio AI: Organize"
PLAN_ITEM_CAP = 2000              # hard cap to stay under 5s relay timeout
FIND_SCORE_CUTOFF = 0.6           # below this, omit entirely


def _cmd_apply_organization_plan(params):
    """Apply a structured plan in a single FL undo step.

    Returns:
      { applied: {section: count}, errors: [...], undo_label: str,
        undo_grouped: bool, op_count: int }

    `undo_grouped=False` means general.saveUndo was unavailable on this FL
    version — the AI should issue `undo` `op_count` times to fully revert.
    """
    import general

    plan = params or {}

    # Item-cap guardrail before touching FL (5s relay timeout protection).
    total_items = sum(
        len(plan.get(k) or [])
        for k in ("channels", "mixer_tracks", "playlist_tracks", "patterns")
    )
    if total_items > PLAN_ITEM_CAP:
        raise ValueError(
            "PLAN_TOO_LARGE: {} items exceeds {} cap. "
            "Split into smaller batches (each its own undo step).".format(
                total_items, PLAN_ITEM_CAP
            )
        )

    applied = {"channels": 0, "mixer_tracks": 0, "playlist_tracks": 0, "patterns": 0}
    errors = []
    op_count = [0]  # boxed for closure mutation under Py 2/3 stdlib

    # Group everything under a single undo entry IF saveUndo is available.
    undo_grouped = hasattr(general, "saveUndo")
    if undo_grouped:
        try:
            general.saveUndo(UNDO_LABEL, 0)
        except Exception:
            undo_grouped = False  # FL refused; fall back

    def _apply_section(section_key, items, field_handlers):
        for item in items or []:
            try:
                idx = int(item["index"])
            except (KeyError, ValueError, TypeError):
                errors.append({
                    "entity": section_key, "index": -1, "field": "index",
                    "message": "missing or invalid index",
                })
                continue
            touched = False
            for field, handler in field_handlers.items():
                if field in item and item[field] is not None:
                    try:
                        handler({"index": idx, field: item[field]})
                        touched = True
                        op_count[0] += 1
                    except Exception as e:
                        errors.append({
                            "entity": section_key, "index": idx,
                            "field": field, "message": str(e),
                        })
            if touched:
                applied[section_key] += 1

    _apply_section("channels", plan.get("channels"), {
        "name":   lambda p: _cmd_rename_channel({"index": p["index"], "name": p["name"]}),
        "color":  lambda p: _cmd_set_channel_color({"index": p["index"], "color": p["color"]}),
        "insert": lambda p: _cmd_set_channel_insert({"index": p["index"], "insert": p["insert"]}),
    })
    _apply_section("mixer_tracks", plan.get("mixer_tracks"), {
        "name":  lambda p: _cmd_rename_mixer_track({"index": p["index"], "name": p["name"]}),
        "color": lambda p: _cmd_set_mixer_track_color({"index": p["index"], "color": p["color"]}),
    })
    _apply_section("playlist_tracks", plan.get("playlist_tracks"), {
        "name":  lambda p: _cmd_rename_playlist_track({"index": p["index"], "name": p["name"]}),
        "color": lambda p: _cmd_set_playlist_track_color({"index": p["index"], "color": p["color"]}),
    })
    _apply_section("patterns", plan.get("patterns"), {
        "name":  lambda p: _cmd_rename_pattern({"index": p["index"], "name": p["name"]}),
        "color": lambda p: _cmd_set_pattern_color({"index": p["index"], "color": p["color"]}),
    })

    return {
        "applied": applied,
        "errors": errors,
        "undo_label": UNDO_LABEL,
        "undo_grouped": undo_grouped,
        "op_count": op_count[0],
    }


def _cmd_undo(params):
    """Undo the most recent FL action.

    If params.count is provided (used when undo_grouped=False from a prior
    apply), undoUp is called that many times. Default 1.
    """
    import general
    count = max(1, int((params or {}).get("count", 1)))
    for _ in range(count):
        general.undoUp()
    return {"undone": True, "steps": count}


def _score(query, name):
    """Hybrid match: substring boost + difflib SequenceMatcher fallback.

    Pure SequenceMatcher.ratio is too strict for the dominant query case
    where the user types one word and expects to match a longer name
    (e.g. "kick" vs "Kick Layer Sub"). Substring matches earn a 0.7
    baseline, scaled up by query coverage of the candidate.
    """
    q = (query or "").lower()
    n = (name or "").lower()
    if not n:
        return 0.0
    if q in n:
        return round(0.7 + 0.3 * (len(q) / len(n)), 3)
    return round(difflib.SequenceMatcher(None, q, n).ratio(), 3)


def _rank_matches(query, candidates, limit, cutoff=FIND_SCORE_CUTOFF):
    """Score candidates against query, sort, return top N above cutoff."""
    scored = []
    for index, name in candidates:
        s = _score(query, name)
        if s >= cutoff:
            scored.append({"index": index, "name": name, "score": s})
    scored.sort(key=lambda m: (-m["score"], m["index"]))
    return scored[:limit]


def _cmd_find_channel_by_name(params):
    import channels
    query = str((params or {}).get("query", "")).strip()
    limit = int((params or {}).get("limit", 5))
    if not query:
        return {"matches": []}
    candidates = []
    for i in range(channels.channelCount()):
        try:
            name = channels.getChannelName(i) or ""
        except Exception:
            continue
        candidates.append((i, name))
    return {"matches": _rank_matches(query, candidates, limit)}


def _cmd_find_mixer_track_by_name(params):
    import mixer
    query = str((params or {}).get("query", "")).strip()
    limit = int((params or {}).get("limit", 5))
    if not query:
        return {"matches": []}
    candidates = []
    for i in range(mixer.trackCount()):
        try:
            name = mixer.getTrackName(i) or ""
        except Exception:
            continue
        candidates.append((i, name))
    return {"matches": _rank_matches(query, candidates, limit)}


def _cmd_find_playlist_track_by_name(params):
    import playlist
    query = str((params or {}).get("query", "")).strip()
    limit = int((params or {}).get("limit", 5))
    if not query:
        return {"matches": []}
    candidates = []
    for i in range(1, playlist.trackCount() + 1):  # 1-indexed
        try:
            name = playlist.getTrackName(i) or ""
        except Exception:
            continue
        candidates.append((i, name))
    return {"matches": _rank_matches(query, candidates, limit)}


BULK_HANDLERS = {
    "apply_organization_plan":      _cmd_apply_organization_plan,
    "undo":                         _cmd_undo,
    "find_channel_by_name":         _cmd_find_channel_by_name,
    "find_mixer_track_by_name":     _cmd_find_mixer_track_by_name,
    "find_playlist_track_by_name":  _cmd_find_playlist_track_by_name,
}
