import os
import posixpath
import stat
import threading
from datetime import datetime
from typing import Callable

import paramiko

from linuxscp.core.base_session import BaseSession, ProgressCb
from linuxscp.core.local_fs import FileEntry


class HostKeyPolicy(paramiko.MissingHostKeyPolicy):
    """Accept all host keys but store them for display (like WinSCP's first-connect prompt)."""
    def __init__(self, callback: Callable[[str, str, str], bool] | None = None):
        self._cb = callback  # cb(hostname, key_type, fingerprint) -> bool (True=accept)

    def missing_host_key(self, client, hostname, key):
        fp = key.get_fingerprint().hex(":")
        if self._cb:
            if not self._cb(hostname, key.get_name(), fp):
                raise paramiko.SSHException(f"Host key rejected for {hostname}")
        # accept silently if no callback


class SFTPSession(BaseSession):
    """
    SFTP/SCP session backed by paramiko.

    Usage:
        session = SFTPSession(host, port, user)
        session.connect(password="…")          # or key_filename="…"
        entries, err = session.list_directory("/home/user")
        session.disconnect()
    """

    def __init__(
        self,
        host: str,
        port: int = 22,
        user: str = "",
        host_key_callback: Callable | None = None,
    ):
        self._host = host
        self._port = port
        self._user = user
        self._host_key_cb = host_key_callback
        self._client: paramiko.SSHClient | None = None
        self._sftp: paramiko.SFTPClient | None = None
        self._home: str = "/"
        self._lock = threading.Lock()

    # ── Connection ────────────────────────────────────────────────────────

    def connect(
        self,
        password: str = "",
        key_filename: str = "",
        timeout: float = 15.0,
    ) -> None:
        """Raises paramiko.AuthenticationException / SSHException on failure."""
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(HostKeyPolicy(self._host_key_cb))

        kwargs: dict = {
            "hostname":  self._host,
            "port":      self._port,
            "username":  self._user,
            "timeout":   timeout,
            "allow_agent": True,
            "look_for_keys": True,
        }
        if password:
            kwargs["password"] = password
        if key_filename:
            kwargs["key_filename"] = key_filename

        client.connect(**kwargs)
        sftp = client.open_sftp()

        try:
            home = sftp.normalize(".")
        except Exception:
            home = "/"

        with self._lock:
            if self._sftp:
                self._sftp.close()
            if self._client:
                self._client.close()
            self._client = client
            self._sftp   = sftp
            self._home   = home

    def disconnect(self):
        with self._lock:
            if self._sftp:
                try: self._sftp.close()
                except Exception: pass
                self._sftp = None
            if self._client:
                try: self._client.close()
                except Exception: pass
                self._client = None

    def is_connected(self) -> bool:
        with self._lock:
            return (
                self._sftp is not None
                and self._client is not None
                and self._client.get_transport() is not None
                and self._client.get_transport().is_active()
            )

    # ── Filesystem ────────────────────────────────────────────────────────

    def list_directory(self, path: str) -> tuple[list[FileEntry], str | None]:
        with self._lock:
            if not self._sftp:
                return [], "Not connected"
            sftp = self._sftp

        entries: list[FileEntry] = []

        try:
            real = sftp.normalize(path)
        except IOError as e:
            return [], str(e)

        if real != "/":
            entries.append(_parent_entry(posixpath.dirname(real)))

        try:
            attrs = sftp.listdir_attr(real)
        except PermissionError as e:
            return entries, str(e)
        except IOError as e:
            return entries, str(e)

        # Directories first, then files — both sorted case-insensitively
        attrs.sort(key=lambda a: (
            not stat.S_ISDIR(a.st_mode or 0),
            (a.filename or "").lower(),
        ))

        for attr in attrs:
            name = attr.filename or ""
            full = posixpath.join(real, name)
            entry = _attr_to_entry(name, full, attr)
            if entry:
                entries.append(entry)

        return entries, None

    def home_dir(self) -> str:
        return self._home

    # ── File operations ───────────────────────────────────────────────────

    def mkdir(self, path: str) -> str | None:
        with self._lock:
            if not self._sftp:
                return "Not connected"
            sftp = self._sftp
        try:
            sftp.mkdir(path)
            return None
        except IOError as e:
            return str(e)

    def delete(self, path: str, is_dir: bool) -> str | None:
        with self._lock:
            if not self._sftp:
                return "Not connected"
            sftp = self._sftp
        try:
            if is_dir:
                _sftp_rmtree(sftp, path)
            else:
                sftp.remove(path)
            return None
        except IOError as e:
            return str(e)

    def rename(self, src: str, dst: str) -> str | None:
        with self._lock:
            if not self._sftp:
                return "Not connected"
            sftp = self._sftp
        try:
            sftp.rename(src, dst)
            return None
        except IOError as e:
            return str(e)

    # ── Transfer primitives ───────────────────────────────────────────────

    def upload(self, local_path: str, remote_path: str,
               progress: ProgressCb | None = None) -> str | None:
        with self._lock:
            if not self._sftp:
                return "Not connected"
            sftp = self._sftp
        try:
            if os.path.isdir(local_path):
                return _sftp_put_dir(sftp, local_path, remote_path, progress)
            else:
                sftp.put(local_path, remote_path,
                         callback=progress, confirm=True)
            return None
        except IOError as e:
            return str(e)

    def download(self, remote_path: str, local_path: str,
                 progress: ProgressCb | None = None) -> str | None:
        with self._lock:
            if not self._sftp:
                return "Not connected"
            sftp = self._sftp
        try:
            attr = sftp.stat(remote_path)
            if stat.S_ISDIR(attr.st_mode or 0):
                return _sftp_get_dir(sftp, remote_path, local_path, progress)
            else:
                sftp.get(remote_path, local_path, callback=progress)
            return None
        except IOError as e:
            return str(e)

    def execute(self, command: str) -> tuple[str, str, int]:
        """Run a command, return (stdout, stderr, exit_code)."""
        with self._lock:
            if not self._client:
                return "", "Not connected", -1
            client = self._client
        _, stdout, stderr = client.exec_command(command)
        exit_code = stdout.channel.recv_exit_status()
        return stdout.read().decode(errors="replace"), stderr.read().decode(errors="replace"), exit_code

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

