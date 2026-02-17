"""Chat input and timeline list widgets."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QListWidget, QPlainTextEdit


class ChatInputBox(QPlainTextEdit):
    submitRequested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._ime_composing = False

    def inputMethodEvent(self, event) -> None:
        self._ime_composing = bool(event.preeditString())
        super().inputMethodEvent(event)
        if not event.preeditString():
            self._ime_composing = False

    def keyPressEvent(self, event) -> None:
        is_enter = event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        modifiers = event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier
        is_plain_enter = modifiers == Qt.KeyboardModifier.NoModifier
        if is_enter and self._ime_composing:
            super().keyPressEvent(event)
            return
        if is_enter and is_plain_enter:
            self.submitRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class ChatTimelineList(QListWidget):
    def keyPressEvent(self, event) -> None:
        bar = self.verticalScrollBar()
        step = max(24, bar.singleStep())
        page = max(step * 4, bar.pageStep())
        key = event.key()
        if key == Qt.Key.Key_Up:
            bar.setValue(bar.value() - step)
            event.accept()
            return
        if key == Qt.Key.Key_Down:
            bar.setValue(bar.value() + step)
            event.accept()
            return
        if key == Qt.Key.Key_PageUp:
            bar.setValue(bar.value() - page)
            event.accept()
            return
        if key == Qt.Key.Key_PageDown:
            bar.setValue(bar.value() + page)
            event.accept()
            return
        if key == Qt.Key.Key_Home:
            bar.setValue(bar.minimum())
            event.accept()
            return
        if key == Qt.Key.Key_End:
            bar.setValue(bar.maximum())
            event.accept()
            return
        super().keyPressEvent(event)
