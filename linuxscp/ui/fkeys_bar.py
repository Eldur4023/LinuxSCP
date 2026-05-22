from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, QSizePolicy
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QKeySequence, QShortcut, QFont

from linuxscp.ui.styles import FKEYS_STYLE

FKEYS = [
    (1,  "Help",       "F1"),
    (2,  "Rename",     "F2"),
    (3,  "View",       "F3"),
    (4,  "Edit",       "F4"),
    (5,  "Copy",       "F5"),
    (6,  "Move",       "F6"),
    (7,  "Mkdir",      "F7"),
    (8,  "Delete",     "F8"),
    (9,  "Properties", "F9"),
    (10, "Quit",       "F10"),
]

_NUM_FONT = QFont()
_NUM_FONT.setBold(True)


class _FKeyButton(QWidget):
    """F-key button: bold number prefix + label, styled like WinSCP's bottom bar."""

    clicked = pyqtSignal()

    def __init__(self, num: int, label: str, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            "QWidget { background: #C0C0C0; border: 1px solid #808080; }"
            "QWidget:hover { background: #A8D4F0; border: 1px solid #0078D7; }"
        )

        row = QHBoxLayout(self)
        row.setContentsMargins(4, 1, 4, 1)
        row.setSpacing(2)

        num_lbl = QLabel(str(num))
        num_lbl.setFont(_NUM_FONT)
        num_lbl.setStyleSheet("background: transparent; border: none; color: #000080;")
        num_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        txt_lbl = QLabel(label)
        txt_lbl.setStyleSheet("background: transparent; border: none; color: #000000;")
        txt_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        row.addWidget(num_lbl)
        row.addWidget(txt_lbl)

        sp = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setSizePolicy(sp)
        self.setFixedHeight(22)

    def mousePressEvent(self, event):
        self.clicked.emit()


class FKeysBar(QWidget):
    key_pressed = pyqtSignal(int)   # emits F-key number (1-10)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("FKeysBar")
        self.setFixedHeight(26)
        self.setStyleSheet(FKEYS_STYLE)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        for num, label, fkey in FKEYS:
            btn = _FKeyButton(num, label, self)
            btn.setToolTip(f"{fkey} — {label}")
            n = num
            btn.clicked.connect(lambda n=n: self.key_pressed.emit(n))

            sc = QShortcut(QKeySequence(fkey), parent or self)
            sc.activated.connect(lambda n=n: self.key_pressed.emit(n))

            layout.addWidget(btn)
