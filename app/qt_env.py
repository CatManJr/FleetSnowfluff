from __future__ import annotations

import os
import sys
from pathlib import Path


def bootstrap_qt_plugin_paths() -> None:
    os.environ.setdefault("QT_LOGGING_RULES", "*.debug=false;qt.multimedia.ffmpeg=false")
    for raw_path in sys.path:
        if not raw_path:
            continue
        plugins_path = Path(raw_path) / "PySide6" / "Qt" / "plugins"
        platforms_path = plugins_path / "platforms"
        if platforms_path.exists():
            os.environ.setdefault("QT_PLUGIN_PATH", str(plugins_path))
            os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", str(platforms_path))
            break


def configure_qt_plugin_paths() -> None:
    from PySide6.QtCore import QCoreApplication, QLibraryInfo

    plugins_path = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath))
    platforms_path = plugins_path / "platforms"
    if not platforms_path.exists():
        return

    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(platforms_path)
    os.environ["QT_PLUGIN_PATH"] = str(plugins_path)
    QCoreApplication.setLibraryPaths([str(plugins_path)])
