"""Bridge authentication — local token generation and validation."""

import os
import secrets
import sys
from pathlib import Path


def get_token_path() -> Path:
    if sys.platform == "darwin":
        base = Path.home() / ".config" / "studio-ai"
    elif sys.platform == "win32":
        appdata = os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")
        base = Path(appdata) / "studio-ai"
    else:
        base = Path.home() / ".config" / "studio-ai"
    return base / "bridge.token"


def generate_token() -> str:
    return secrets.token_hex(32)


def ensure_token() -> str:
    path = get_token_path()
    if path.exists():
        token = path.read_text().strip()
        if token:
            return token
    path.parent.mkdir(parents=True, exist_ok=True)
    token = generate_token()
    path.write_text(token)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return token


def validate_token(provided: str, expected: str) -> bool:
    return secrets.compare_digest(provided, expected)
