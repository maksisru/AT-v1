"""Workspace container: renders, removes, and repositions cards only."""
from __future__ import annotations

from .card_manager import CardManager, CardState
from .flow_layout import FlowLayout

try:
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QWidget
except ImportError:  # pragma: no cover
    QWidget = object  # type: ignore


if QWidget is not object:
    class Workspace(QWidget):
        """Thin Qt container backed by CardManager; it owns no card business state."""

        def __init__(self, manager: CardManager, parent=None):
            super().__init__(parent)
            self.manager = manager
            self.layout = FlowLayout(self, spacing=12)
            self.autosave_timer = QTimer(self)
            self.autosave_timer.setInterval(30_000)
            self.autosave_timer.timeout.connect(self.manager.save_workspace)
            self.autosave_timer.start()

        def load_current_workspace(self) -> None:
            """Render manager cards for the active workspace."""
            self.clear()
            for card in self.manager.list_cards():
                self.show_card(card)

        def show_card(self, card: CardState) -> None:
            """Add one card widget to the FlowLayout."""
            self.layout.addWidget(self.manager.create_widget(card))

        def remove_card(self, card_id: str) -> None:
            """Remove one card widget from the layout."""
            for index in range(self.layout.count()):
                item = self.layout.itemAt(index)
                widget = item.widget() if item else None
                if widget and getattr(widget, "state", None) and widget.state.card_id == card_id:
                    self.layout.takeAt(index)
                    widget.setParent(None)
                    return

        def clear(self) -> None:
            """Remove every currently rendered widget."""
            while self.layout.count():
                item = self.layout.takeAt(0)
                if item and item.widget():
                    item.widget().setParent(None)

        def update_order_from_widgets(self) -> None:
            """Report the current visual order after drag/drop completes."""
            ids = []
            for index in range(self.layout.count()):
                widget = self.layout.itemAt(index).widget()
                if getattr(widget, "state", None):
                    ids.append(widget.state.card_id)
            self.manager.reorder_cards(ids)
            self.manager.save_workspace()
else:
    class Workspace:  # type: ignore
        """Import-safe placeholder used when Qt bindings are unavailable."""
        pass
