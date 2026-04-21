# ─────────────────────────────────────────────
#  main.py  —  Entry Point
# ─────────────────────────────────────────────

import sys
import os

# Pastikan folder root ada di path
sys.path.insert(0, os.path.dirname(__file__))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from gui.app import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Auto Video Editor")
    app.setOrganizationName("Prhatara")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()