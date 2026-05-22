"""
Application preferences — single source of truth for all user settings.
Loaded once at startup, saved on change, accessed via get_prefs().
"""
import json
import os
from dataclasses import dataclass, asdict, field

_PREFS_FILE = os.path.join(os.path.expanduser("~"), ".config", "linuxscp", "preferences.json")
_instance = None


@dataclass
class Preferences:
    # ── General ───────────────────────────────────────────────────────────
    confirm_delete:          bool = True
    confirm_overwrite:       bool = True
    show_hidden_files:       bool = True
    resume_on_error:         bool = False
    remember_last_dir:       bool = True
    last_local_dir:          str  = ""
    last_remote_dir:         str  = ""

    # ── Transfers ─────────────────────────────────────────────────────────
    preserve_timestamps:     bool = True
    preserve_permissions:    bool = True
    transfer_mode:           str  = "auto"    # "binary" | "text" | "auto"
    max_concurrent:          int  = 2
    retry_count:             int  = 3

    # ── Editor ────────────────────────────────────────────────────────────
    use_external_editor:     bool = False
    external_editor_cmd:     str  = ""        # e.g. "gedit %f" or "code %f"
    editor_font_family:      str  = "Courier New"
    editor_font_size:        int  = 10

    # ── Interface ────────────────────────────────────────────────────────
    panel_font_family:       str  = ""        # empty = system default
    panel_font_size:         int  = 9
    show_queue_panel:        bool = True
    theme:                   str  = "system"  # "system" | "light" | "dark"
    double_click_action:     str  = "open"    # "open" | "select"

    def save(self):
        os.makedirs(os.path.dirname(_PREFS_FILE), exist_ok=True)
        with open(_PREFS_FILE, "w") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls) -> "Preferences":
        try:
            with open(_PREFS_FILE, "r") as f:
                data = json.load(f)
            p = cls()
            for k, v in data.items():
                if hasattr(p, k):
                    setattr(p, k, v)
            return p
        except (FileNotFoundError, json.JSONDecodeError):
            return cls()


def get_prefs() -> Preferences:
    global _instance
    if _instance is None:
        _instance = Preferences.load()
    return _instance


def reload_prefs() -> Preferences:
    global _instance
    _instance = Preferences.load()
    return _instance
