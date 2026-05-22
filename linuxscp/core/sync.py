import os
import posixpath
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from linuxscp.core.base_session import BaseSession
    from linuxscp.core.local_fs import FileEntry


class SyncDirection(Enum):
    LOCAL_TO_REMOTE = auto()   # upload newer/missing
    REMOTE_TO_LOCAL = auto()   # download newer/missing
    MIRROR          = auto()   # bidirectional: newest wins


class SyncAction(Enum):
    UPLOAD         = auto()   # copy local → remote
    DOWNLOAD       = auto()   # copy remote → local
    DELETE_REMOTE  = auto()   # exists only on local (mirror delete)
    DELETE_LOCAL   = auto()   # exists only on remote (mirror delete)
    SKIP           = auto()   # identical or excluded
    CONFLICT       = auto()   # both modified (mirror only)


@dataclass
class SyncEntry:
    name:          str
    rel_path:      str          # path relative to sync root
    local_path:    str | None
    remote_path:   str | None
    local_mtime:   float = 0.0
    remote_mtime:  float = 0.0
    local_size:    int   = 0
    remote_size:   int   = 0
    is_dir:        bool  = False
    action:        SyncAction = SyncAction.SKIP

    @property
    def local_mtime_str(self) -> str:
        if not self.local_path:
            return "—"
        from datetime import datetime
        return datetime.fromtimestamp(self.local_mtime).strftime("%d/%m/%Y %H:%M")

    @property
    def remote_mtime_str(self) -> str:
        if not self.remote_path:
            return "—"
        from datetime import datetime
        return datetime.fromtimestamp(self.remote_mtime).strftime("%d/%m/%Y %H:%M")

    @property
    def action_label(self) -> str:
        return {
            SyncAction.UPLOAD:        "↑ Upload",
            SyncAction.DOWNLOAD:      "↓ Download",
            SyncAction.DELETE_REMOTE: "✗ Del remote",
            SyncAction.DELETE_LOCAL:  "✗ Del local",
            SyncAction.SKIP:          "= Skip",
            SyncAction.CONFLICT:      "⚠ Conflict",
        }.get(self.action, "?")


def compare_directories(
    local_session: "BaseSession",
    remote_session: "BaseSession",
    local_dir: str,
    remote_dir: str,
    direction: SyncDirection,
    recursive: bool = True,
) -> tuple[list[SyncEntry], str | None]:
    """
    Returns (entries, error).
    Entries describe the diff between local_dir and remote_dir.
    """
    local_map:  dict[str, "FileEntry"] = {}
    remote_map: dict[str, "FileEntry"] = {}

    err = _build_map(local_session,  local_dir,  "",  local_map,  recursive, is_remote=False)
    if err:
        return [], f"Local listing failed: {err}"

    err = _build_map(remote_session, remote_dir, "", remote_map, recursive, is_remote=True)
    if err:
        return [], f"Remote listing failed: {err}"

    all_keys = sorted(set(local_map) | set(remote_map))
    entries: list[SyncEntry] = []

    for key in all_keys:
        local_e  = local_map.get(key)
        remote_e = remote_map.get(key)

        lpath = os.path.join(local_dir, key.replace("/", os.sep)) if local_e else None
        rpath = posixpath.join(remote_dir, key) if remote_e else None

        entry = SyncEntry(
            name        = key.split("/")[-1],
            rel_path    = key,
            local_path  = lpath,
            remote_path = rpath,
            local_mtime = local_e.modified.timestamp() if local_e else 0,
            remote_mtime= remote_e.modified.timestamp() if remote_e else 0,
            local_size  = local_e.size if local_e else 0,
            remote_size = remote_e.size if remote_e else 0,
            is_dir      = (local_e.is_dir if local_e else False) or
                          (remote_e.is_dir if remote_e else False),
        )
        entry.action = _decide_action(entry, direction)
        entries.append(entry)

    return entries, None


def _decide_action(e: SyncEntry, direction: SyncDirection) -> SyncAction:
    only_local  = e.local_path  is not None and e.remote_path is None
    only_remote = e.remote_path is not None and e.local_path  is None
    both        = e.local_path  is not None and e.remote_path is not None

    match direction:
        case SyncDirection.LOCAL_TO_REMOTE:
            if only_local:
                return SyncAction.UPLOAD
            if only_remote:
                return SyncAction.SKIP
            if both and e.local_mtime > e.remote_mtime + 1:
                return SyncAction.UPLOAD
            return SyncAction.SKIP

        case SyncDirection.REMOTE_TO_LOCAL:
            if only_remote:
                return SyncAction.DOWNLOAD
            if only_local:
                return SyncAction.SKIP
            if both and e.remote_mtime > e.local_mtime + 1:
                return SyncAction.DOWNLOAD
            return SyncAction.SKIP

        case SyncDirection.MIRROR:
            if only_local:
                return SyncAction.UPLOAD
            if only_remote:
                return SyncAction.DOWNLOAD
            if both:
                diff = abs(e.local_mtime - e.remote_mtime)
                if diff <= 1:
                    return SyncAction.SKIP
                if e.local_mtime > e.remote_mtime:
                    return SyncAction.UPLOAD
                return SyncAction.DOWNLOAD

    return SyncAction.SKIP


def _build_map(
    session: "BaseSession",
    base_dir: str,
    prefix: str,
    result: dict,
    recursive: bool,
    is_remote: bool,
) -> str | None:
    entries, err = session.list_directory(base_dir)
    if err:
        return err

    for e in entries:
        if e.name == "..":
            continue
        key = f"{prefix}{e.name}" if not prefix else f"{prefix}/{e.name}"
        result[key] = e
        if recursive and e.is_dir:
            sub_dir = (posixpath.join(base_dir, e.name) if is_remote
                       else os.path.join(base_dir, e.name))
            sub_err = _build_map(session, sub_dir, key, result, recursive, is_remote)
            if sub_err:
                return sub_err
    return None
