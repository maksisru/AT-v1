"""Card lifecycle, persistence, ordering, and history management.

The :class:`CardManager` is the single business-logic entry point for GUI
cards. Workspace widgets should only ask it what to display and report UI
ordering changes back to it; they must not keep their own card registry.
"""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from typing import Any, Callable, Deque, Dict, Iterable, List, MutableMapping, Optional
from uuid import uuid4


CARD_SIZES: Dict[str, tuple[int, int]] = {
    "SMALL": (280, 120),
    "MEDIUM": (360, 190),
    "LARGE": (480, 280),
}
DEFAULT_WORKSPACES = ("Scalping", "Funding", "Arbitrage", "Testing")


@dataclass
class CardData:
    """Mutable market/UI data rendered by one card.

    Only changed data should be pushed to widgets. The manager compares incoming
    values with the last stored value and returns ``False`` for no-op updates.
    """

    symbol: str = ""
    exchange_long: str = ""
    exchange_short: str = ""
    gross_spread: float = 0.0
    effective_spread: float = 0.0
    net_edge: float = 0.0
    pnl: float = 0.0
    settings: Dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class CardState:
    """Serializable state for one arbitrage card."""

    card_id: str
    workspace: str
    data: CardData = field(default_factory=CardData)
    size: str = "MEDIUM"
    collapsed: bool = False
    pinned: bool = False
    position: int = 0
    graph_lines: Dict[str, bool] = field(default_factory=lambda: {
        "gross_spread": True,
        "effective_spread": True,
        "net_edge": True,
        "pnl": True,
    })
    history: List[Dict[str, Any]] = field(default_factory=list)


