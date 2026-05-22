from abc import ABC, abstractmethod
from typing import Callable
from linuxscp.core.local_fs import FileEntry

ProgressCb = Callable[[int, int], None]   # (bytes_done, bytes_total)


class BaseSession(ABC):
    """Protocol-agnostic interface for both local and remote filesystems."""

    @abstractmethod
    def list_directory(self, path: str) -> tuple[list[FileEntry], str | None]:
        """Returns (entries, error). entries[0] is '..' when not at root."""

    @abstractmethod
    def home_dir(self) -> str:
        """Return the home/default directory for this session."""

    @abstractmethod
    def is_connected(self) -> bool: ...

    @abstractmethod
    def disconnect(self): ...

    # ── File operations ───────────────────────────────────────────────────

    @abstractmethod
    def mkdir(self, path: str) -> str | None:
        """Create directory. Returns error string or None."""

    @abstractmethod
    def delete(self, path: str, is_dir: bool) -> str | None:
        """Delete file or directory (recursive for dirs). Returns error or None."""

    @abstractmethod
    def rename(self, src: str, dst: str) -> str | None:
        """Rename/move within the same session. Returns error or None."""

    # ── Transfer primitives ───────────────────────────────────────────────

    def upload(self, local_path: str, remote_path: str,
               progress: ProgressCb | None = None) -> str | None:
        """Upload local_path → remote_path. Override in remote sessions."""
        return "Upload not supported by this session type"

    def download(self, remote_path: str, local_path: str,
                 progress: ProgressCb | None = None) -> str | None:
        """Download remote_path → local_path. Override in remote sessions."""
        return "Download not supported by this session type"

    def copy_local(self, src: str, dst: str,
                   progress: ProgressCb | None = None) -> str | None:
        """Local-to-local copy. Override in local sessions."""
        return "Local copy not supported by this session type"

    @property
    def is_remote(self) -> bool:
        return False

    @property
    def label(self) -> str:
        return "Local"
