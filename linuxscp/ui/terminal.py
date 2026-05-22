"""
Embedded terminal for LinuxSCP.

- SSH sessions: uses paramiko invoke_shell() + ChannelReader thread
- Local sessions: spawns the user's $SHELL via pty + PtyReader thread
- Output: QTextEdit with basic ANSI colour parsing
- Input:  QLineEdit with command history (↑/↓)
- "Open external terminal here" button as fallback
"""
import os
import re
import select
import subprocess
import threading
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit,
    QPushButton, QLabel, QSizePolicy, QToolBar,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QTextCursor, QTextCharFormat, QColor, QFont, QAction, QKeyEvent

# ── ANSI parser ────────────────────────────────────────────────────────────

_ANSI_RE = re.compile(r'\x1b\[([0-9;]*)([A-Za-z])')
_ANSI_COLORS = {
    30: "#000000", 31: "#CC0000", 32: "#00CC00", 33: "#CCCC00",
    34: "#0000CC", 35: "#CC00CC", 36: "#00CCCC", 37: "#CCCCCC",
    90: "#666666", 91: "#FF3333", 92: "#33FF33", 93: "#FFFF33",
    94: "#3333FF", 95: "#FF33FF", 96: "#33FFFF", 97: "#FFFFFF",
}
_ANSI_BG = {k + 10: v for k, v in _ANSI_COLORS.items()}


def _parse_ansi(text: str) -> list[tuple[str, QTextCharFormat]]:
    """Return list of (chunk, QTextCharFormat). Strips unsupported codes."""
    result = []
    fmt = QTextCharFormat()
    pos = 0
    for m in _ANSI_RE.finditer(text):
        if m.start() > pos:
            result.append((text[pos:m.start()], QTextCharFormat(fmt)))
        cmd   = m.group(2)
        codes = [int(x) for x in m.group(1).split(";") if x] if m.group(1) else [0]
        if cmd == "m":
            for code in codes:
                if code == 0:
                    fmt = QTextCharFormat()
                elif code == 1:
                    fmt.setFontWeight(QFont.Weight.Bold)
                elif code == 22:
                    fmt.setFontWeight(QFont.Weight.Normal)
                elif code in _ANSI_COLORS:
                    fmt.setForeground(QColor(_ANSI_COLORS[code]))
                elif code in _ANSI_BG:
                    fmt.setBackground(QColor(_ANSI_BG[code]))
                elif code == 39:
                    fmt.clearForeground()
                elif code == 49:
                    fmt.clearBackground()
        pos = m.end()
    if pos < len(text):
        result.append((text[pos:], QTextCharFormat(fmt)))
    return result


# ── Reader threads ─────────────────────────────────────────────────────────

class ChannelReader(QThread):
    """Reads from a paramiko Channel and emits received text."""
    text_received = pyqtSignal(str)
    closed        = pyqtSignal()

    def __init__(self, channel, parent=None):
        super().__init__(parent)
        self._channel = channel

    def run(self):
        while not self._channel.closed:
            try:
                if self._channel.recv_ready():
                    data = self._channel.recv(4096)
                    if data:
                        self.text_received.emit(data.decode("utf-8", errors="replace"))
                    else:
                        break
                else:
                    self._channel.settimeout(0.1)
                    try:
                        data = self._channel.recv(4096)
                        if not data:
                            break
                        self.text_received.emit(data.decode("utf-8", errors="replace"))
                    except Exception:
                        pass
            except Exception:
                break
        self.closed.emit()


class PtyReader(QThread):
    """Reads from a pty master fd and emits received text."""
    text_received = pyqtSignal(str)
    closed        = pyqtSignal()

    def __init__(self, fd: int, parent=None):
        super().__init__(parent)
        self._fd   = fd
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        while not self._stop:
            try:
                r, _, _ = select.select([self._fd], [], [], 0.1)
                if r:
                    data = os.read(self._fd, 4096)
                    if data:
                        self.text_received.emit(data.decode("utf-8", errors="replace"))
            except OSError:
                break
        self.closed.emit()


# ── Terminal widget ────────────────────────────────────────────────────────

