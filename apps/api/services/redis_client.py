"""Redis key helpers for connection registry."""

ONLINE_KEY_PREFIX = "plugin:online:"
ONLINE_TTL_SECONDS = 90


def online_key(user_id: str) -> str:
    """Redis key for user's online status."""
    return f"{ONLINE_KEY_PREFIX}{user_id}"


def relay_channel(user_id: str) -> str:
    """Redis pub/sub channel for cross-instance relay."""
    return f"relay:{user_id}"
