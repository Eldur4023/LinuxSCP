MAIN_STYLE = """
QMainWindow, QWidget {
    background-color: #F0F0F0;
    color: #000000;
    font-family: "Segoe UI", "DejaVu Sans", sans-serif;
    font-size: 9pt;
}

QMenuBar {
    background-color: #F0F0F0;
    border-bottom: 1px solid #ADADAD;
}
QMenuBar::item:selected {
    background-color: #0078D7;
    color: white;
}
QMenu {
    background-color: #FFFFFF;
    color: #000000;
    border: 1px solid #ADADAD;
}
QMenu::item:selected {
    background-color: #0078D7;
    color: white;
}
QMenu::separator {
    height: 1px;
    background: #ADADAD;
    margin: 2px 4px;
}

QToolBar {
    background-color: #F0F0F0;
    border-bottom: 1px solid #ADADAD;
    spacing: 2px;
    padding: 2px;
}
QToolBar QToolButton {
    background-color: transparent;
    border: 1px solid transparent;
    padding: 3px 4px;
    min-width: 24px;
}
QToolBar QToolButton:hover {
    background-color: #CCE4F7;
    border: 1px solid #0078D7;
}
QToolBar QToolButton:pressed {
    background-color: #99C9EF;
}
QToolBar::separator {
    width: 1px;
    background: #ADADAD;
    margin: 3px 2px;
}

QSplitter::handle {
    background-color: #ADADAD;
    width: 4px;
}
QSplitter::handle:hover {
    background-color: #0078D7;
}

QStatusBar {
    background-color: #F0F0F0;
    border-top: 1px solid #ADADAD;
    font-size: 8pt;
}
QStatusBar::item {
    border: none;
}
"""

PANEL_STYLE = """
QWidget#FilePanel {
    background-color: #FFFFFF;
    border: 1px solid #ADADAD;
}

QLineEdit#PathBar {
    background-color: #FFFFFF;
    color: #000000;
    border: 1px solid #7A7A7A;
    border-radius: 0px;
    padding: 1px 4px;
    font-family: "Courier New", monospace;
    font-size: 9pt;
    selection-background-color: #0078D7;
}
QLineEdit#PathBar:focus {
    border: 1px solid #0078D7;
}

QTreeView#FileList {
    background-color: #FFFFFF;
    color: #000000;
    border: none;
    alternate-background-color: #F5F5F5;
    selection-background-color: #0078D7;
    selection-color: #FFFFFF;
    show-decoration-selected: 1;
    outline: 0;
}
QTreeView#FileList::item {
    padding: 1px 0px;
    height: 18px;
}
QTreeView#FileList::item {
    color: #000000;
}
QTreeView#FileList::item:hover {
    background-color: #CCE4F7;
    color: #000000;
}
QTreeView#FileList::item:selected {
    background-color: #0078D7;
    color: #FFFFFF;
}

QHeaderView::section {
    background-color: #E1E1E1;
    color: #000000;
    border: none;
    border-right: 1px solid #ADADAD;
    border-bottom: 1px solid #ADADAD;
    padding: 2px 4px;
    font-size: 8pt;
}
QHeaderView::section:hover {
    background-color: #CCE4F7;
}

QLabel#PanelTitle {
    background-color: #0078D7;
    color: #FFFFFF;
    font-weight: bold;
    padding: 2px 6px;
    font-size: 9pt;
}
QLabel#PanelTitle[active="false"] {
    background-color: #808080;
}
"""

FKEYS_STYLE = """
QWidget#FKeysBar {
    background-color: #C0C0C0;
    border-top: 1px solid #808080;
}
QPushButton#FKeyBtn {
    background-color: #C0C0C0;
    color: #000000;
    border: 1px solid #808080;
    border-radius: 0px;
    padding: 1px 2px;
    font-size: 8pt;
    text-align: left;
    min-height: 20px;
}
QPushButton#FKeyBtn:hover {
    background-color: #A8D4F0;
    border: 1px solid #0078D7;
}
QPushButton#FKeyBtn:pressed {
    background-color: #80BFDF;
}
"""

QUEUE_STYLE = """
QWidget#QueuePanel {
    background-color: #FFFFFF;
    color: #000000;
    border-top: 2px solid #ADADAD;
}
QLabel#QueueTitle {
    background-color: #E1E1E1;
    color: #000000;
    border-bottom: 1px solid #ADADAD;
    padding: 2px 6px;
    font-weight: bold;
    font-size: 8pt;
}
QTreeWidget#QueueList {
    border: none;
    color: #000000;
    font-size: 8pt;
    alternate-background-color: #F5F5F5;
}
"""

SITE_MANAGER_STYLE = """
QDialog {
    background-color: #F0F0F0;
}
QTreeWidget#SiteTree {
    background-color: #FFFFFF;
    border: 1px solid #ADADAD;
    alternate-background-color: #F5F5F5;
}
QTreeWidget#SiteTree::item:selected {
    background-color: #0078D7;
    color: white;
}
QGroupBox {
    border: 1px solid #ADADAD;
    margin-top: 8px;
    font-size: 9pt;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 3px;
}
QPushButton {
    background-color: #E1E1E1;
    color: #000000;
    border: 1px solid #ADADAD;
    padding: 4px 14px;
    min-width: 75px;
}
QPushButton:hover {
    background-color: #CCE4F7;
    border: 1px solid #0078D7;
}
QPushButton:pressed {
    background-color: #99C9EF;
}
QPushButton#ConnectBtn {
    background-color: #0078D7;
    color: white;
    font-weight: bold;
    border: 1px solid #005FA3;
}
QPushButton#ConnectBtn:hover {
    background-color: #1688E7;
}
QComboBox, QLineEdit, QSpinBox {
    background-color: #FFFFFF;
    color: #000000;
    border: 1px solid #ADADAD;
    padding: 3px 5px;
    min-height: 20px;
}
QComboBox:focus, QLineEdit:focus {
    border: 1px solid #0078D7;
}
QTabWidget::pane {
    border: 1px solid #ADADAD;
    background-color: #F0F0F0;
}
QTabBar::tab {
    background-color: #E1E1E1;
    color: #000000;
    border: 1px solid #ADADAD;
    border-bottom: none;
    padding: 4px 10px;
}
QTabBar::tab:selected {
    background-color: #F0F0F0;
    color: #000000;
}
"""
