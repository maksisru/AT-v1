"""Read-only data structures rendered by arbitrage cards."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Tuple


class CardMode(str, Enum):
    """Lifecycle/strategy modes shown by a card header."""

    ACTIVE = "ACTIVE"
    WATCH = "WATCH"
    PAUSED = "PAUSED"
    ERROR = "ERROR"
    CLOSED = "CLOSED"


@dataclass(frozen=True)
class ExchangeMarketSnapshot:
    """Market values for a single exchange; values are precomputed upstream."""

    funding: str = "—"
    next_funding: str = "—"
    ask: str = "—"
    bid: str = "—"
    mark: str = "—"
    index: str = "—"
    open_interest: str = "—"
    volume: str = "—"
    bid_size: str = "—"
    ask_size: str = "—"
    latency: str = "—"


@dataclass(frozen=True)
class CardData:
    """Complete display payload for one arbitrage opportunity.

    The GUI must only render this object. Spread, fee, funding and score
    calculations belong to TerminalService/business logic.
    """

    card_id: str
    symbol: str
    long_exchange: str
    short_exchange: str
    mode: CardMode = CardMode.WATCH
    status: str = "READY"
    score: str = "—"
    latency: str = "—"
    connection: str = "CONNECTED"
    exchange_status: str = "OK"
    markets: Dict[str, ExchangeMarketSnapshot] = field(default_factory=dict)
    metrics: Dict[str, str] = field(default_factory=dict)
    graph_points: Tuple[Tuple[float, float, float], ...] = field(default_factory=tuple)
    last_update: datetime = field(default_factory=datetime.utcnow)
    message_count: int = 0
    lifetime: str = "00:00:00"
    last_trade: str = "—"
