"""Icon loading helpers for music window."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import QSize


def load_icon_from_candidates(
    icon_dir: Path | None, filenames: tuple[str, ...]
) -> QIcon | None:
    if icon_dir is None:
        return None
    for filename in filenames:
        candidate = icon_dir / filename
        if not candidate.exists():
            continue
        icon = QIcon(str(candidate))
        if not icon.isNull():
            return icon
    return None


def mirrored_icon(icon: QIcon) -> QIcon | None:
    if icon.isNull():
        return None
    sizes = icon.availableSizes()
    base_size = sizes[0] if sizes else QSize(64, 64)
    pixmap = icon.pixmap(base_size)
    if pixmap.isNull():
        return None
    mirrored = pixmap.toImage().mirrored(True, False)
    return QIcon(QPixmap.fromImage(mirrored))
