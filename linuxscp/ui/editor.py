import os
import tempfile
from PyQt6.QtWidgets import (
    QMainWindow, QPlainTextEdit, QToolBar, QLabel, QWidget,
    QVBoxLayout, QMessageBox, QStatusBar, QFileDialog,
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence, QFont, QTextCursor

from linuxscp.core.base_session import BaseSession


class FileEditor(QMainWindow):
    """
    F4 built-in text editor.
    Remote files: download → edit → upload on Ctrl+S or close-with-changes.
    """

    file_saved = pyqtSignal(str)   # emits remote path when saved to remote

    def __init__(self, path: str, session: BaseSession, parent=None):
        super().__init__(parent)
        self._path        = path       # original path (remote or local)
        self._session     = session
        self._tmpfile     = None       # temp file for remote edits
        self._remote_path = path if session.is_remote else None
        self._modified    = False

        fname = path.split("/")[-1] if session.is_remote else os.path.basename(path)
        self._fname = fname
        self.setWindowTitle(f"Edit: {fname}")
        self.setMinimumSize(820, 560)
        self.resize(960, 660)

        self._build_toolbar()
        self._build_editor()
        self._build_statusbar()

        self._load()

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_toolbar(self):
        tb = QToolBar()
        tb.setMovable(False)
        tb.setIconSize(QSize(16, 16))
        self.addToolBar(tb)

        save_act = QAction("Save (Ctrl+S)", self)
        save_act.setShortcut(QKeySequence("Ctrl+S"))
        save_act.triggered.connect(self._save)
        tb.addAction(save_act)

        tb.addSeparator()

        find_act = QAction("Find (Ctrl+F)", self)
        find_act.setShortcut(QKeySequence("Ctrl+F"))
        find_act.triggered.connect(self._focus_find)
        tb.addAction(find_act)

        tb.addSeparator()
        close_act = QAction("Close", self)
        close_act.triggered.connect(self.close)
        tb.addAction(close_act)

    def _build_editor(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._editor = QPlainTextEdit()
        font = QFont("Courier New", 10)
        font.setFixedPitch(True)
        self._editor.setFont(font)
        self._editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._editor.document().contentsChanged.connect(self._on_modified)
        layout.addWidget(self._editor)

        # Inline find bar
        from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QLineEdit, QCheckBox
        find_bar = QWidget()
        find_bar.setStyleSheet("background: #FFFDE7; border-top: 1px solid #ADADAD;")
        fl = QHBoxLayout(find_bar)
        fl.setContentsMargins(6, 3, 6, 3)
        fl.setSpacing(6)
        fl.addWidget(QLabel("Find:"))
        self._find_input = QLineEdit()
        self._find_input.setFixedWidth(220)
        self._find_input.returnPressed.connect(self._find_next)
        fl.addWidget(self._find_input)
        for label, slot in (("◀", self._find_prev), ("▶", self._find_next)):
            b = QPushButton(label)
            b.setFixedSize(24, 22)
            b.clicked.connect(slot)
            fl.addWidget(b)
        fl.addWidget(QLabel("Replace:"))
        self._replace_input = QLineEdit()
        self._replace_input.setFixedWidth(180)
        fl.addWidget(self._replace_input)
        rep_btn = QPushButton("Replace")
        rep_btn.setFixedHeight(22)
        rep_btn.clicked.connect(self._replace_one)
        fl.addWidget(rep_btn)
        rep_all = QPushButton("All")
        rep_all.setFixedHeight(22)
        rep_all.clicked.connect(self._replace_all)
        fl.addWidget(rep_all)
        self._find_status = QLabel("")
        self._find_status.setStyleSheet("color: #888;")
        fl.addWidget(self._find_status)
        fl.addStretch()
        close_find = QPushButton("✕")
        close_find.setFixedSize(20, 20)
        close_find.setFlat(True)
        close_find.clicked.connect(lambda: find_bar.setVisible(False))
        fl.addWidget(close_find)
        self._find_bar = find_bar
        find_bar.setVisible(False)
        layout.addWidget(find_bar)

        self.setCentralWidget(container)

    def _build_statusbar(self):
        sb = self.statusBar()
        self._sb_pos    = QLabel("Line 1, Col 1")
        self._sb_status = QLabel("")
        sb.addPermanentWidget(self._sb_pos,    1)
        sb.addPermanentWidget(self._sb_status, 0)
        self._editor.cursorPositionChanged.connect(self._update_pos)

    # ── Loading ───────────────────────────────────────────────────────────

    def _load(self):
        if self._session.is_remote:
            self._load_remote()
        else:
            self._load_local(self._path)

    def _load_remote(self):
        tmp = tempfile.NamedTemporaryFile(
            delete=False, suffix=f"_linuxscp_{self._fname}")
        self._tmpfile = tmp.name
        tmp.close()
        self._path = self._tmpfile  # edit the local copy

        self.setWindowTitle(f"Edit: {self._fname}  [downloading…]")
        err = self._session.download(self._remote_path, self._tmpfile)
        if err:
            QMessageBox.critical(self, "Download failed", err)
            self.close()
            return
        self.setWindowTitle(f"Edit: {self._fname}")
        self._load_local(self._tmpfile)

    def _load_local(self, path: str):
        try:
            with open(path, "r", errors="replace") as f:
                content = f.read()
        except OSError as e:
            QMessageBox.critical(self, "Error opening file", str(e))
            return
        self._editor.setPlainText(content)
        self._modified = False
        self._editor.document().setModified(False)
        self._update_title()

    # ── Save ──────────────────────────────────────────────────────────────

    def _save(self):
        content = self._editor.toPlainText()
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError as e:
            QMessageBox.critical(self, "Save failed", str(e))
            return

        if self._remote_path:
            self._sb_status.setText("Uploading…")
            err = self._session.upload(self._path, self._remote_path)
            if err:
                QMessageBox.critical(self, "Upload failed", err)
                self._sb_status.setText("Upload failed")
                return
            self._sb_status.setText("Saved & uploaded")
            self.file_saved.emit(self._remote_path)
        else:
            self._sb_status.setText("Saved")

        self._modified = False
        self._editor.document().setModified(False)
        self._update_title()

    # ── Find / Replace ────────────────────────────────────────────────────

    def _focus_find(self):
        self._find_bar.setVisible(True)
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
        from PyQt6.QtGui import QTextDocument
        opts = QTextDocument.FindFlag(0)
        if not forward:
            opts |= QTextDocument.FindFlag.FindBackward
        found = self._editor.find(needle, opts)
        if not found:
            cursor = self._editor.textCursor()
            cursor.movePosition(
                QTextCursor.MoveOperation.End if not forward
                else QTextCursor.MoveOperation.Start
            )
            self._editor.setTextCursor(cursor)
            found = self._editor.find(needle, opts)
        self._find_status.setText("" if found else "Not found")

    def _replace_one(self):
        needle      = self._find_input.text()
        replacement = self._replace_input.text()
        cursor = self._editor.textCursor()
        if cursor.hasSelection() and cursor.selectedText() == needle:
            cursor.insertText(replacement)
        self._do_find(forward=True)

    def _replace_all(self):
        needle      = self._find_input.text()
        replacement = self._replace_input.text()
        if not needle:
            return
        content = self._editor.toPlainText()
        new_content = content.replace(needle, replacement)
        count = content.count(needle)
        if count:
            self._editor.setPlainText(new_content)
        self._find_status.setText(f"{count} replaced" if count else "No match")

    # ── Internals ─────────────────────────────────────────────────────────

    def _on_modified(self):
        if not self._modified and self._editor.document().isModified():
            self._modified = True
            self._update_title()

    def _update_title(self):
        dirty = " [modified]" if self._modified else ""
        remote = f"  ({self._remote_path})" if self._remote_path else ""
        self.setWindowTitle(f"Edit: {self._fname}{dirty}{remote}")

    def _update_pos(self):
        cursor = self._editor.textCursor()
        line = cursor.blockNumber() + 1
        col  = cursor.columnNumber() + 1
        self._sb_pos.setText(f"Line {line}, Col {col}")

    def closeEvent(self, event):
        if self._modified:
            reply = QMessageBox.question(
                self, "Unsaved changes",
                f"Save changes to '{self._fname}' before closing?",
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Save:
                self._save()
            elif reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return

        if self._tmpfile and os.path.exists(self._tmpfile):
            try:
                os.unlink(self._tmpfile)
            except OSError:
                pass

        super().closeEvent(event)
