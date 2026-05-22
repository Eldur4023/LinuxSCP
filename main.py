#!/usr/bin/env python3
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from linuxscp.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("LinuxSCP")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("LinuxSCP")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
