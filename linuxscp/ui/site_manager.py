from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QLabel, QLineEdit, QComboBox, QSpinBox,
    QTabWidget, QWidget, QFormLayout, QFileDialog,
    QMessageBox, QSplitter, QMenu,
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QKeySequence, QShortcut

from linuxscp.ui.styles import SITE_MANAGER_STYLE
from linuxscp.core.config_store import StoredSession, load_sessions, save_sessions


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


class SiteManager(QDialog):
    connect_requested = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Site Manager – LinuxSCP")
        self.setMinimumSize(780, 520)
        self.setStyleSheet(SITE_MANAGER_STYLE)

        # id(item) → SessionData  (avoids PyQt6 setData copy problem)
        self._data: dict[int, SessionData] = {}
        self._current_item: QTreeWidgetItem | None = None
        self._loading = False   # suppress signals while populating form

        self._build_ui()
        self._load_from_disk()

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(4)

        self._tree = QTreeWidget()
        self._tree.setObjectName("SiteTree")
        self._tree.setHeaderHidden(True)
        self._tree.setMinimumWidth(220)
        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.itemChanged.connect(self._on_item_renamed)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_context_menu)
        ll.addWidget(self._tree)

        del_sc = QShortcut(QKeySequence(Qt.Key.Key_Delete), self._tree)
        del_sc.setContext(Qt.ShortcutContext.WidgetShortcut)
        del_sc.activated.connect(self._delete_item)

        btns = QHBoxLayout()
        for label, slot in (("New Site", self._new_site),
                            ("New Folder", self._new_folder),
                            ("Delete", self._delete_item)):
            b = QPushButton(label)
            b.setFixedHeight(24)
            b.clicked.connect(slot)
            btns.addWidget(b)
        ll.addLayout(btns)
        splitter.addWidget(left)

        # Right panel
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(4, 0, 0, 0)
        rl.setSpacing(6)
        self._tabs = QTabWidget()
        rl.addWidget(self._tabs)
        splitter.addWidget(right)
        splitter.setSizes([240, 520])
        root.addWidget(splitter)

        # Bottom buttons
        br = QHBoxLayout()
        br.addStretch()
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
        br.addWidget(self._btn_save)
        br.addWidget(btn_close)
        br.addSpacing(12)
        br.addWidget(self._btn_connect)
        root.addLayout(br)

        self._build_session_tab()
        self._set_form_enabled(False)

    def _build_session_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)
        form.setContentsMargins(12, 12, 12, 12)

        self._f_name = QLineEdit()
        self._f_name.setPlaceholderText("My Server")

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

        form.addRow("Display name:", self._f_name)
        form.addRow("File Protocol:", self._f_protocol)
        form.addRow("Host name:", self._f_host)
        form.addRow("Port number:", self._f_port)
        form.addRow("User name:", self._f_user)
        form.addRow("Password:", self._f_password)
        form.addRow("Private key file:", key_row)
        form.addRow("Remote directory:", self._f_remote_dir)
        form.addRow("Local directory:", local_row)

        self._tabs.addTab(tab, "Session")

        adv = QWidget()
        adv_l = QVBoxLayout(adv)
        adv_l.addWidget(QLabel("Advanced settings — coming soon."))
        adv_l.addStretch()
        self._tabs.addTab(adv, "Advanced")

    # ── Helpers ───────────────────────────────────────────────────────────

    def _get_data(self, item: QTreeWidgetItem) -> SessionData | None:
        return self._data.get(id(item))

    def _set_data(self, item: QTreeWidgetItem, data: SessionData):
        self._data[id(item)] = data

    def _is_folder(self, item: QTreeWidgetItem) -> bool:
        return id(item) not in self._data

    # ── Persistence ───────────────────────────────────────────────────────

    def _load_from_disk(self):
        self._loading = True
        stored = load_sessions()
        groups: dict[str, QTreeWidgetItem] = {}

        def _get_group(name: str) -> QTreeWidgetItem:
            if name not in groups:
                g = QTreeWidgetItem(self._tree, [name])
                g.setFlags(g.flags() | Qt.ItemFlag.ItemIsEditable)
                groups[name] = g
            return groups[name]

        if not stored:
            g = QTreeWidgetItem(self._tree, ["My Sites"])
            g.setFlags(g.flags() | Qt.ItemFlag.ItemIsEditable)
        else:
            for ss in stored:
                grp = _get_group(ss.group or "My Sites")
                data = _stored_to_session_data(ss)
                label = ss.name or (f"{ss.user}@{ss.host}" if ss.host else "Session")
                item = QTreeWidgetItem(grp, [label])
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                self._set_data(item, data)

        self._tree.expandAll()
        self._loading = False
        self._auto_select_first()

    def _save_to_disk(self):
        stored: list[StoredSession] = []

        def _walk(parent: QTreeWidgetItem, group_name: str):
            for i in range(parent.childCount()):
                child = parent.child(i)
                d = self._get_data(child)
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

    def _auto_select_first(self):
        root = self._tree.invisibleRootItem()

        def _first_leaf(item):
            if self._get_data(item) is not None:
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
            self._new_site()

    # ── Tree actions ──────────────────────────────────────────────────────

    def _new_site(self):
        cur = self._tree.currentItem()
        if cur is not None and self._get_data(cur) is not None:
            folder = cur.parent() or self._tree.topLevelItem(0)
        elif cur is not None:
            folder = cur
        else:
            folder = self._tree.topLevelItem(0)

        if folder is None:
            folder = QTreeWidgetItem(self._tree, ["My Sites"])
            folder.setFlags(folder.flags() | Qt.ItemFlag.ItemIsEditable)

        item = QTreeWidgetItem(folder, ["New Session"])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        data = SessionData()
        self._set_data(item, data)
        self._current_item = item
        self._tree.expandAll()
        self._tree.setCurrentItem(item)
        self._load_form(data)
        self._set_form_enabled(True)
        self._f_host.setFocus()

    def _new_folder(self):
        folder = QTreeWidgetItem(self._tree, ["New Folder"])
        folder.setFlags(folder.flags() | Qt.ItemFlag.ItemIsEditable)
        self._tree.setCurrentItem(folder)
        self._save_to_disk()
        self._tree.editItem(folder)

    def _delete_item(self):
        item = self._tree.currentItem()
        if not item:
            return
        reply = QMessageBox.question(
            self, "Delete", f'Delete "{item.text(0)}"?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            if self._current_item is item:
                self._current_item = None
                self._set_form_enabled(False)
            self._data.pop(id(item), None)
            (item.parent() or self._tree.invisibleRootItem()).removeChild(item)
            self._save_to_disk()

    def _on_item_clicked(self, item: QTreeWidgetItem, _col):
        data = self._get_data(item)
        if data is not None:
            self._current_item = item
            self._load_form(data)
            self._set_form_enabled(True)
        else:
            self._current_item = None
            self._set_form_enabled(False)

    def _show_context_menu(self, pos: QPoint):
        menu = QMenu(self)
        menu.addAction("New Site",   self._new_site)
        menu.addAction("New Folder", self._new_folder)
        item = self._tree.itemAt(pos)
        if item:
            menu.addSeparator()
            menu.addAction("Rename", lambda: self._tree.editItem(item))
            act_del = menu.addAction("Delete")
            act_del.triggered.connect(self._delete_item)
        menu.exec(self._tree.viewport().mapToGlobal(pos))

    def _on_item_renamed(self, item: QTreeWidgetItem, _col):
        if self._loading:
            return
        # If it's a session leaf, sync the name field too
        data = self._get_data(item)
        if data is not None:
            data.name = item.text(0)
            if self._current_item is item:
                self._loading = True
                self._f_name.setText(item.text(0))
                self._loading = False
        self._save_to_disk()

    # ── Form ──────────────────────────────────────────────────────────────

    def _load_form(self, data: SessionData):
        self._loading = True
        self._f_name.setText(data.name)
        self._f_protocol.setCurrentText(data.protocol)
        self._f_host.setText(data.host)
        self._f_port.setValue(data.port)
        self._f_user.setText(data.user)
        self._f_password.setText(data.password)
        self._f_keyfile.setText(data.key_file)
        self._f_remote_dir.setText(data.remote_dir)
        self._f_local_dir.setText(data.local_dir)
        self._loading = False

    def _save_current(self):
        if self._current_item is None:
            return
        data = self._get_data(self._current_item)
        if data is None:
            return
        data.name       = self._f_name.text().strip() or "New Session"
        data.protocol   = self._f_protocol.currentText()
        data.host       = self._f_host.text().strip()
        data.port       = self._f_port.value()
        data.user       = self._f_user.text().strip()
        data.password   = self._f_password.text()
        data.key_file   = self._f_keyfile.text().strip()
        data.remote_dir = self._f_remote_dir.text().strip()
        data.local_dir  = self._f_local_dir.text().strip()

        # Update tree label with display name (or user@host if name is default)
        label = data.name if data.name != "New Session" else (
            f"{data.user}@{data.host}" if data.user and data.host else
            data.host or data.name)
        self._loading = True
        self._current_item.setText(0, label)
        self._loading = False

        self._save_to_disk()

    def _do_connect(self):
        self._save_current()
        if self._current_item is None:
            return
        data = self._get_data(self._current_item)
        if not data or not data.host:
            QMessageBox.warning(self, "Missing host", "Please enter a host name.")
            return
        self.connect_requested.emit(data)
        self.accept()

    def _on_protocol_changed(self, proto: str):
        if self._loading:
            return
        defaults = {"SFTP": 22, "SCP": 22, "FTP": 21, "FTPS": 990, "WebDAV": 80, "S3": 443}
        self._f_port.setValue(defaults.get(proto, 22))

    def _set_form_enabled(self, enabled: bool):
        for w in (self._f_name, self._f_protocol, self._f_host, self._f_port,
                  self._f_user, self._f_password, self._f_keyfile,
                  self._f_remote_dir, self._f_local_dir,
                  self._btn_browse_key, self._btn_browse_local,
                  self._btn_save, self._btn_connect):
            w.setEnabled(enabled)

    def closeEvent(self, event):
        self._save_to_disk()
        super().closeEvent(event)

    def _browse_key(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select private key", "",
            "Key files (*.pem *.ppk *.key);;All files (*)")
        if path:
            self._f_keyfile.setText(path)

    def _browse_local(self):
        path = QFileDialog.getExistingDirectory(self, "Select local directory")
        if path:
            self._f_local_dir.setText(path)


# ── helpers ───────────────────────────────────────────────────────────────────

def _stored_to_session_data(ss: StoredSession) -> SessionData:
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
