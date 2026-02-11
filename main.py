from __future__ import annotations

import sys
from pathlib import Path

from app.qt_env import bootstrap_qt_plugin_paths, configure_qt_plugin_paths

bootstrap_qt_plugin_paths()

from PySide6.QtWidgets import QApplication

from app.aemeath import Aemeath


def main() -> None:
    configure_qt_plugin_paths()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    root = Path(__file__).resolve().parent.parent
    resources_dir = root / "resources"
    pet = Aemeath(resources_dir=resources_dir)
    app.setProperty("aemeath", pet)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
