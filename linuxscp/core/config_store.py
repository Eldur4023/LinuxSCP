"""
Persistent config for LinuxSCP: sessions + bookmarks.
Stored as JSON under ~/.config/linuxscp/.
"""
import json
import os
from dataclasses import dataclass, asdict, field
from typing import Any

_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "linuxscp")
_SESSIONS_FILE  = os.path.join(_CONFIG_DIR, "sessions.json")
_BOOKMARKS_FILE = os.path.join(_CONFIG_DIR, "bookmarks.json")


# ── Sessions ──────────────────────────────────────────────────────────────

@dataclass
class StoredSession:
    name:       str = "New Session"
    protocol:   str = "SFTP"
    host:       str = ""
    port:       int = 22
    user:       str = ""
    password:   str = ""   # stored in plaintext — phase 6 will add keyring
    key_file:   str = ""
    remote_dir: str = ""
    local_dir:  str = ""
    group:      str = "My Sites"


def load_sessions() -> list[StoredSession]:
    try:
        with open(_SESSIONS_FILE, "r") as f:
            data = json.load(f)
        return [StoredSession(**s) for s in data]
    except (FileNotFoundError, json.JSONDecodeError, TypeError):
        return []


def save_sessions(sessions: list[StoredSession]):
    _ensure_dir()
    with open(_SESSIONS_FILE, "w") as f:
        json.dump([asdict(s) for s in sessions], f, indent=2)


# ── Bookmarks ─────────────────────────────────────────────────────────────

@dataclass
class Bookmark:
    name:  str = ""
    path:  str = ""
    label: str = "Local"   # session label: "Local" or "user@host"


def load_bookmarks() -> list[Bookmark]:
    try:
        with open(_BOOKMARKS_FILE, "r") as f:
            data = json.load(f)
        return [Bookmark(**b) for b in data]
    except (FileNotFoundError, json.JSONDecodeError, TypeError):
        return []


def save_bookmarks(bookmarks: list[Bookmark]):
    _ensure_dir()
    with open(_BOOKMARKS_FILE, "w") as f:
        json.dump([asdict(b) for b in bookmarks], f, indent=2)


def add_bookmark(path: str, label: str, name: str = "") -> list[Bookmark]:
    bookmarks = load_bookmarks()
    # Avoid exact duplicates
    for b in bookmarks:
        if b.path == path and b.label == label:
            return bookmarks
    bm = Bookmark(
        name  = name or path.split("/")[-1] or path.split(os.sep)[-1] or path,
        path  = path,
        label = label,
    )
    bookmarks.append(bm)
    save_bookmarks(bookmarks)
    return bookmarks


def remove_bookmark(path: str, label: str) -> list[Bookmark]:
    bookmarks = [b for b in load_bookmarks()
                 if not (b.path == path and b.label == label)]
    save_bookmarks(bookmarks)
    return bookmarks


def _ensure_dir():
    os.makedirs(_CONFIG_DIR, exist_ok=True)
