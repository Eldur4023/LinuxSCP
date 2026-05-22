import os
import posixpath
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

from PyQt6.QtCore import QThread, pyqtSignal

if TYPE_CHECKING:
    from linuxscp.core.base_session import BaseSession


class TransferDirection(Enum):
    UPLOAD      = auto()   # local → remote
    DOWNLOAD    = auto()   # remote → local
    LOCAL_COPY  = auto()   # local → local


class TransferStatus(Enum):
    QUEUED     = auto()
    RUNNING    = auto()
    DONE       = auto()
    FAILED     = auto()
    SKIPPED    = auto()
    CANCELLED  = auto()


@dataclass
class TransferJob:
    src_path:   str
    dst_path:   str
    direction:  TransferDirection
    src_session: "BaseSession"
    dst_session: "BaseSession"
    filename:   str = ""
    size:       int = 0
    is_dir:     bool = False
    status:     TransferStatus = TransferStatus.QUEUED
    bytes_done: int = 0
    error:      str = ""

    def __post_init__(self):
        if not self.filename:
            self.filename = os.path.basename(self.src_path) or posixpath.basename(self.src_path)


class OverwriteMode(Enum):
    OVERWRITE = auto()
    SKIP      = auto()
    RENAME    = auto()   # append "(1)", "(2)", … to dst


class TransferWorker(QThread):
    """
    Executes a queue of TransferJobs off the GUI thread.

    Signals:
        job_started(int)                    — job index
        job_progress(int, int, int, float)  — index, bytes_done, bytes_total, speed_bps
        job_done(int)                       — index
        job_failed(int, str)                — index, error
        all_done()
    """

    job_started  = pyqtSignal(int)
    job_progress = pyqtSignal(int, int, int, float)   # idx, done, total, speed
    job_done     = pyqtSignal(int)
    job_failed   = pyqtSignal(int, str)
    all_done     = pyqtSignal()

    def __init__(self, jobs: list[TransferJob],
                 overwrite: OverwriteMode = OverwriteMode.OVERWRITE,
                 parent=None):
        super().__init__(parent)
        self._jobs     = jobs
        self._overwrite = overwrite
        self._cancel   = False

    def cancel(self):
        self._cancel = True

    def run(self):
        for idx, job in enumerate(self._jobs):
            if self._cancel:
                job.status = TransferStatus.CANCELLED
                break

            job.status = TransferStatus.RUNNING
            self.job_started.emit(idx)

            err = self._execute(idx, job)
            if err:
                job.status = TransferStatus.FAILED
                job.error  = err
                self.job_failed.emit(idx, err)
            else:
                job.status = TransferStatus.DONE
                self.job_done.emit(idx)

        self.all_done.emit()

    def _execute(self, idx: int, job: TransferJob) -> str | None:
        t0    = time.monotonic()
        last  = [0, t0]   # [last_bytes, last_time]

        def progress(done: int, total: int):
            job.bytes_done = done
            now   = time.monotonic()
            dt    = now - last[1]
            if dt >= 0.25:
                speed = (done - last[0]) / dt if dt > 0 else 0.0
                self.job_progress.emit(idx, done, total, speed)
                last[0] = done
                last[1] = now

        match job.direction:
            case TransferDirection.UPLOAD:
                return job.src_session.upload(job.src_path, job.dst_path, progress)
            case TransferDirection.DOWNLOAD:
                return job.src_session.download(job.src_path, job.dst_path, progress)
            case TransferDirection.LOCAL_COPY:
                return job.src_session.copy_local(job.src_path, job.dst_path, progress)

        return "Unknown transfer direction"


def build_transfer_jobs(
    entries: list,                # list[FileEntry]
    src_session: "BaseSession",
    dst_session: "BaseSession",
    dst_dir: str,
) -> list[TransferJob]:
    """Build a list of TransferJobs from selected entries."""
    jobs: list[TransferJob] = []

    if src_session.is_remote and not dst_session.is_remote:
        direction = TransferDirection.DOWNLOAD
    elif not src_session.is_remote and dst_session.is_remote:
        direction = TransferDirection.UPLOAD
    else:
        direction = TransferDirection.LOCAL_COPY

    for entry in entries:
        if entry.name == "..":
            continue
        if dst_session.is_remote:
            dst_path = posixpath.join(dst_dir, entry.name)
        else:
            dst_path = os.path.join(dst_dir, entry.name)

        jobs.append(TransferJob(
            src_path   = entry.path,
            dst_path   = dst_path,
            direction  = direction,
            src_session = src_session,
            dst_session = dst_session,
            filename   = entry.name,
            size       = entry.size,
            is_dir     = entry.is_dir,
        ))

    return jobs
