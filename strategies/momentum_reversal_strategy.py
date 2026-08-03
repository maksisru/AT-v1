"""Momentum Reversal Strategy — стратегия разворота импульса"""
from typing import Dict
from collections import deque
from datetime import datetime
import statistics
from core.models import Trade, MarketData


class MomentumReversalStrategy:
    """
    Стратегия закрытия на основе разворота импульса спреда.
    
    Концепция:
    - Спред имеет импульс (momentum) — скорость изменения
    - Когда импульс меняет направление (reversal) — оптимальный момент закрытия
    - Работает на средних спредах (1-3%) с умеренной волатильностью
    
    Пример:
    T0: Спред 2.0%
    T1: Спред 1.5% (снижается -0.5%)
    T2: Спред 1.2% (снижается -0.3%, замедление!)
    T3: Спред 1.3% (растёт +0.1%, РАЗВОРОТ!) → ЗАКРЫВАЕМ
    """
    
    def __init__(self, 
                 window_size: int = 10,
                 reversal_threshold: float = 0.05,
                 min_profit_pct: float = 0.3,
                 max_hold_time_sec: float = 600):
        
        self.window_size = window_size
        self.reversal_threshold = reversal_threshold
        self.min_profit_pct = min_profit_pct
        self.max_hold_time_sec = max_hold_time_sec
        
        # История спредов для каждой позиции
        self.spread_history: Dict[str, deque] = {}
    
    def calculate_current_spread(self, trade: Trade, market_data: Dict[str, Dict[str, MarketData]]) -> float:
        """Расчёт текущего спреда"""
        long_data = market_data.get(trade.exchange_long, {}).get(trade.symbol)
        short_data = market_data.get(trade.exchange_short, {}).get(trade.symbol)
        
        if not long_data or not short_data:
            return None
        
        current_spread = (short_data.bid - long_data.ask) / long_data.ask * 100
        return current_spread
    
    def calculate_pnl_pct(self, trade: Trade, market_data: Dict[str, Dict[str, MarketData]]) -> float:
        """Расчёт PnL в процентах"""
        from core.analyzers.pnl_calculator import calculate_net_pnl
        
        long_data = market_data.get(trade.exchange_long, {}).get(trade.symbol)
        short_data = market_data.get(trade.exchange_short, {}).get(trade.symbol)
        
        if not long_data or not short_data:
            return 0.0
        
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

    
    def detect_momentum_reversal(self, pair_id: str, current_spread: float) -> bool:
        """Обнаружение разворота импульса"""
        if pair_id not in self.spread_history:
            self.spread_history[pair_id] = deque(maxlen=self.window_size)
        
        history = self.spread_history[pair_id]
        history.append(current_spread)
        
        # Нужно минимум 3 точки для определения разворота
        if len(history) < 3:
            return False
        
        # Последние 3 изменения спреда
        changes = [history[i] - history[i-1] for i in range(1, len(history))]
        
        if len(changes) < 2:
            return False
        
        # Импульс = среднее изменение
        recent_momentum = changes[-1]
        previous_momentum = changes[-2]
        
        # Разворот = смена знака импульса
        # Был отрицательный (спред снижался) → стал положительный (спред растёт)
        if previous_momentum < 0 and recent_momentum > self.reversal_threshold:
            return True
        
        # Или: был положительный → стал отрицательный (для обратной ситуации)
        if previous_momentum > 0 and recent_momentum < -self.reversal_threshold:
            return True
        
        return False
    
    def should_close(self, trade: Trade, market_data: Dict[str, Dict[str, MarketData]]) -> tuple[bool, str]:
        """Проверка условий закрытия"""
        current_spread = self.calculate_current_spread(trade, market_data)
        
        if current_spread is None:
            return False, ""
        
        pnl_pct = self.calculate_pnl_pct(trade, market_data)
        time_held = (datetime.now() - trade.open_time).total_seconds()
        
        # === УСЛОВИЕ 1: Разворот импульса + прибыль ===
        reversal = self.detect_momentum_reversal(trade.pair_id, current_spread)
        if reversal and pnl_pct >= self.min_profit_pct:
            return True, f"Momentum reversal detected: PnL {pnl_pct:.3f}%"
        
        # === УСЛОВИЕ 2: Спред развернулся против нас ===
        spread_change = current_spread - trade.entry_spread
        if spread_change > 0.5 and pnl_pct < 0:
            return True, f"Adverse spread movement: {spread_change:+.3f}%"
        
        # === УСЛОВИЕ 3: Целевая прибыль достигнута ===
        target_profit = trade.entry_spread * 0.5  # 50% от входного спреда
        if pnl_pct >= target_profit:
            return True, f"Target profit: {pnl_pct:.3f}% >= {target_profit:.3f}%"
        
        # === УСЛОВИЕ 4: Timeout ===
        if time_held > self.max_hold_time_sec:
            return True, f"Timeout: {time_held:.0f}s (PnL: {pnl_pct:.3f}%)"
        
        return False, ""
    
    def get_statistics(self, symbol: str) -> Dict:
        """Статистика (для совместимости)"""
        return {
            "samples": 0,
            "avg_amplitude": 0,
            "max_amplitude": 0,
            "threshold": self.reversal_threshold
        }
