from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QPushButton, QProgressBar,
    QSizePolicy, QAbstractItemView,
)
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QColor

from linuxscp.core.transfer import TransferJob, TransferStatus, TransferDirection
from linuxscp.ui.styles import QUEUE_STYLE

# Column indices
COL_FILE  = 0
COL_DIR   = 1
COL_SIZE  = 2
COL_PROG  = 3
COL_SPEED = 4
COL_STAT  = 5

_DIR_LABELS = {
    TransferDirection.UPLOAD:     "↑ Upload",
    TransferDirection.DOWNLOAD:   "↓ Download",
    TransferDirection.LOCAL_COPY: "→ Copy",
}
_STATUS_COLORS = {
    TransferStatus.DONE:      "#006600",
    TransferStatus.FAILED:    "#AA0000",
    TransferStatus.CANCELLED: "#808080",
    TransferStatus.RUNNING:   "#0000AA",
    TransferStatus.QUEUED:    "#444444",
}


class TransferQueuePanel(QWidget):
    """
    Collapsible bottom panel showing active and completed transfers.
    Mirrors WinSCP's transfer queue.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("QueuePanel")
        self.setStyleSheet(QUEUE_STYLE)
        self._jobs: list[TransferJob] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header row ────────────────────────────────────────────────────
        header_row = QWidget()
        header_row.setObjectName("QueueTitle")
        hrl = QHBoxLayout(header_row)
        hrl.setContentsMargins(6, 2, 6, 2)

        self._title = QLabel("Transfer Queue")
        self._title.setStyleSheet("font-weight: bold; font-size: 8pt;")
        hrl.addWidget(self._title)
        hrl.addStretch()

        self._btn_toggle = QPushButton("▼")
        self._btn_toggle.setFixedSize(20, 18)
        self._btn_toggle.setFlat(True)
        self._btn_toggle.setToolTip("Collapse/Expand queue")
        self._btn_toggle.clicked.connect(self._toggle)
        hrl.addWidget(self._btn_toggle)

        self._btn_clear = QPushButton("Clear done")
        self._btn_clear.setFixedHeight(18)
        self._btn_clear.setStyleSheet("font-size: 7pt; padding: 0 6px;")
        self._btn_clear.clicked.connect(self._clear_done)
        hrl.addWidget(self._btn_clear)

        layout.addWidget(header_row)

        # ── Table ─────────────────────────────────────────────────────────
        self._table = QTableWidget(0, 6)
        self._table.setObjectName("QueueList")
        self._table.setHorizontalHeaderLabels(["File", "Dir", "Size", "Progress", "Speed", "Status"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(COL_FILE,  QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(COL_DIR,   QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(COL_SIZE,  QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(COL_PROG,  QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(COL_SPEED, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(COL_STAT,  QHeaderView.ResizeMode.ResizeToContents)
        self._table.setColumnWidth(COL_PROG, 120)

        self._table.setFixedHeight(110)
        layout.addWidget(self._table)

        self._expanded = True
        self.setMaximumHeight(140)

    # ── Public API ────────────────────────────────────────────────────────

    def add_jobs(self, jobs: list[TransferJob]):
        for job in jobs:
            self._jobs.append(job)
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setRowHeight(row, 20)

            self._table.setItem(row, COL_FILE,  _item(job.filename))
            self._table.setItem(row, COL_DIR,   _item(_DIR_LABELS.get(job.direction, "?")))
            self._table.setItem(row, COL_SIZE,  _item(_fmt(job.size)))
            self._table.setItem(row, COL_SPEED, _item(""))
            self._table.setItem(row, COL_STAT,  _item("Queued"))

            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setTextVisible(True)
            bar.setFixedHeight(16)
            self._table.setCellWidget(row, COL_PROG, bar)

        self._refresh_title()

    @pyqtSlot(int)
    def on_job_started(self, idx: int):
        self._set_status(idx, "Running", "#0000AA")

    @pyqtSlot(int, int, int, float)
    def on_job_progress(self, idx: int, done: int, total: int, speed: float):
        if idx >= self._table.rowCount():
            return
        pct = int(done * 100 / total) if total > 0 else 0
        bar = self._table.cellWidget(idx, COL_PROG)
        if bar:
            bar.setValue(pct)
        speed_str = _fmt(int(speed)) + "/s" if speed > 0 else ""
        self._table.setItem(idx, COL_SPEED, _item(speed_str))

    @pyqtSlot(int)
    def on_job_done(self, idx: int):
        bar = self._table.cellWidget(idx, COL_PROG)
        if bar:
            bar.setValue(100)
        self._set_status(idx, "Done", "#006600")
        self._refresh_title()

    @pyqtSlot(int, str)
    def on_job_failed(self, idx: int, error: str):
        self._set_status(idx, f"Failed: {error}", "#AA0000")
        self._refresh_title()

    @pyqtSlot()
    def on_all_done(self):
        self._refresh_title()

    # ── Internals ─────────────────────────────────────────────────────────

    def _set_status(self, idx: int, text: str, color: str):
        if idx >= self._table.rowCount():
            return
        item = _item(text)
        item.setForeground(QColor(color))
        self._table.setItem(idx, COL_STAT, item)

    def _toggle(self):
        self._expanded = not self._expanded
        self._table.setVisible(self._expanded)
        self._btn_toggle.setText("▼" if self._expanded else "▲")
        if self._expanded:
            self.setMaximumHeight(140)
        else:
            self.setMaximumHeight(28)

    def _clear_done(self):
        rows_to_remove = [
            i for i, job in enumerate(self._jobs)
            if job.status in (TransferStatus.DONE, TransferStatus.FAILED,
                               TransferStatus.CANCELLED, TransferStatus.SKIPPED)
        ]
        for row in reversed(rows_to_remove):
            self._table.removeRow(row)
            self._jobs.pop(row)
        self._refresh_title()

    def _refresh_title(self):
        total   = len(self._jobs)
        running = sum(1 for j in self._jobs if j.status == TransferStatus.RUNNING)
        done    = sum(1 for j in self._jobs if j.status == TransferStatus.DONE)
        failed  = sum(1 for j in self._jobs if j.status == TransferStatus.FAILED)

        if running:
            self._title.setText(f"Transfer Queue  [{running} running, {done}/{total} done]")
        elif failed:
            self._title.setText(f"Transfer Queue  [{done} done, {failed} failed]")
        elif total:
            self._title.setText(f"Transfer Queue  [{done}/{total} done]")
        else:
            self._title.setText("Transfer Queue")


def _item(text: str) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return it


def _fmt(n: int) -> str:
    for unit, th in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= th:
            return f"{n / th:.1f} {unit}"
    return f"{n} B"
