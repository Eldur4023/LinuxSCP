import os
import posixpath
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QRadioButton, QButtonGroup, QGroupBox, QCheckBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QProgressBar,
    QSplitter, QWidget, QSizePolicy, QApplication, QComboBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont

from linuxscp.core.sync import (
    SyncDirection, SyncAction, SyncEntry, compare_directories,
)
from linuxscp.core.base_session import BaseSession
from linuxscp.core.transfer import TransferDirection, TransferJob, TransferWorker

# Column indices
COL_NAME   = 0
COL_LTIME  = 1
COL_RTIME  = 2
COL_SIZE   = 3
COL_ACTION = 4

_ACTION_COLORS = {
    SyncAction.UPLOAD:        QColor("#003399"),
    SyncAction.DOWNLOAD:      QColor("#006600"),
    SyncAction.DELETE_REMOTE: QColor("#AA0000"),
    SyncAction.DELETE_LOCAL:  QColor("#AA0000"),
    SyncAction.SKIP:          QColor("#888888"),
    SyncAction.CONFLICT:      QColor("#CC6600"),
}

_BOLD = QFont()
_BOLD.setBold(True)


class _CompareWorker(QThread):
    finished = pyqtSignal(list, str)   # entries, error

    def __init__(self, local_session, remote_session,
                 local_dir, remote_dir, direction, recursive, parent=None):
        super().__init__(parent)
        self._args = (local_session, remote_session,
                      local_dir, remote_dir, direction, recursive)

    def run(self):
        entries, err = compare_directories(*self._args)
        self.finished.emit(entries, err or "")