class TerminalPanel(QWidget):
    """
    Embedded terminal panel.
    Call connect_ssh(sftp_session) or connect_local(work_dir) to activate.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._channel   = None   # paramiko channel
        self._pty_fd    = None   # pty master fd
        self._proc      = None   # local subprocess
        self._reader    = None   # ChannelReader or PtyReader
        self._history:  list[str] = []
        self._hist_idx: int = -1

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Toolbar ───────────────────────────────────────────────────────
        tb = QToolBar()
        tb.setMovable(False)
        tb.setIconSize(QSize(14, 14))
        tb.setStyleSheet("QToolBar { border: none; background: #E8E8E8; border-bottom: 1px solid #ADADAD; }")

        self._title_label = QLabel("  Terminal")
        self._title_label.setStyleSheet("font-weight: bold; font-size: 8pt;")
        tb.addWidget(self._title_label)

        clear_act = QAction("Clear", self)
        clear_act.triggered.connect(self._output.clear if hasattr(self, '_output') else lambda: None)
        tb.addSeparator()

        self._btn_ext = QPushButton("Open in system terminal")
        self._btn_ext.setFixedHeight(20)
        self._btn_ext.setStyleSheet("font-size: 8pt; padding: 0 6px;")
        self._btn_ext.clicked.connect(self._open_external)
        tb.addWidget(self._btn_ext)
        layout.addWidget(tb)

        # ── Output ────────────────────────────────────────────────────────
        self._output = QTextEdit()
        self._output.setReadOnly(True)
        font = QFont("Courier New", 9)
        font.setFixedPitch(True)
        self._output.setFont(font)
        self._output.setStyleSheet(
            "QTextEdit { background: #1E1E1E; color: #D4D4D4; border: none; }")
        self._output.document().setMaximumBlockCount(5000)
        layout.addWidget(self._output)

        # Re-wire clear after output is created
        clear_act.triggered.disconnect()
        clear_act.triggered.connect(self._output.clear)

        # ── Input row ─────────────────────────────────────────────────────
        input_row = QWidget()
        input_row.setStyleSheet("background: #2D2D2D;")
        ir = QHBoxLayout(input_row)
        ir.setContentsMargins(4, 2, 4, 2)
        ir.setSpacing(4)

        prompt = QLabel("$")
        prompt.setStyleSheet("color: #00FF00; font-family: 'Courier New'; font-size: 9pt;")
        ir.addWidget(prompt)

        self._input = QLineEdit()
        self._input.setStyleSheet(
            "QLineEdit { background: #2D2D2D; color: #D4D4D4; border: none; "
            "font-family: 'Courier New'; font-size: 9pt; }")
        self._input.returnPressed.connect(self._send_command)
        self._input.installEventFilter(self)
        ir.addWidget(self._input)

        layout.addWidget(input_row)
        self.setMinimumHeight(200)

    # ── Connect ───────────────────────────────────────────────────────────

    def connect_ssh(self, sftp_session, title: str = ""):
        """Attach to an active SFTPSession."""
        self._disconnect()
        self._title_label.setText(f"  Terminal — {title or sftp_session.label}")
        try:
            channel = sftp_session._client.invoke_shell(term="xterm", width=220, height=50)
            self._channel = channel
            reader = ChannelReader(channel, parent=self)
            reader.text_received.connect(self._append_output)
            reader.closed.connect(self._on_reader_closed)
            reader.start()
            self._reader = reader
            self._append_system("Connected. Type commands below.\n")
        except Exception as e:
            self._append_system(f"Failed to open shell: {e}\n")

    def connect_local(self, work_dir: str = ""):
        """Open a local shell using pty."""
        self._disconnect()
        work_dir = work_dir or os.path.expanduser("~")
        self._title_label.setText(f"  Terminal — Local ({work_dir})")
        try:
            import pty
            master_fd, slave_fd = pty.openpty()
            shell = os.environ.get("SHELL", "/bin/bash")
            proc = subprocess.Popen(
                [shell],
                stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
                close_fds=True, cwd=work_dir,
                env={**os.environ, "TERM": "xterm"},
            )
            os.close(slave_fd)
            self._pty_fd = master_fd
            self._proc   = proc

            reader = PtyReader(master_fd, parent=self)
            reader.text_received.connect(self._append_output)
            reader.closed.connect(self._on_reader_closed)
            reader.start()
            self._reader = reader
        except Exception as e:
            self._append_system(f"Failed to open local shell: {e}\n"
                                f"Use 'Open in system terminal' instead.\n")

    def _disconnect(self):
        if self._reader:
            if isinstance(self._reader, PtyReader):
                self._reader.stop()
            self._reader = None
        if self._channel:
            try: self._channel.close()
            except Exception: pass
            self._channel = None
        if self._proc:
            try: self._proc.terminate()
            except Exception: pass
            self._proc = None
        if self._pty_fd is not None:
            try: os.close(self._pty_fd)
            except Exception: pass
            self._pty_fd = None

    def closeEvent(self, event):
        self._disconnect()
        super().closeEvent(event)

    # ── I/O ───────────────────────────────────────────────────────────────

    def _send_command(self):
        cmd = self._input.text()
        if not cmd:
            return
        self._history.append(cmd)
        self._hist_idx = len(self._history)
        self._input.clear()

        raw = (cmd + "\n").encode("utf-8")
        if self._channel:
            try: self._channel.send(raw)
            except Exception: pass
        elif self._pty_fd is not None:
            try: os.write(self._pty_fd, raw)
            except OSError: pass

    def _append_output(self, text: str):
        cursor = self._output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        # Handle \r\n and \r
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        chunks = _parse_ansi(text)
        for chunk, fmt in chunks:
            cursor.insertText(chunk, fmt)
        self._output.setTextCursor(cursor)
        self._output.ensureCursorVisible()

    def _append_system(self, text: str):
        fmt = QTextCharFormat()
        fmt.setForeground(QColor("#888888"))
        cursor = self._output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text, fmt)
        self._output.ensureCursorVisible()

    def _on_reader_closed(self):
        self._append_system("\n[Connection closed]\n")

    # ── History navigation ────────────────────────────────────────────────

    def eventFilter(self, source, event):
        if source is self._input and isinstance(event, QKeyEvent):
            if event.key() == Qt.Key.Key_Up:
                if self._history and self._hist_idx > 0:
                    self._hist_idx -= 1
                    self._input.setText(self._history[self._hist_idx])
                return True
            if event.key() == Qt.Key.Key_Down:
                if self._hist_idx < len(self._history) - 1:
                    self._hist_idx += 1
                    self._input.setText(self._history[self._hist_idx])
                else:
                    self._hist_idx = len(self._history)
                    self._input.clear()
                return True
        return super().eventFilter(source, event)

    # ── External terminal ────────────────────────────────────────────────

    def _open_external(self):
        """Launch system terminal emulator as fallback."""
        work_dir = os.path.expanduser("~")
        for term in ("gnome-terminal", "konsole", "xfce4-terminal", "xterm", "lxterminal"):
            try:
                subprocess.Popen([term, "--working-directory", work_dir])
                return
            except FileNotFoundError:
                continue
        self._append_system("No terminal emulator found (tried gnome-terminal, konsole, xterm).\n")
