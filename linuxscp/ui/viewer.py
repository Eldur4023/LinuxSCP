import os
import tempfile
from PyQt6.QtWidgets import (
    QMainWindow, QPlainTextEdit, QToolBar, QStatusBar,
    QLabel, QLineEdit, QPushButton, QWidget, QHBoxLayout,
    QMessageBox, QCheckBox,
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence, QTextCursor, QFont, QTextCharFormat, QColor

from linuxscp.core.base_session import BaseSession


class FileViewer(QMainWindow):
    """
    F3 read-only file viewer.
    Supports plain text and hex view, Ctrl+F search.
    For remote files: downloads to a temp file first.
    """

    def __init__(self, path: str, session: BaseSession, parent=None):
        super().__init__(parent)
        self._path    = path
        self._session = session
        self._tmpfile = None
        self._hex_mode = False
        self._raw: bytes = b""

        fname = os.path.basename(path) if not session.is_remote else path.split("/")[-1]
        self.setWindowTitle(f"View: {fname}")
        self.setMinimumSize(820, 560)
        self.resize(900, 620)

        self._build_toolbar()
        self._build_editor()
        self._build_find_bar()
        self._build_statusbar()

        self._load()

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_toolbar(self):
        tb = QToolBar()
        tb.setMovable(False)
        tb.setIconSize(QSize(16, 16))
        self.addToolBar(tb)

        find_act = QAction("Find (Ctrl+F)", self)
        find_act.setShortcut(QKeySequence("Ctrl+F"))
        find_act.triggered.connect(self._toggle_find)
        tb.addAction(find_act)

        hex_act = QAction("Hex view", self)
        hex_act.setCheckable(True)
        hex_act.triggered.connect(self._toggle_hex)
        tb.addAction(hex_act)
        self._hex_action = hex_act

        tb.addSeparator()
        close_act = QAction("Close", self)
        close_act.setShortcut(QKeySequence("Escape"))
        close_act.triggered.connect(self.close)
        tb.addAction(close_act)

    def _build_editor(self):
        self._editor = QPlainTextEdit()
        self._editor.setReadOnly(True)
        font = QFont("Courier New", 10)
        font.setFixedPitch(True)
        self._editor.setFont(font)
        self._editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setCentralWidget(self._editor)

    def _build_find_bar(self):
        bar = QWidget()
        bar.setStyleSheet("background: #FFFDE7; border-top: 1px solid #ADADAD;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(6)

        layout.addWidget(QLabel("Find:"))
        self._find_input = QLineEdit()
        self._find_input.setFixedWidth(240)
        self._find_input.returnPressed.connect(self._find_next)
        layout.addWidget(self._find_input)

        btn_prev = QPushButton("◀ Prev")
        btn_prev.setFixedHeight(22)
        btn_prev.clicked.connect(self._find_prev)
        layout.addWidget(btn_prev)

        btn_next = QPushButton("Next ▶")
        btn_next.setFixedHeight(22)
        btn_next.clicked.connect(self._find_next)
        layout.addWidget(btn_next)

        self._chk_case = QCheckBox("Case sensitive")
        layout.addWidget(self._chk_case)

        self._find_status = QLabel("")
        self._find_status.setStyleSheet("color: #666;")
        layout.addWidget(self._find_status)
        layout.addStretch()

        btn_close_find = QPushButton("✕")
        btn_close_find.setFixedSize(20, 20)
        btn_close_find.setFlat(True)
        btn_close_find.clicked.connect(lambda: bar.setVisible(False))
        layout.addWidget(btn_close_find)

        self._find_bar = bar
        bar.setVisible(False)
        # Add as a docked bar below the editor via statusBar area
        self.setMenuWidget(None)
        # We place it as a floating widget above status bar
        self._central_container = QWidget()
        vlay = QHBoxLayout(self._central_container)
        vlay.setContentsMargins(0, 0, 0, 0)
        # actual layout handled differently — inject bar into bottom
        from PyQt6.QtWidgets import QVBoxLayout
        container = QWidget()
        vlay2 = QVBoxLayout(container)
        vlay2.setContentsMargins(0, 0, 0, 0)
        vlay2.setSpacing(0)
        vlay2.addWidget(self._editor)
        vlay2.addWidget(bar)
        self.setCentralWidget(container)

    def _build_statusbar(self):
        sb = self.statusBar()
        self._sb_pos   = QLabel("")
        self._sb_size  = QLabel("")
        self._sb_enc   = QLabel("UTF-8")
        sb.addPermanentWidget(self._sb_pos,  1)
        sb.addPermanentWidget(self._sb_size, 0)
        sb.addPermanentWidget(QLabel("  "),  0)
        sb.addPermanentWidget(self._sb_enc,  0)
        self._editor.cursorPositionChanged.connect(self._update_pos)

    # ── Loading ───────────────────────────────────────────────────────────

    def _load(self):
        if self._session.is_remote:
            self._load_remote()
        else:
            self._load_local()

    def _load_local(self):
        try:
            with open(self._path, "rb") as f:
                self._raw = f.read()
        except OSError as e:
            QMessageBox.critical(self, "Error", str(e))
            return
        self._display()
        size = len(self._raw)
        self._sb_size.setText(f"{size:,} bytes")

    def _load_remote(self):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix="_linuxscp_view")
        self._tmpfile = tmp.name
        tmp.close()

        self.setWindowTitle(f"View: {self._path.split('/')[-1]}  [downloading…]")
        err = self._session.download(self._path, self._tmpfile)
        if err:
            QMessageBox.critical(self, "Download failed", err)
            return
        self.setWindowTitle(f"View: {self._path.split('/')[-1]}")
        self._path = self._tmpfile
        self._load_local()

    def _display(self):
        if self._hex_mode:
            self._editor.setPlainText(_hex_dump(self._raw))
        else:
            text = self._raw.decode("utf-8", errors="replace")
            self._editor.setPlainText(text)

    # ── Find ──────────────────────────────────────────────────────────────

    def _toggle_find(self):
        self._find_bar.setVisible(not self._find_bar.isVisible())
        if self._find_bar.isVisible():
            self._find_input.setFocus()
            self._find_input.selectAll()

    def _find_next(self):
        self._do_find(forward=True)

    def _find_prev(self):
        self._do_find(forward=False)

    def _do_find(self, forward: bool):
        needle = self._find_input.text()
        if not needle:
            return
        flags = QTextCursor.MoveMode.KeepAnchor
        from PyQt6.QtGui import QTextDocument
        opts = QTextDocument.FindFlag(0)
        if not forward:
            opts |= QTextDocument.FindFlag.FindBackward
        if self._chk_case.isChecked():
            opts |= QTextDocument.FindFlag.FindCaseSensitively

        found = self._editor.find(needle, opts)
        if not found:
            # Wrap around
            cursor = self._editor.textCursor()
            cursor.movePosition(
                QTextCursor.MoveOperation.End if not forward else QTextCursor.MoveOperation.Start
            )
            self._editor.setTextCursor(cursor)
            found = self._editor.find(needle, opts)

        self._find_status.setText("" if found else "Not found")

    # ── Hex view ──────────────────────────────────────────────────────────

    def _toggle_hex(self, checked: bool):
        self._hex_mode = checked
        self._display()

    # ── Status ────────────────────────────────────────────────────────────

    def _update_pos(self):
        cursor = self._editor.textCursor()
        line = cursor.blockNumber() + 1
        col  = cursor.columnNumber() + 1
        self._sb_pos.setText(f"Line {line}, Col {col}")

    # ── Cleanup ───────────────────────────────────────────────────────────

    def closeEvent(self, event):
        if self._tmpfile and os.path.exists(self._tmpfile):
            try:
                os.unlink(self._tmpfile)
            except OSError:
                pass
        super().closeEvent(event)


def _hex_dump(data: bytes, width: int = 16) -> str:
    lines = []
    for i in range(0, len(data), width):
        chunk = data[i:i + width]
        hex_part  = " ".join(f"{b:02X}" for b in chunk)
        hex_part  = f"{hex_part:<{width * 3 - 1}}"
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{i:08X}  {hex_part}  {ascii_part}")
    return "\n".join(lines)
