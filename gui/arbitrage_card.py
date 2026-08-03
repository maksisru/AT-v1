"""Arbitrage card widget with size, collapse, pin, and graph-line controls."""
from __future__ import annotations

from .card_manager import CARD_SIZES, CardData, CardState
from .theme_manager import ThemeManager

try:
    from PyQt5.QtCore import pyqtSignal, Qt
    from PyQt5.QtWidgets import QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout
except ImportError:  # pragma: no cover
    QFrame = object  # type: ignore


if QFrame is not object:
    class ArbitrageCard(QFrame):
        """Qt widget that renders one CardState and delegates mutations outward."""

        size_changed = pyqtSignal(str, str)
        collapsed_changed = pyqtSignal(str, bool)
        pinned_changed = pyqtSignal(str, bool)
        graph_line_changed = pyqtSignal(str, str, bool)

        def __init__(self, state: CardState, theme_manager: ThemeManager | None = None, parent=None):
            super().__init__(parent)
            self.state = state
            self.theme_manager = theme_manager or ThemeManager()
            self.setObjectName(f"card-{state.card_id}")
            self.header = QHBoxLayout()
            self.body = QVBoxLayout()
            root = QVBoxLayout(self)
            root.addLayout(self.header)
            root.addLayout(self.body)
            self.title = QLabel()
            self.pin_button = QPushButton("📌")
            self.collapse_button = QPushButton("▾")
            self.size_select = QComboBox()
            self.size_select.addItems(list(CARD_SIZES))
            self.header.addWidget(self.title)
            self.header.addWidget(self.pin_button)
            self.header.addWidget(self.collapse_button)
            self.header.addWidget(self.size_select)
            self.metrics = QLabel()
            self.body.addWidget(self.metrics)
            for line in state.graph_lines:
                checkbox = QCheckBox(line.replace("_", " ").title())
                checkbox.setChecked(state.graph_lines[line])
                checkbox.toggled.connect(lambda checked, name=line: self.graph_line_changed.emit(self.state.card_id, name, checked))
                self.body.addWidget(checkbox)
            self.size_select.currentTextChanged.connect(lambda size: self.size_changed.emit(self.state.card_id, size))
            self.collapse_button.clicked.connect(self._toggle_collapsed)
            self.pin_button.clicked.connect(self._toggle_pinned)
            self.update_data(state.data)
            self.apply_state(state)
            self.apply_theme()

        def update_data(self, data: CardData) -> None:
            """Refresh labels without rebuilding the whole card."""
            self.state.data = data
            self.title.setText(f"{data.symbol or 'New card'} | {data.exchange_long} ↔ {data.exchange_short}")
            self.metrics.setText(
                f"Gross: {data.gross_spread:.3f}%  Effective: {data.effective_spread:.3f}%  "
                f"Net Edge: {data.net_edge:.3f}%  PnL: {data.pnl:.2f}"
            )

        def apply_state(self, state: CardState) -> None:
            """Apply visual state without business logic."""
            self.state = state
            self.size_select.setCurrentText(state.size)
            self.body.parentWidget().setVisible(not state.collapsed)
            self.collapse_button.setText("▸" if state.collapsed else "▾")
            self.setFixedSize(*CARD_SIZES[state.size])

        def apply_theme(self) -> None:
            """Apply active ThemeManager palette."""
            theme = self.theme_manager.active
            self.setStyleSheet(f"QFrame {{ background: {theme.surface}; color: {theme.text}; border: 1px solid {theme.border}; }}")

        def _toggle_collapsed(self) -> None:
            self.collapsed_changed.emit(self.state.card_id, not self.state.collapsed)

        def _toggle_pinned(self) -> None:
            self.pinned_changed.emit(self.state.card_id, not self.state.pinned)
else:
    class ArbitrageCard:  # type: ignore
        """Import-safe placeholder used when Qt bindings are unavailable."""
        pass
