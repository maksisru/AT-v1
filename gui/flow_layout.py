"""Qt FlowLayout that wraps card widgets without using GridLayout."""
from __future__ import annotations

try:
    from PyQt5.QtCore import QPoint, QRect, QSize, Qt
    from PyQt5.QtWidgets import QLayout, QSizePolicy
except ImportError:  # pragma: no cover - allows headless non-GUI tests
    QLayout = object  # type: ignore


if QLayout is not object:
    class FlowLayout(QLayout):
        """A wrapping layout for freely ordered card widgets."""

        def __init__(self, parent=None, margin=0, spacing=10):
            super().__init__(parent)
            self._items = []
            self.setContentsMargins(margin, margin, margin, margin)
            self.setSpacing(spacing)

        def addItem(self, item):
            self._items.append(item)

        def count(self):
            return len(self._items)

        def itemAt(self, index):
            return self._items[index] if 0 <= index < len(self._items) else None

        def takeAt(self, index):
            return self._items.pop(index) if 0 <= index < len(self._items) else None

        def expandingDirections(self):
            return Qt.Orientations(Qt.Orientation(0))

        def hasHeightForWidth(self):
            return True

        def heightForWidth(self, width):
            return self._do_layout(QRect(0, 0, width, 0), True)

        def setGeometry(self, rect):
            super().setGeometry(rect)
            self._do_layout(rect, False)

        def sizeHint(self):
            return self.minimumSize()

        def minimumSize(self):
            size = QSize()
            for item in self._items:
                size = size.expandedTo(item.minimumSize())
            margins = self.contentsMargins()
            size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
            return size

        def _do_layout(self, rect, test_only):
            x, y, line_height = rect.x(), rect.y(), 0
            for item in self._items:
                wid = item.widget()
                space_x = self.spacing() + wid.style().layoutSpacing(QSizePolicy.PushButton, QSizePolicy.PushButton, Qt.Horizontal)
                space_y = self.spacing() + wid.style().layoutSpacing(QSizePolicy.PushButton, QSizePolicy.PushButton, Qt.Vertical)
                next_x = x + item.sizeHint().width() + space_x
                if next_x - space_x > rect.right() and line_height > 0:
                    x = rect.x()
                    y += line_height + space_y
                    next_x = x + item.sizeHint().width() + space_x
                    line_height = 0
                if not test_only:
                    item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
                x = next_x
                line_height = max(line_height, item.sizeHint().height())
            return y + line_height - rect.y()
else:
    class FlowLayout:  # type: ignore
        """Import-safe placeholder used when Qt bindings are unavailable."""
        pass
