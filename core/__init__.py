"""Core package initialization"""
# Ленивая инициализация для избежания циклических импортов
# Импортируйте компоненты напрямую:
# from core.models import MarketData, Position, ArbitragePair, Trade
# from core.engines.market_data_engine import MarketDataEngine
# и т.д.

__all__ = [
    'MarketData',
    'Position',
    'ArbitragePair',
    'Trade',
    'MarketDataEngine',
    'ArbitrageEngine',
    'TradingEngine',
    'RiskManager',
    'PositionManager',
]
