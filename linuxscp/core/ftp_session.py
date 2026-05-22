import ftplib
import os
import posixpath
import stat
import threading
from datetime import datetime
from email.utils import parsedate_to_datetime

from linuxscp.core.base_session import BaseSession, ProgressCb
from linuxscp.core.local_fs import FileEntry

_CHUNK = 256 * 1024


class FTPSession(BaseSession):
    """
    FTP / FTPS session backed by ftplib.
    Uses MLSD for directory listing when available, falls back to LIST parsing.
    """

    def __init__(self, host: str, port: int = 21, user: str = "",
                 protocol: str = "FTP"):
        self._host     = host
        self._port     = port
        self._user     = user
        self._protocol = protocol   # "FTP" or "FTPS"
        self._ftp: ftplib.FTP | None = None
        self._home = "/"
        self._lock = threading.Lock()

    # ── Connection ────────────────────────────────────────────────────────

    def connect(self, password: str = "", timeout: float = 15.0) -> None:
        """Raises ftplib.Error on failure."""
        if self._protocol == "FTPS":
            ftp: ftplib.FTP = ftplib.FTP_TLS()
        else:
            ftp = ftplib.FTP()

        ftp.connect(self._host, self._port, timeout=timeout)
        user = self._user or "anonymous"
        ftp.login(user, password or "")

        if isinstance(ftp, ftplib.FTP_TLS):
            ftp.prot_p()

        try:
            home = ftp.pwd()
        except ftplib.Error:
            home = "/"

        with self._lock:
            if self._ftp:
                try: self._ftp.quit()
                except Exception: pass
            self._ftp = ftp
            self._home = home

    def disconnect(self):
        with self._lock:
            if self._ftp:
                try: self._ftp.quit()
                except Exception: pass
                self._ftp = None

    def is_connected(self) -> bool:
        with self._lock:
            if not self._ftp:
                return False
        try:
            self._ftp.voidcmd("NOOP")
            return True
        except Exception:
            return False

    # ── Filesystem ────────────────────────────────────────────────────────

    def list_directory(self, path: str) -> tuple[list[FileEntry], str | None]:
        with self._lock:
            if not self._ftp:
                return [], "Not connected"
            ftp = self._ftp

        entries: list[FileEntry] = []
        try:
            real = _normalize(ftp, path)
        except ftplib.Error as e:
            return [], str(e)

        if real != "/":
            entries.append(_parent_entry(posixpath.dirname(real)))

        try:
            raw = list(ftp.mlsd(real, facts=["type", "size", "modify", "perm",
                                              "unix.mode", "unix.owner", "unix.group"]))
            items = [_mlsd_to_entry(name, real, facts)
                     for name, facts in raw
                     if name not in (".", "..")]
        except ftplib.Error:
            # Server doesn't support MLSD — fall back to LIST
            try:
                raw_list: list[str] = []
                ftp.retrlines(f"LIST {real}", raw_list.append)
                items = [e for line in raw_list
                         if (e := _list_line_to_entry(line, real)) is not None]
            except ftplib.Error as e:
                return entries, str(e)

        items = [i for i in items if i is not None]
        items.sort(key=lambda e: (not e.is_dir, e.name.lower()))
        entries.extend(items)
        return entries, None

    def home_dir(self) -> str:
        return self._home

    # ── File operations ───────────────────────────────────────────────────

    def mkdir(self, path: str) -> str | None:
        with self._lock:
            if not self._ftp: return "Not connected"
            ftp = self._ftp
        try:
            ftp.mkd(path)
            return None
        except ftplib.Error as e:
            return str(e)

    def delete(self, path: str, is_dir: bool) -> str | None:
        with self._lock:
            if not self._ftp: return "Not connected"
            ftp = self._ftp
        try:
            if is_dir:
                _ftp_rmtree(ftp, path)
            else:
                ftp.delete(path)
            return None
        except ftplib.Error as e:
            return str(e)

    def rename(self, src: str, dst: str) -> str | None:
        with self._lock:
            if not self._ftp: return "Not connected"
            ftp = self._ftp
        try:
            ftp.rename(src, dst)
            return None
        except ftplib.Error as e:
            return str(e)

    # ── Transfers ─────────────────────────────────────────────────────────

    def upload(self, local_path: str, remote_path: str,
               progress: ProgressCb | None = None) -> str | None:
        with self._lock:
            if not self._ftp: return "Not connected"
            ftp = self._ftp
        try:
            size = os.path.getsize(local_path)
            sent = [0]
            def cb(chunk: bytes):
                sent[0] += len(chunk)
                if progress:
                    progress(sent[0], size)

            with open(local_path, "rb") as f:
                ftp.storbinary(f"STOR {remote_path}", f,
                               blocksize=_CHUNK, callback=cb)
            return None
        except (ftplib.Error, OSError) as e:
            return str(e)

    def download(self, remote_path: str, local_path: str,
                 progress: ProgressCb | None = None) -> str | None:
        with self._lock:
            if not self._ftp: return "Not connected"
            ftp = self._ftp
        try:
            # Get remote size for progress (best effort)
            try:
                total = int(ftp.size(remote_path) or 0)
            except Exception:
                total = 0
            recv = [0]
            with open(local_path, "wb") as f:
                def cb(chunk: bytes):
                    f.write(chunk)
                    recv[0] += len(chunk)
                    if progress:
                        progress(recv[0], total)
                ftp.retrbinary(f"RETR {remote_path}", cb, blocksize=_CHUNK)
            return None
        except (ftplib.Error, OSError) as e:
            return str(e)

    @property
    def is_remote(self) -> bool:
        return True

    @property
    def label(self) -> str:
        return f"{self._user}@{self._host}" if self._user else self._host

    @property
    def host(self) -> str:
        return self._host

    @property
    def user(self) -> str:
        return self._user