class CardManager:
    """Single point of control for all card operations and workspace state."""

    def __init__(self, storage_path: str | Path = "workspace.json", card_factory: Optional[Callable[[CardState], Any]] = None):
        self.storage_path = Path(storage_path)
        self.card_factory = card_factory
        self.current_workspace = DEFAULT_WORKSPACES[0]
        self.workspaces: Dict[str, Dict[str, CardState]] = {name: {} for name in DEFAULT_WORKSPACES}
        self._widgets: Dict[str, Any] = {}
        self._history: Dict[str, Deque[Dict[str, Any]]] = {}

    def create_card(self, workspace: Optional[str] = None, data: Optional[CardData | MutableMapping[str, Any]] = None, **kwargs: Any) -> CardState:
        """Create a card in ``workspace`` and return its state."""
        workspace = self._ensure_workspace(workspace or self.current_workspace)
        card_data = self._coerce_data(data or kwargs.pop("data", None) or {})
        card = CardState(card_id=str(uuid4()), workspace=workspace, data=card_data, position=len(self.workspaces[workspace]), **kwargs)
        self.workspaces[workspace][card.card_id] = card
        self._history[card.card_id] = deque(card.history, maxlen=300)
        return card

    def delete_card(self, card_id: str) -> None:
        """Delete a card from its workspace and compact ordering."""
        card = self.get_card(card_id)
        del self.workspaces[card.workspace][card_id]
        self._widgets.pop(card_id, None)
        self._history.pop(card_id, None)
        self.reorder_cards([c.card_id for c in self.list_cards(card.workspace)], card.workspace)

    def find_cards(self, **criteria: Any) -> List[CardState]:
        """Find cards by state or nested data attributes."""
        result = []
        for card in self.iter_cards():
            if all(getattr(card, key, getattr(card.data, key, None)) == value for key, value in criteria.items()):
                result.append(card)
        return result

    def get_card(self, card_id: str) -> CardState:
        """Return card state or raise ``KeyError``."""
        for cards in self.workspaces.values():
            if card_id in cards:
                return cards[card_id]
        raise KeyError(f"Unknown card: {card_id}")

    def update_card(self, card_id: str, data: CardData | MutableMapping[str, Any]) -> bool:
        """Update card data only when changed; returns ``True`` on change."""
        card = self.get_card(card_id)
        new_data = self._coerce_data(data)
        if self._data_payload(card.data) == self._data_payload(new_data):
            return False
        card.data = new_data
        self._append_history(card)
        widget = self._widgets.get(card_id)
        if widget and hasattr(widget, "update_data"):
            widget.update_data(new_data)
        return True

    def update_card_state(self, card_id: str, **changes: Any) -> CardState:
        """Update visual state such as size, collapse, pin, and graph toggles."""
        card = self.get_card(card_id)
        if "size" in changes:
            changes["size"] = self._normalize_size(changes["size"])
        for key, value in changes.items():
            if not hasattr(card, key):
                raise AttributeError(key)
            setattr(card, key, value)
        if "pinned" in changes:
            self.reorder_cards([c.card_id for c in self.list_cards(card.workspace)], card.workspace)
        return card

    def bulk_update(self, updates: Iterable[tuple[str, CardData | MutableMapping[str, Any]]]) -> List[str]:
        """Apply many data updates and return ids that changed."""
        changed = []
        for card_id, data in updates:
            if self.update_card(card_id, data):
                changed.append(card_id)
        return changed

    def reorder_cards(self, ordered_ids: Iterable[str], workspace: Optional[str] = None) -> List[str]:
        """Persist a new order. Pinned cards are always placed first."""
        workspace = self._ensure_workspace(workspace or self.current_workspace)
        cards = self.workspaces[workspace]
        requested = [cid for cid in ordered_ids if cid in cards]
        requested.extend(cid for cid in cards if cid not in requested)
        original_index = {cid: index for index, cid in enumerate(requested)}
        requested.sort(key=lambda cid: (not cards[cid].pinned, original_index[cid]))
        for index, cid in enumerate(requested):
            cards[cid].position = index
        return requested

    def switch_workspace(self, name: str) -> List[CardState]:
        """Switch active workspace, creating it when needed."""
        self.current_workspace = self._ensure_workspace(name)
        return self.list_cards(name)

    def list_cards(self, workspace: Optional[str] = None) -> List[CardState]:
        """Return ordered cards for a workspace."""
        workspace = self._ensure_workspace(workspace or self.current_workspace)
        return sorted(self.workspaces[workspace].values(), key=lambda card: card.position)

    def iter_cards(self) -> Iterable[CardState]:
        """Iterate through every card in every workspace."""
        for workspace in self.workspaces:
            yield from self.list_cards(workspace)

    def register_widget(self, card_id: str, widget: Any) -> None:
        """Bind a rendered widget to an existing card id."""
        self.get_card(card_id)
        self._widgets[card_id] = widget

    def create_widget(self, card: CardState) -> Any:
        """Create a widget using the optional factory."""
        if not self.card_factory:
            raise RuntimeError("Card factory is not configured")
        widget = self.card_factory(card)
        self.register_widget(card.card_id, widget)
        return widget

    def save_workspace(self, path: str | Path | None = None) -> None:
        """Save all workspaces to JSON."""
        target = Path(path) if path else self.storage_path
        payload = {"current_workspace": self.current_workspace, "workspaces": {}}
        for name, cards in self.workspaces.items():
            payload["workspaces"][name] = [self._serialize_card(card) for card in self.list_cards(name)]
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_workspace(self, path: str | Path | None = None) -> List[CardState]:
        """Load workspaces from JSON and return cards for the active workspace."""
        target = Path(path) if path else self.storage_path
        if not target.exists():
            return self.list_cards()
        payload = json.loads(target.read_text(encoding="utf-8"))
        self.current_workspace = payload.get("current_workspace", self.current_workspace)
        self.workspaces = {name: {} for name in DEFAULT_WORKSPACES}
        self._history.clear()
        for name, entries in payload.get("workspaces", {}).items():
            self._ensure_workspace(name)
            for raw in entries:
                card = self._deserialize_card(raw, name)
                self.workspaces[name][card.card_id] = card
                self._history[card.card_id] = deque(card.history[-300:], maxlen=300)
        return self.list_cards(self.current_workspace)

    def _append_history(self, card: CardState) -> None:
        sample = asdict(card.data)
        sample["timestamp"] = datetime.now(UTC).isoformat()
        history = self._history.setdefault(card.card_id, deque(maxlen=300))
        cutoff = datetime.now(UTC) - timedelta(seconds=300)
        history.append(sample)
        while history and datetime.fromisoformat(history[0]["timestamp"]) < cutoff:
            history.popleft()
        card.history = list(history)

    def _ensure_workspace(self, name: str) -> str:
        self.workspaces.setdefault(name, {})
        return name

    @staticmethod
    def _normalize_size(size: str) -> str:
        size = size.upper()
        if size not in CARD_SIZES:
            raise ValueError(f"Unsupported card size: {size}")
        return size

    @staticmethod
    def _coerce_data(data: CardData | MutableMapping[str, Any]) -> CardData:
        if isinstance(data, CardData):
            return data
        return CardData(**dict(data))

    @staticmethod
    def _data_payload(data: CardData) -> Dict[str, Any]:
        payload = asdict(data)
        payload.pop("updated_at", None)
        return payload

    @staticmethod
    def _serialize_card(card: CardState) -> Dict[str, Any]:
        return asdict(card)

    @staticmethod
    def _deserialize_card(raw: Dict[str, Any], workspace: str) -> CardState:
        raw = dict(raw)
        raw["workspace"] = raw.get("workspace", workspace)
        raw["data"] = CardData(**raw.get("data", {}))
        raw["history"] = raw.get("history", [])[-300:]
        return CardState(**raw)
