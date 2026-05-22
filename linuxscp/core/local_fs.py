import os
import stat
import pwd
import grp
from datetime import datetime
from dataclasses import dataclass
from typing import Optional


@dataclass
class FileEntry:
    name: str
    path: str
    is_dir: bool
    is_link: bool
    size: int
    modified: datetime
    permissions: str
    owner: str
    group: str
    extension: str

    @property
    def size_str(self) -> str:
        if self.is_dir:
            return ""
        for unit, threshold in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
            if self.size >= threshold:
                return f"{self.size / threshold:.1f} {unit}"
        return f"{self.size} B"

    @property
    def modified_str(self) -> str:
        return self.modified.strftime("%d/%m/%Y %H:%M")

    @property
    def type_str(self) -> str:
        if self.is_link:
            return "Link"
        if self.is_dir:
            return "Directory"
        if self.extension:
            return f"{self.extension.upper()} File"
        return "File"


def list_directory(path: str) -> tuple[list[FileEntry], Optional[str]]:
    """Returns (entries, error_message). entries[0] is '..' if not root."""
    entries: list[FileEntry] = []

    try:
        real_path = os.path.realpath(path)
    except OSError as e:
        return [], str(e)

    if real_path != "/":
        parent = os.path.dirname(real_path)
        entries.append(_make_parent_entry(parent))

    try:
        names = sorted(os.listdir(real_path), key=lambda n: (not os.path.isdir(os.path.join(real_path, n)), n.lower()))
    except PermissionError as e:
        return entries, str(e)

    for name in names:
        full = os.path.join(real_path, name)
        entry = _stat_entry(name, full)
        if entry:
            entries.append(entry)

    return entries, None


def _make_parent_entry(parent_path: str) -> FileEntry:
    return FileEntry(
        name="..",
        path=parent_path,
        is_dir=True,
        is_link=False,
        size=0,
        modified=datetime.fromtimestamp(0),
        permissions="",
        owner="",
        group="",
        extension="",
    )


def _stat_entry(name: str, full_path: str) -> Optional[FileEntry]:
    try:
        st = os.lstat(full_path)
    except OSError:
        return None

    is_link = stat.S_ISLNK(st.st_mode)
    is_dir = os.path.isdir(full_path)
    ext = "" if is_dir else os.path.splitext(name)[1].lstrip(".").lower()

    try:
        owner = pwd.getpwuid(st.st_uid).pw_name
    except KeyError:
        owner = str(st.st_uid)

    try:
        group = grp.getgrgid(st.st_gid).gr_name
    except KeyError:
        group = str(st.st_gid)

    return FileEntry(
        name=name,
        path=full_path,
        is_dir=is_dir,
        is_link=is_link,
        size=st.st_size,
        modified=datetime.fromtimestamp(st.st_mtime),
        permissions=_mode_str(st.st_mode),
        owner=owner,
        group=group,
        extension=ext,
    )


def _mode_str(mode: int) -> str:
    chars = []
    for who in ((stat.S_IRUSR, stat.S_IWUSR, stat.S_IXUSR),
                (stat.S_IRGRP, stat.S_IWGRP, stat.S_IXGRP),
                (stat.S_IROTH, stat.S_IWOTH, stat.S_IXOTH)):
        chars.append("r" if mode & who[0] else "-")
        chars.append("w" if mode & who[1] else "-")
        chars.append("x" if mode & who[2] else "-")
    return "".join(chars)
