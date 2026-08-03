"""Модели данных системы"""
from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class MarketData:
    """Рыночные данные"""
    exchange: str
    symbol: str
    bid: float
    ask: float
    funding_rate: float
    timestamp: datetime


@dataclass
class Position:
    """Открытая позиция"""
    exchange: str
    symbol: str
    side: str  # 'LONG' or 'SHORT'
    size: float
    entry_price: float
    timestamp: datetime


@dataclass
class ArbitragePair:
    """Арбитражная пара"""
    exchange_long: str
    exchange_short: str
    symbol: str
    spread: float
    funding_diff: float
    price_long: float
    price_short: float
    timestamp: datetime
    data_long: 'MarketData' = None
    data_short: 'MarketData' = None
    effective_spread: float = 0.0
    spread_trend: str = 'unknown'  # 'expanding', 'stable', 'collapsing', 'unknown'


@dataclass
class Trade:
    """Исполненная сделка"""
    pair_id: str
    exchange_long: str          # Биржа где LONG
    exchange_short: str         # Биржа где SHORT
    symbol: str
    entry_price_long: float     # Цена входа в LONG
    entry_price_short: float    # Цена входа в SHORT
    entry_spread: float         # Спред при открытии (%)
    position_size_usd: float    # Размер позиции в USD
    open_spread: float          # Дублирует entry_spread (совместимость)
    close_spread: Optional[float] = None
    pnl: Optional[float] = None
    status: str = 'open'  # 'open', 'closed', 'failed'
    open_time: datetime = None
    close_time: Optional[datetime] = None
    strategy_name: str = 'balanced'
    leverage: int = 5
    hs_spread_type: Optional[str] = None
    hs_max_hold_min: int = 60
    spread_trend_at_entry: str = 'unknown'  # Тренд спреда в момент входа
