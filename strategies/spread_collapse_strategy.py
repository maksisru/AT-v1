"""Классическая стратегия схлопывания спреда"""
from typing import Dict
from datetime import datetime
from core.models import Trade, MarketData


class SpreadCollapseStrategy:
    """Стратегия закрытия при схлопывании спреда"""
    
    def __init__(self, 
                 collapse_threshold: float = 0.1,  # Спред схлопнулся до 0.1%
                 min_profit_pct: float = 0.05,      # Минимальная прибыль 0.05%
                 max_hold_time_sec: float = 3600):  # Макс 1 час
        
        self.collapse_threshold = collapse_threshold
        self.min_profit_pct = min_profit_pct
        self.max_hold_time_sec = max_hold_time_sec
    
    def calculate_current_spread(self, trade: Trade, market_data: Dict[str, Dict[str, MarketData]]) -> float:
        """Расчёт текущего спреда с проверкой валидности данных"""
        import logging
        logger = logging.getLogger(__name__)
        
        long_data = market_data.get(trade.exchange_long, {}).get(trade.symbol)
        short_data = market_data.get(trade.exchange_short, {}).get(trade.symbol)
        
        if not long_data or not short_data:
            return None
        
        # БАГ #3 FIX: Проверка нулевых цен (потеря данных)
        if long_data.bid <= 0 or long_data.ask <= 0:
            logger.warning(f"Zero prices on {trade.exchange_long} for {trade.symbol}")
            return None
        if short_data.bid <= 0 or short_data.ask <= 0:
            logger.warning(f"Zero prices on {trade.exchange_short} for {trade.symbol}")
            return None
        
        # БАГ #3 FIX: Проверка свежести данных (stale data)
        now_ms = datetime.now().timestamp() * 1000
        age_long = now_ms - long_data.timestamp.timestamp() * 1000
        age_short = now_ms - short_data.timestamp.timestamp() * 1000
        
        if age_long > 3000 or age_short > 3000:
            # Данные старше 3 секунд — не принимаем решение о закрытии
            logger.warning(f"Stale data for {trade.symbol}: ages {age_long:.0f}/{age_short:.0f}ms")
            return None
        
        # Текущий спред (SHORT bid - LONG ask)
        current_spread = (short_data.bid - long_data.ask) / long_data.ask * 100
        return current_spread
    
    def calculate_pnl_pct(self, trade: Trade, market_data: Dict[str, Dict[str, MarketData]]) -> float:
        """Расчёт PnL в процентах"""
        from core.analyzers.pnl_calculator import calculate_net_pnl
        
        long_data = market_data.get(trade.exchange_long, {}).get(trade.symbol)
        short_data = market_data.get(trade.exchange_short, {}).get(trade.symbol)
        
        if not long_data or not short_data:
            return 0.0
        
        # Используем унифицированный калькулятор
        result = calculate_net_pnl(
            entry_price_long=trade.entry_price_long,
            entry_price_short=trade.entry_price_short,
            current_price_long=long_data.bid,
            current_price_short=short_data.ask,
            position_size_usd=trade.position_size_usd,
            leverage=getattr(trade, 'leverage', 10),
            fee_rate=0.0005
        )
        
        return result['net_pct']

    
    def should_close(self, trade: Trade, market_data: Dict[str, Dict[str, MarketData]]) -> tuple[bool, str]:
        """Проверка условий закрытия (asymmetric risk/reward)"""
        current_spread = self.calculate_current_spread(trade, market_data)
        
        if current_spread is None:
            return False, ""
        
        pnl_pct = self.calculate_pnl_pct(trade, market_data)
        time_held = (datetime.now() - trade.open_time).total_seconds()
        
        # === ВЫХОД В ПРИБЫЛЬ (более реалистичные цели) ===
        
        # 1. Спред схлопнулся до порога
        if current_spread <= self.collapse_threshold and pnl_pct >= self.min_profit_pct:
            return True, f"Collapse: spread {current_spread:.3f}%"
        
        # 2. Поэтапное снятие прибыли (30% от entry spread, max 1%)
        partial_target = min(trade.entry_spread * 0.30, 1.0)
        if pnl_pct >= partial_target:
            return True, f"Partial target: {pnl_pct:.3f}% >= {partial_target:.3f}%"
        
        # === СТОП-ЛОССЫ (УЖЕСТОЧЕНЫ) ===
        
        # 3. Hard stop: спред расширился более чем на 1.0% от входа
        if current_spread > trade.entry_spread + 1.0:
            return True, f"Hard stop: spread expanded to {current_spread:.3f}%"
        
        # 4. Time stop: если за 5 минут нет движения в нашу сторону — выходим
        if time_held > 300 and pnl_pct < 0.05:
            return True, f"Time stop: {time_held:.0f}s without progress (PnL: {pnl_pct:.3f}%)"
        
        # 5. Разворот спреда
        if current_spread < 0 and trade.entry_spread > 0:
            return True, f"Reversal: {current_spread:.3f}%"
        
        # 6. Максимальное время (10 минут вместо 1 часа)
        if time_held > 600:
            return True, f"Max hold: {time_held:.0f}s (PnL: {pnl_pct:.3f}%)"
        
        return False, ""
    
    def get_statistics(self, symbol: str) -> Dict:
        """Статистика (для совместимости с AmplitudeStrategy)"""
        return {
            "samples": 0,
            "avg_amplitude": 0,
            "max_amplitude": 0,
            "threshold": self.collapse_threshold
        }
