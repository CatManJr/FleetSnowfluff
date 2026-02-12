from __future__ import annotations

import os
import sys
from pathlib import Path


def bootstrap_qt_plugin_paths() -> None:
    # Force deterministic low-noise runtime logs for end users.
    os.environ["QT_FFMPEG_DEBUG"] = "0"
    os.environ["QT_LOGGING_RULES"] = (
        "*.debug=false;"
        "qt.multimedia.*=false;"
        "qt.multimedia.ffmpeg.*=false;"
        "qt.multimedia.ffmpeg=false;"
        "qt.multimedia.playbackengine.*=false;"
        "qt.multimedia.integration.*=false;"
        "qt.accessibility.*=false;"
        "qt.accessibility.table=false"
    )
    # Guard against Qt runtime pollution from external environments (conda/homebrew).
    # These variables can cause Qt to resolve incompatible framework/plugin binaries.
    for key in ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "DYLD_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH"):
        os.environ.pop(key, None)
    if sys.platform == "darwin":
        os.environ["QT_QPA_PLATFORM"] = "cocoa"

    for raw_path in sys.path:
        if not raw_path:
            continue
        plugins_path = Path(raw_path) / "PySide6" / "Qt" / "plugins"
        platforms_path = plugins_path / "platforms"
        if platforms_path.exists():
            # Force override to avoid stale shell env poisoning.
            os.environ["QT_PLUGIN_PATH"] = str(plugins_path)
            os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(platforms_path)
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
