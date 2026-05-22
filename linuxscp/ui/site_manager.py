from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QLabel, QLineEdit, QComboBox, QSpinBox, QCheckBox,
    QTabWidget, QWidget, QGroupBox, QFormLayout, QFileDialog,
    QMessageBox, QSplitter, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon

from linuxscp.ui.styles import SITE_MANAGER_STYLE
from linuxscp.core.config_store import (
    StoredSession, load_sessions, save_sessions,
)

_ROLE = Qt.ItemDataRole.UserRole   # stores SessionData on each leaf item


class SessionData:
    def __init__(self):
        self.name       = "New Session"
        self.protocol   = "SFTP"
        self.host       = ""
        self.port       = 22
        self.user       = ""
        self.password   = ""
        self.key_file   = ""
        self.remote_dir = ""
        self.local_dir  = ""
        self.notes      = ""


def _item_data(item: QTreeWidgetItem) -> SessionData | None:
    """Return the SessionData stored on a tree item, or None for folders."""
    return item.data(0, _ROLE)


def _set_item_data(item: QTreeWidgetItem, data: SessionData):
    item.setData(0, _ROLE, data)


class SiteManager(QDialog):
    connect_requested = pyqtSignal(object)   # emits SessionData

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Site Manager – LinuxSCP")
        self.setMinimumSize(780, 520)
        self.setStyleSheet(SITE_MANAGER_STYLE)
        self._current_item: QTreeWidgetItem | None = None
        self._building = False
        self._build_ui()
        self._load_from_disk()

    # ── UI construction ───────────────────────────────────────────────────

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(6)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Left: site tree + tree buttons ───────────────────────────────
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        self._tree = QTreeWidget()
        self._tree.setObjectName("SiteTree")
        self._tree.setHeaderHidden(True)
        self._tree.setMinimumWidth(220)
        self._tree.itemClicked.connect(self._on_item_clicked)
        left_layout.addWidget(self._tree)

        tree_btns = QHBoxLayout()
        for label, slot in (
            ("New Site",   self._new_site),
            ("New Folder", self._new_folder),
            ("Delete",     self._delete_item),
        ):
            btn = QPushButton(label)
            btn.setFixedHeight(24)
            btn.clicked.connect(slot)
            tree_btns.addWidget(btn)
        left_layout.addLayout(tree_btns)
        splitter.addWidget(left)

        # ── Right: session form ───────────────────────────────────────────
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 0, 0, 0)
        right_layout.setSpacing(6)

        self._tabs = QTabWidget()
        right_layout.addWidget(self._tabs)
        splitter.addWidget(right)
        splitter.setSizes([240, 520])

        root_layout.addWidget(splitter)

        # ── Bottom buttons ────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._btn_save = QPushButton("Save")
        self._btn_save.setFixedSize(90, 28)
        self._btn_save.clicked.connect(self._save_current)

        self._btn_connect = QPushButton("Login")
        self._btn_connect.setObjectName("ConnectBtn")
        self._btn_connect.setFixedSize(90, 28)
        self._btn_connect.clicked.connect(self._do_connect)

        btn_close = QPushButton("Close")
        btn_close.setFixedSize(90, 28)
        btn_close.clicked.connect(self.reject)

        btn_row.addWidget(self._btn_save)
        btn_row.addWidget(btn_close)
        btn_row.addSpacing(12)
        btn_row.addWidget(self._btn_connect)
        root_layout.addLayout(btn_row)

        self._build_session_tab()

    def _build_session_tab(self):
        session_tab = QWidget()
        form = QFormLayout(session_tab)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)
        form.setContentsMargins(12, 12, 12, 12)

        self._f_protocol = QComboBox()
        self._f_protocol.addItems(["SFTP", "SCP", "FTP", "FTPS", "WebDAV", "S3"])
        self._f_protocol.currentTextChanged.connect(self._on_protocol_changed)

        self._f_host = QLineEdit()
        self._f_host.setPlaceholderText("hostname or IP")

        self._f_port = QSpinBox()
        self._f_port.setRange(1, 65535)
        self._f_port.setValue(22)
        self._f_port.setFixedWidth(80)

        self._f_user = QLineEdit()
        self._f_user.setPlaceholderText("username")

        self._f_password = QLineEdit()
        self._f_password.setEchoMode(QLineEdit.EchoMode.Password)
        self._f_password.setPlaceholderText("leave empty to prompt on connect")

        self._f_keyfile = QLineEdit()
        self._f_keyfile.setPlaceholderText("private key file (optional)")
        self._btn_browse_key = QPushButton("...")
        self._btn_browse_key.setFixedWidth(28)
        self._btn_browse_key.clicked.connect(self._browse_key)
        key_row = QHBoxLayout()
        key_row.setSpacing(4)
        key_row.addWidget(self._f_keyfile)
        key_row.addWidget(self._btn_browse_key)

        self._f_remote_dir = QLineEdit()
        self._f_remote_dir.setPlaceholderText("/home/user  (leave empty for default)")

        self._f_local_dir = QLineEdit()
        self._f_local_dir.setPlaceholderText("local directory")
        self._btn_browse_local = QPushButton("...")
        self._btn_browse_local.setFixedWidth(28)
        self._btn_browse_local.clicked.connect(self._browse_local)
        local_row = QHBoxLayout()
        local_row.setSpacing(4)
        local_row.addWidget(self._f_local_dir)
        local_row.addWidget(self._btn_browse_local)

        form.addRow("File Protocol:", self._f_protocol)
        form.addRow("Host name:", self._f_host)
        form.addRow("Port number:", self._f_port)
        form.addRow("User name:", self._f_user)
        form.addRow("Password:", self._f_password)
        form.addRow("Private key file:", key_row)
        form.addRow("Remote directory:", self._f_remote_dir)
        form.addRow("Local directory:", local_row)

        self._tabs.addTab(session_tab, "Session")

        adv_tab = QWidget()
        adv_layout = QVBoxLayout(adv_tab)
        adv_layout.addWidget(QLabel("Advanced settings — coming soon."))
        adv_layout.addStretch()
        self._tabs.addTab(adv_tab, "Advanced")

    # ── Persistence ───────────────────────────────────────────────────────

    def _load_from_disk(self):
        stored = load_sessions()
        groups: dict[str, QTreeWidgetItem] = {}

        def _get_group(name: str) -> QTreeWidgetItem:
            if name not in groups:
                item = QTreeWidgetItem(self._tree, [name])
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                groups[name] = item
            return groups[name]

        if not stored:
            root = QTreeWidgetItem(self._tree, ["My Sites"])
            root.setFlags(root.flags() | Qt.ItemFlag.ItemIsEditable)
        else:
            for ss in stored:
                grp = _get_group(ss.group or "My Sites")
                data = _stored_to_session_data(ss)
                display = f"{ss.user}@{ss.host}" if ss.host else ss.name
                item = QTreeWidgetItem(grp, [display])
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                _set_item_data(item, data)

        self._tree.expandAll()
        self._auto_select_first()

    def _auto_select_first(self):
        """Select first session leaf, or open blank form if none exist."""
        root = self._tree.invisibleRootItem()

        def _first_leaf(item: QTreeWidgetItem) -> QTreeWidgetItem | None:
            if _item_data(item) is not None:
                return item
            for i in range(item.childCount()):
                found = _first_leaf(item.child(i))
                if found:
                    return found
            return None

        leaf = None
        for i in range(root.childCount()):
            leaf = _first_leaf(root.child(i))
            if leaf:
                break

        if leaf:
            self._tree.setCurrentItem(leaf)
            self._on_item_clicked(leaf, 0)
        else:
            # No saved sessions — open a blank form ready to fill in
            self._new_site()

    def _save_to_disk(self):
        stored: list[StoredSession] = []

        def _walk(parent_item: QTreeWidgetItem, group_name: str):
            for i in range(parent_item.childCount()):
                child = parent_item.child(i)
                d = _item_data(child)
                if d is not None:
                    stored.append(StoredSession(
                        name       = child.text(0),
                        protocol   = d.protocol,
                        host       = d.host,
                        port       = d.port,
                        user       = d.user,
                        password   = d.password,
                        key_file   = d.key_file,
                        remote_dir = d.remote_dir,
                        local_dir  = d.local_dir,
                        group      = group_name,
                    ))
                else:
                    _walk(child, child.text(0))

        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            top = root.child(i)
            _walk(top, top.text(0))

        save_sessions(stored)

    # ── Tree actions ──────────────────────────────────────────────────────

    def _new_site(self):
        cur = self._tree.currentItem()
        # Find the target folder: if current item is a session leaf, go to its parent
        if cur is not None and _item_data(cur) is not None:
            folder = cur.parent() or self._tree.topLevelItem(0)
        elif cur is not None:
            folder = cur   # cur is a folder
        else:
            folder = self._tree.topLevelItem(0)

        if folder is not None:
            item = QTreeWidgetItem(folder, ["New Session"])
        else:
            # No top-level folder at all; create a root folder on the fly
            folder = QTreeWidgetItem(self._tree, ["My Sites"])
            folder.setFlags(folder.flags() | Qt.ItemFlag.ItemIsEditable)
            item = QTreeWidgetItem(folder, ["New Session"])

        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        data = SessionData()
        _set_item_data(item, data)
        self._current_item = item
        self._tree.expandAll()
        self._tree.setCurrentItem(item)
        self._load_session(data)
        self._set_form_enabled(True)
        self._f_host.setFocus()

    def _new_folder(self):
        folder = QTreeWidgetItem(self._tree, ["New Folder"])
        folder.setFlags(folder.flags() | Qt.ItemFlag.ItemIsEditable)
        self._tree.setCurrentItem(folder)
        self._tree.editItem(folder)

    def _delete_item(self):
        item = self._tree.currentItem()
        if not item:
            return
        name = item.text(0)
        reply = QMessageBox.question(
            self, "Delete", f'Delete "{name}"?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            if self._current_item is item:
                self._current_item = None
            parent = item.parent() or self._tree.invisibleRootItem()
            parent.removeChild(item)
            self._set_form_enabled(False)

    def _on_item_clicked(self, item: QTreeWidgetItem, _col):
        data = _item_data(item)
        if data is not None:
            self._current_item = item
            self._load_session(data)
            self._set_form_enabled(True)
        else:
            self._current_item = None
            self._set_form_enabled(False)

    # ── Form helpers ──────────────────────────────────────────────────────

    def _load_session(self, data: SessionData):
        self._building = True
        self._f_protocol.setCurrentText(data.protocol)
        self._f_host.setText(data.host)
        self._f_port.setValue(data.port)
        self._f_user.setText(data.user)
        self._f_password.setText(data.password)
        self._f_keyfile.setText(data.key_file)
        self._f_remote_dir.setText(data.remote_dir)
        self._f_local_dir.setText(data.local_dir)
        self._building = False

    def _save_current(self):
        if self._current_item is None:
            return
        data = _item_data(self._current_item)
        if data is None:
            return
        data.protocol   = self._f_protocol.currentText()
        data.host       = self._f_host.text().strip()
        data.port       = self._f_port.value()
        data.user       = self._f_user.text().strip()
        data.password   = self._f_password.text()
        data.key_file   = self._f_keyfile.text().strip()
        data.remote_dir = self._f_remote_dir.text().strip()
        data.local_dir  = self._f_local_dir.text().strip()
        label = f"{data.user}@{data.host}" if data.user and data.host else data.host or "New Session"
        self._current_item.setText(0, label)
        self._save_to_disk()

    def _do_connect(self):
        self._save_current()
        if self._current_item is None:
            return
        data = _item_data(self._current_item)
        if not data or not data.host:
            QMessageBox.warning(self, "Missing host", "Please enter a host name.")
            return
        self.connect_requested.emit(data)
        self.accept()

    def _on_protocol_changed(self, proto: str):
        if self._building:
            return
        defaults = {"SFTP": 22, "SCP": 22, "FTP": 21, "FTPS": 990, "WebDAV": 80, "S3": 443}
        self._f_port.setValue(defaults.get(proto, 22))

    def _set_form_enabled(self, enabled: bool):
        for w in (self._f_protocol, self._f_host, self._f_port, self._f_user,
                  self._f_password, self._f_keyfile, self._f_remote_dir, self._f_local_dir,
                  self._btn_browse_key, self._btn_browse_local,
                  self._btn_save, self._btn_connect):
            w.setEnabled(enabled)

    def _browse_key(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select private key", "", "Key files (*.pem *.ppk *.key);;All files (*)")
        if path:
            self._f_keyfile.setText(path)

    def _browse_local(self):
        path = QFileDialog.getExistingDirectory(self, "Select local directory")
        if path:
            self._f_local_dir.setText(path)


# ── Module-level helpers ───────────────────────────────────────────────────

def _stored_to_session_data(ss: "StoredSession") -> "SessionData":
    d = SessionData()
    d.name       = ss.name
    d.protocol   = ss.protocol
    d.host       = ss.host
    d.port       = ss.port
    d.user       = ss.user
    d.password   = ss.password
    d.key_file   = ss.key_file
    d.remote_dir = ss.remote_dir
    d.local_dir  = ss.local_dir
    return d
