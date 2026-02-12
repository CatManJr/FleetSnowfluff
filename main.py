from __future__ import annotations

import sys
from pathlib import Path

from app.qt_env import bootstrap_qt_plugin_paths, configure_qt_plugin_paths

bootstrap_qt_plugin_paths()

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.aemeath import Aemeath


def _resolve_resources_dir() -> Path:
    """
    Resolve resources path for both source-run and frozen app bundles.
    """
    candidates: list[Path] = []

    if getattr(sys, "frozen", False):
        # PyInstaller onefile/onedir may expose _MEIPASS.
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "resources")

        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend(
            [
                exe_dir / "resources",
                exe_dir.parent / "Resources" / "resources",
            ]
        )

    # Source mode fallback.
    src_root = Path(__file__).resolve().parent.parent
    candidates.append(src_root / "resources")

    for path in candidates:
        if path.exists():
            return path
    # Return the first candidate for clearer downstream error context.
    return candidates[0]


def main() -> None:
    configure_qt_plugin_paths()
    app = QApplication(sys.argv)
    app.setApplicationName("Fleet Snowfluff")
    app.setApplicationDisplayName("Fleet Snowfluff")
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(
        """
        QMessageBox {
            background: #ffffff;
            color: #000000;
        }
        QMessageBox QLabel {
            color: #000000;
        }
        QMessageBox QPushButton {
            color: #000000;
            background: #f7f7f7;
            border: 1px solid #d0d0d0;
            border-radius: 6px;
            padding: 4px 10px;
            min-width: 72px;
        }
        """
    )

    resources_dir = _resolve_resources_dir()
    icon_path = resources_dir / "icon.webp"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    pet = Aemeath(resources_dir=resources_dir)
    if icon_path.exists():
        pet.setWindowIcon(QIcon(str(icon_path)))
    app.setProperty("aemeath", pet)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