def _parent_entry(parent_path: str) -> FileEntry:
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


def _attr_to_entry(name: str, full_path: str, attr: paramiko.SFTPAttributes) -> FileEntry | None:
    if not name:
        return None

    mode     = attr.st_mode or 0
    is_dir   = stat.S_ISDIR(mode)
    is_link  = stat.S_ISLNK(mode)
    size     = attr.st_size or 0
    mtime    = attr.st_mtime or 0
    ext      = "" if is_dir else posixpath.splitext(name)[1].lstrip(".").lower()
    uid      = str(attr.st_uid) if attr.st_uid is not None else ""
    gid      = str(attr.st_gid) if attr.st_gid is not None else ""

    return FileEntry(
        name=name,
        path=full_path,
        is_dir=is_dir,
        is_link=is_link,
        size=size,
        modified=datetime.fromtimestamp(mtime) if mtime else datetime.fromtimestamp(0),
        permissions=_mode_str(mode),
        owner=uid,
        group=gid,
        extension=ext,
    )


def _mode_str(mode: int) -> str:
    chars = []
    for r, w, x in (
        (stat.S_IRUSR, stat.S_IWUSR, stat.S_IXUSR),
        (stat.S_IRGRP, stat.S_IWGRP, stat.S_IXGRP),
        (stat.S_IROTH, stat.S_IWOTH, stat.S_IXOTH),
    ):
        chars += ["r" if mode & r else "-", "w" if mode & w else "-", "x" if mode & x else "-"]
    return "".join(chars)


def _sftp_rmtree(sftp: paramiko.SFTPClient, path: str):
    for attr in sftp.listdir_attr(path):
        full = posixpath.join(path, attr.filename)
        if stat.S_ISDIR(attr.st_mode or 0):
            _sftp_rmtree(sftp, full)
        else:
            sftp.remove(full)
    sftp.rmdir(path)


def _sftp_put_dir(sftp: paramiko.SFTPClient, local_dir: str, remote_dir: str,
                  progress: ProgressCb | None) -> str | None:
    try:
        sftp.mkdir(remote_dir)
    except IOError:
        pass  # already exists
    for name in os.listdir(local_dir):
        local_path  = os.path.join(local_dir, name)
        remote_path = posixpath.join(remote_dir, name)
        if os.path.isdir(local_path):
            err = _sftp_put_dir(sftp, local_path, remote_path, progress)
            if err:
                return err
        else:
            sftp.put(local_path, remote_path, callback=progress, confirm=True)
    return None


def _sftp_get_dir(sftp: paramiko.SFTPClient, remote_dir: str, local_dir: str,
                  progress: ProgressCb | None) -> str | None:
    os.makedirs(local_dir, exist_ok=True)
    for attr in sftp.listdir_attr(remote_dir):
        remote_path = posixpath.join(remote_dir, attr.filename)
        local_path  = os.path.join(local_dir, attr.filename)
        if stat.S_ISDIR(attr.st_mode or 0):
            err = _sftp_get_dir(sftp, remote_path, local_path, progress)
            if err:
                return err
        else:
            sftp.get(remote_path, local_path, callback=progress)
    return None
