import os
import shutil
from linuxscp.core.base_session import BaseSession, ProgressCb
from linuxscp.core.local_fs import FileEntry, list_directory

_CHUNK = 256 * 1024   # 256 KB


class LocalSession(BaseSession):
    def list_directory(self, path: str) -> tuple[list[FileEntry], str | None]:
        return list_directory(path)

    def home_dir(self) -> str:
        return os.path.expanduser("~")

    def is_connected(self) -> bool:
        return True

    def disconnect(self):
        pass

    # ── File operations ───────────────────────────────────────────────────

    def mkdir(self, path: str) -> str | None:
        try:
            os.makedirs(path, exist_ok=True)
            return None
        except OSError as e:
            return str(e)

    def delete(self, path: str, is_dir: bool) -> str | None:
        try:
            if is_dir:
                shutil.rmtree(path)
            else:
                os.unlink(path)
            return None
        except OSError as e:
            return str(e)

    def rename(self, src: str, dst: str) -> str | None:
        try:
            os.rename(src, dst)
            return None
        except OSError as e:
            return str(e)

    def copy_local(self, src: str, dst: str,
                   progress: ProgressCb | None = None) -> str | None:
        try:
            if os.path.isdir(src):
                shutil.copytree(src, dst)
                if progress:
                    sz = _dir_size(src)
                    progress(sz, sz)
            else:
                sz = os.path.getsize(src)
                done = 0
                with open(src, "rb") as rf, open(dst, "wb") as wf:
                    while chunk := rf.read(_CHUNK):
                        wf.write(chunk)
                        done += len(chunk)
                        if progress:
                            progress(done, sz)
                shutil.copystat(src, dst)
            return None
        except OSError as e:
            return str(e)

    @property
    def label(self) -> str:
        return "Local"


def _dir_size(path: str) -> int:
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total