class SyncDialog(QDialog):
    """
    Synchronize Directories dialog — mirrors WinSCP's synchronize window.
    Phases: configure → compare → preview → execute.
    """

    def __init__(self, local_session: BaseSession, remote_session: BaseSession,
                 local_dir: str, remote_dir: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Synchronize Directories")
        self.setMinimumSize(860, 580)
        self.resize(960, 640)
        self.setModal(True)

        self._local_session  = local_session
        self._remote_session = remote_session
        self._entries: list[SyncEntry] = []
        self._worker = None
        self._transfer_worker = None

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 10, 10, 10)

        # ── Directory row ─────────────────────────────────────────────────
        dir_row = QHBoxLayout()
        dir_row.addWidget(QLabel("Local:"))
        self._local_edit = QLineEdit(local_dir)
        self._local_edit.setMinimumWidth(260)
        dir_row.addWidget(self._local_edit)

        dir_row.addWidget(QLabel("Remote:"))
        self._remote_edit = QLineEdit(remote_dir)
        self._remote_edit.setMinimumWidth(260)
        dir_row.addWidget(self._remote_edit)
        layout.addLayout(dir_row)

        # ── Options row ───────────────────────────────────────────────────
        opts_row = QHBoxLayout()

        grp_dir = QGroupBox("Direction")
        grp_dir_layout = QHBoxLayout(grp_dir)
        self._dir_group = QButtonGroup(self)
        for label, direction in (
            ("Local → Remote",  SyncDirection.LOCAL_TO_REMOTE),
            ("Remote → Local",  SyncDirection.REMOTE_TO_LOCAL),
            ("Mirror (newest)", SyncDirection.MIRROR),
        ):
            rb = QRadioButton(label)
            rb.setProperty("direction", direction)
            if direction == SyncDirection.LOCAL_TO_REMOTE:
                rb.setChecked(True)
            self._dir_group.addButton(rb)
            grp_dir_layout.addWidget(rb)
        opts_row.addWidget(grp_dir)

        grp_opts = QGroupBox("Options")
        grp_opts_layout = QHBoxLayout(grp_opts)
        self._chk_recursive = QCheckBox("Recursive")
        self._chk_recursive.setChecked(True)
        self._chk_preview = QCheckBox("Preview only (don't execute)")
        grp_opts_layout.addWidget(self._chk_recursive)
        grp_opts_layout.addWidget(self._chk_preview)
        opts_row.addWidget(grp_opts)
        layout.addLayout(opts_row)

        # ── Compare button ────────────────────────────────────────────────
        compare_row = QHBoxLayout()
        self._btn_compare = QPushButton("Compare")
        self._btn_compare.setFixedHeight(28)
        self._btn_compare.setStyleSheet("font-weight: bold;")
        self._btn_compare.clicked.connect(self._compare)
        compare_row.addWidget(self._btn_compare)
        self._progress_label = QLabel("")
        self._progress_label.setStyleSheet("color: #0000AA;")
        compare_row.addWidget(self._progress_label)
        compare_row.addStretch()
        layout.addLayout(compare_row)

        # ── Results table ─────────────────────────────────────────────────
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["Name", "Local modified", "Remote modified", "Size diff", "Action"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(COL_NAME,   QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(COL_LTIME,  QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(COL_RTIME,  QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(COL_SIZE,   QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(COL_ACTION, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self._table)

        # Summary row
        self._summary = QLabel("")
        self._summary.setStyleSheet("font-size: 8pt; color: #444;")
        layout.addWidget(self._summary)

        # Progress bar (hidden until executing)
        self._exec_progress = QProgressBar()
        self._exec_progress.setVisible(False)
        self._exec_progress.setFixedHeight(16)
        layout.addWidget(self._exec_progress)

        # ── Buttons ───────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._btn_sync = QPushButton("Synchronize")
        self._btn_sync.setFixedSize(110, 28)
        self._btn_sync.setStyleSheet("font-weight: bold; background: #0078D7; color: white;")
        self._btn_sync.setEnabled(False)
        self._btn_sync.clicked.connect(self._execute)
        self._btn_close = QPushButton("Close")
        self._btn_close.setFixedSize(90, 28)
        self._btn_close.clicked.connect(self.reject)
        btn_row.addWidget(self._btn_sync)
        btn_row.addWidget(self._btn_close)
        layout.addLayout(btn_row)

    # ── Compare phase ─────────────────────────────────────────────────────

    def _compare(self):
        self._table.setRowCount(0)
        self._btn_compare.setEnabled(False)
        self._btn_sync.setEnabled(False)
        self._progress_label.setText("Comparing…")
        QApplication.processEvents()

        direction = self._current_direction()
        worker = _CompareWorker(
            self._local_session, self._remote_session,
            self._local_edit.text().strip(),
            self._remote_edit.text().strip(),
            direction,
            self._chk_recursive.isChecked(),
            parent=self,
        )
        worker.finished.connect(self._on_compare_done)
        self._worker = worker
        worker.start()

    def _on_compare_done(self, entries: list[SyncEntry], error: str):
        self._btn_compare.setEnabled(True)
        self._progress_label.setText("")

        if error:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Compare failed", error)
            return

        self._entries = [e for e in entries if e.action != SyncAction.SKIP]
        self._populate_table()
        has_work = bool(self._entries)
        self._btn_sync.setEnabled(has_work and not self._chk_preview.isChecked())
        self._update_summary(entries)

    def _populate_table(self):
        self._table.setRowCount(0)
        for entry in self._entries:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setRowHeight(row, 20)

            color = _ACTION_COLORS.get(entry.action, QColor("#000000"))

            for col, text in (
                (COL_NAME,   ("  " * entry.rel_path.count("/")) + entry.name),
                (COL_LTIME,  entry.local_mtime_str),
                (COL_RTIME,  entry.remote_mtime_str),
                (COL_SIZE,   _size_diff(entry)),
                (COL_ACTION, entry.action_label),
            ):
                item = QTableWidgetItem(text)
                item.setForeground(color)
                if entry.is_dir:
                    item.setFont(_BOLD)
                self._table.setItem(row, col, item)

    def _update_summary(self, all_entries: list[SyncEntry]):
        counts = {}
        for e in all_entries:
            counts[e.action] = counts.get(e.action, 0) + 1
        parts = []
        for action, label in (
            (SyncAction.UPLOAD,        "to upload"),
            (SyncAction.DOWNLOAD,      "to download"),
            (SyncAction.DELETE_REMOTE, "remote deletes"),
            (SyncAction.DELETE_LOCAL,  "local deletes"),
            (SyncAction.SKIP,          "identical"),
        ):
            n = counts.get(action, 0)
            if n:
                parts.append(f"{n} {label}")
        total = len(all_entries)
        self._summary.setText(f"{total} total — " + ", ".join(parts) if parts else f"{total} files compared, all identical")

    # ── Execute phase ─────────────────────────────────────────────────────

    def _execute(self):
        if not self._entries:
            return

        self._btn_sync.setEnabled(False)
        self._btn_compare.setEnabled(False)
        self._exec_progress.setVisible(True)
        self._exec_progress.setRange(0, len(self._entries))
        self._exec_progress.setValue(0)

        jobs = self._build_jobs()
        if not jobs:
            self._exec_progress.setVisible(False)
            return

        worker = TransferWorker(jobs, parent=self)
        done_count = [0]

        def on_job_done(idx):
            done_count[0] += 1
            self._exec_progress.setValue(done_count[0])

        def on_all_done():
            self._exec_progress.setVisible(False)
            self._progress_label.setText(f"Done — {done_count[0]} operations completed.")
            self._btn_compare.setEnabled(True)

        worker.job_done.connect(on_job_done)
        worker.job_failed.connect(lambda idx, err: self._progress_label.setText(f"Error: {err}"))
        worker.all_done.connect(on_all_done)
        self._transfer_worker = worker
        worker.start()

    def _build_jobs(self) -> list[TransferJob]:
        local_dir  = self._local_edit.text().strip()
        remote_dir = self._remote_edit.text().strip()
        jobs = []

        for entry in self._entries:
            if entry.action == SyncAction.UPLOAD:
                jobs.append(TransferJob(
                    src_path    = entry.local_path,
                    dst_path    = entry.remote_path or posixpath.join(remote_dir, entry.rel_path),
                    direction   = TransferDirection.UPLOAD,
                    src_session = self._local_session,
                    dst_session = self._remote_session,
                    filename    = entry.name,
                    size        = entry.local_size,
                    is_dir      = entry.is_dir,
                ))
            elif entry.action == SyncAction.DOWNLOAD:
                jobs.append(TransferJob(
                    src_path    = entry.remote_path,
                    dst_path    = entry.local_path or os.path.join(local_dir, entry.rel_path.replace("/", os.sep)),
                    direction   = TransferDirection.DOWNLOAD,
                    src_session = self._remote_session,
                    dst_session = self._local_session,
                    filename    = entry.name,
                    size        = entry.remote_size,
                    is_dir      = entry.is_dir,
                ))
            elif entry.action == SyncAction.DELETE_REMOTE and entry.remote_path:
                err = self._remote_session.delete(entry.remote_path, entry.is_dir)
                # Deletes run immediately (not via TransferWorker)

            elif entry.action == SyncAction.DELETE_LOCAL and entry.local_path:
                err = self._local_session.delete(entry.local_path, entry.is_dir)

        return jobs

    # ── Helpers ───────────────────────────────────────────────────────────

    def _current_direction(self) -> SyncDirection:
        for btn in self._dir_group.buttons():
            if btn.isChecked():
                return btn.property("direction")
        return SyncDirection.LOCAL_TO_REMOTE


def _size_diff(e: SyncEntry) -> str:
    if e.local_path and e.remote_path:
        diff = e.local_size - e.remote_size
        sign = "+" if diff >= 0 else ""
        return f"{sign}{diff:,} B"
    if e.local_path:
        return f"+{e.local_size:,} B"
    if e.remote_path:
        return f"-{e.remote_size:,} B"
    return ""
