from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon


class PasswordDialog(QDialog):
    """
    Modal password prompt shown when connecting without a saved password.
    Mirrors WinSCP's authentication dialog.
    """

    def __init__(self, host: str, user: str, prompt: str = "Password:", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Authentication Required")
        self.setFixedWidth(380)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        # Info label
        info = QLabel(f"<b>{user}@{host}</b>")
        info.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(info)

        layout.addWidget(QLabel(prompt))

        # Password field
        self._pwd = QLineEdit()
        self._pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self._pwd.setMinimumWidth(260)
        layout.addWidget(self._pwd)

        # Remember checkbox
        self._remember = QCheckBox("Remember password for this session")
        layout.addWidget(self._remember)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok = QPushButton("OK")
        ok.setDefault(True)
        ok.setFixedWidth(80)
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.setFixedWidth(80)
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(ok)
        btn_row.addWidget(cancel)
        layout.addLayout(btn_row)

        self._pwd.setFocus()

    @property
    def password(self) -> str:
        return self._pwd.text()

    @property
    def remember(self) -> bool:
        return self._remember.isChecked()


class HostKeyDialog(QDialog):
    """
    Shown on first connect to an unknown host — mirrors WinSCP's host key warning.
    """

    def __init__(self, hostname: str, key_type: str, fingerprint: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Unknown Host Key")
        self.setFixedWidth(480)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        warn = QLabel(
            f"<b>Warning:</b> The host key for <b>{hostname}</b> is not cached.<br><br>"
            f"Key type: <tt>{key_type}</tt><br>"
            f"Fingerprint:<br><tt>{fingerprint}</tt><br><br>"
            "Do you want to continue connecting and add this key to the cache?"
        )
        warn.setTextFormat(Qt.TextFormat.RichText)
        warn.setWordWrap(True)
        layout.addWidget(warn)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        yes = QPushButton("Accept")
        yes.setDefault(True)
        yes.setFixedWidth(90)
        yes.clicked.connect(self.accept)

        no = QPushButton("Cancel")
        no.setFixedWidth(90)
        no.clicked.connect(self.reject)

        btn_row.addWidget(yes)
        btn_row.addWidget(no)
        layout.addLayout(btn_row)