# ── Helpers ────────────────────────────────────────────────────────────────

def _normalize(ftp: ftplib.FTP, path: str) -> str:
    try:
        old = ftp.pwd()
        ftp.cwd(path)
        real = ftp.pwd()
        ftp.cwd(old)
        return real
    except ftplib.Error:
        return path


def _parent_entry(parent_path: str) -> FileEntry:
    return FileEntry(
        name="..", path=parent_path, is_dir=True, is_link=False,
        size=0, modified=datetime.fromtimestamp(0),
        permissions="", owner="", group="", extension="",
    )


def _mlsd_to_entry(name: str, parent: str, facts: dict) -> FileEntry | None:
    if not name:
        return None
    ftype   = facts.get("type", "file").lower()
    is_dir  = ftype in ("dir", "cdir", "pdir")
    is_link = ftype == "os.unix=symlink"
    size    = int(facts.get("size", 0) or 0)
    ext     = "" if is_dir else posixpath.splitext(name)[1].lstrip(".").lower()

    mtime = 0.0
    raw_modify = facts.get("modify", "")
    if raw_modify and len(raw_modify) >= 14:
        try:
            mtime = datetime.strptime(raw_modify[:14], "%Y%m%d%H%M%S").timestamp()
        except ValueError:
            pass

    mode_str = _unix_mode_str(facts.get("unix.mode", ""))

    return FileEntry(
        name=name,
        path=posixpath.join(parent, name),
        is_dir=is_dir, is_link=is_link,
        size=size,
        modified=datetime.fromtimestamp(mtime) if mtime else datetime.fromtimestamp(0),
        permissions=mode_str,
        owner=facts.get("unix.owner", ""),
        group=facts.get("unix.group", ""),
        extension=ext,
    )


def _unix_mode_str(mode_oct: str) -> str:
    if not mode_oct:
        return ""
    try:
        mode = int(mode_oct, 8)
    except ValueError:
        return mode_oct
    chars = []
    for r, w, x in (
        (0o400, 0o200, 0o100),
        (0o040, 0o020, 0o010),
        (0o004, 0o002, 0o001),
    ):
        chars += ["r" if mode & r else "-",
                  "w" if mode & w else "-",
                  "x" if mode & x else "-"]
    return "".join(chars)


# ── LIST fallback parser ───────────────────────────────────────────────────
# Handles: "drwxr-xr-x  2 user group 4096 Jan 15 10:30 dirname"

import re
_LIST_RE = re.compile(
    r"^([d\-lbcsp])([rwxXsStT\-]{9})\s+"   # permissions
    r"\d+\s+"                               # links
    r"(\S+)\s+(\S+)\s+"                    # owner group
    r"(\d+)\s+"                             # size
    r"(\w+\s+\d+\s+[\d:]+)\s+"            # date
    r"(.+)$"                               # name
)

def _list_line_to_entry(line: str, parent: str) -> FileEntry | None:
    m = _LIST_RE.match(line.strip())
    if not m:
        return None
    type_char, perms, owner, group, size_s, date_s, name = m.groups()
    name = name.split(" -> ")[0].strip()   # strip symlink target
    if name in (".", "..") or not name:
        return None

    is_dir  = type_char == "d"
    is_link = type_char == "l"
    size    = int(size_s)
    ext     = "" if is_dir else posixpath.splitext(name)[1].lstrip(".").lower()

    try:
        from dateutil import parser as dp
        mtime = dp.parse(date_s, default=datetime(datetime.now().year, 1, 1)).timestamp()
    except Exception:
        mtime = 0.0

    return FileEntry(
        name=name,
        path=posixpath.join(parent, name),
        is_dir=is_dir, is_link=is_link,
        size=size,
        modified=datetime.fromtimestamp(mtime),
        permissions=perms,
        owner=owner, group=group,
        extension=ext,
    )


def _ftp_rmtree(ftp: ftplib.FTP, path: str):
    items = list(ftp.mlsd(path, facts=["type"]))
    for name, facts in items:
        if name in (".", ".."):
            continue
        full = posixpath.join(path, name)
        if facts.get("type", "").lower() == "dir":
            _ftp_rmtree(ftp, full)
        else:
            ftp.delete(full)
    ftp.rmd(path)
