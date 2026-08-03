"""Сбалансированная стратегия (гибрид amplitude + collapse)"""
from typing import Dict
from datetime import datetime
from collections import deque
import statistics
from core.models import Trade, MarketData


class BalancedStrategy:
    """
    Комбинированная стратегия:
    - Закрывает по первому сигналу: амплитуда ИЛИ схлопывание
    - Средние параметры между amplitude и collapse
    """
    
    def __init__(self, 
                 amplitude_window: int = 30,
                 amplitude_threshold: float = 0.65,
                 min_amplitude_usd: float = 3.0,
                 collapse_threshold: float = 0.3,
                 min_profit_pct: float = 0.3,
                 max_hold_time_sec: float = 600):  # 10 минут
        
        # Amplitude параметры
        self.amplitude_window = amplitude_window
        self.amplitude_threshold = amplitude_threshold
        self.min_amplitude_usd = min_amplitude_usd
        self.amplitude_history: Dict[str, deque] = {}
        
        # Collapse параметры
        self.collapse_threshold = collapse_threshold
        self.min_profit_pct = min_profit_pct
        
        # Общее
        self.max_hold_time_sec = max_hold_time_sec
    
    def calculate_amplitude(self, trade: Trade, market_data: Dict[str, Dict[str, MarketData]]) -> float:
        """Расчёт текущей амплитуды (PnL в USD)"""
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
        
        return result['net_usd']

    
    def calculate_current_spread(self, trade: Trade, market_data: Dict[str, Dict[str, MarketData]]) -> float:
        """Расчёт текущего спреда"""
        long_data = market_data.get(trade.exchange_long, {}).get(trade.symbol)
        short_data = market_data.get(trade.exchange_short, {}).get(trade.symbol)
        
        if not long_data or not short_data:
            return None
        
        return (short_data.bid - long_data.ask) / long_data.ask * 100
    
    def calculate_pnl_pct(self, trade: Trade, market_data: Dict[str, Dict[str, MarketData]]) -> float:
        """Расчёт PnL в %"""
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

    
    def update_amplitude_history(self, symbol: str, amplitude: float):
        """Обновление истории амплитуд"""
        if symbol not in self.amplitude_history:
            self.amplitude_history[symbol] = deque(maxlen=self.amplitude_window)
        
        self.amplitude_history[symbol].append(amplitude)
    
    def get_avg_max_amplitude(self, symbol: str) -> float:
        """Средняя максимальная амплитуда"""
        if symbol not in self.amplitude_history or len(self.amplitude_history[symbol]) < 5:
            return self.min_amplitude_usd * 1.5
        
        history = list(self.amplitude_history[symbol])
        return statistics.quantiles(history, n=10)[7]  # 80-й перцентиль
    
    def should_close(self, trade: Trade, market_data: Dict[str, Dict[str, MarketData]]) -> tuple[bool, str]:
        """Проверка условий закрытия (amplitude ИЛИ collapse)"""
        amplitude = self.calculate_amplitude(trade, market_data)
        current_spread = self.calculate_current_spread(trade, market_data)
        pnl_pct = self.calculate_pnl_pct(trade, market_data)
        time_held = (datetime.now() - trade.open_time).total_seconds()
        
        self.update_amplitude_history(trade.symbol, amplitude)
        
        # === СИГНАЛ 1: Amplitude (достигнут целевой профит) ===
        avg_max = self.get_avg_max_amplitude(trade.symbol)
        amplitude_target = avg_max * self.amplitude_threshold
        
        if amplitude >= amplitude_target and amplitude >= self.min_amplitude_usd:
            return True, f"Amplitude target: {amplitude:.2f}$ >= {amplitude_target:.2f}$"
        
        # === СИГНАЛ 2: Collapse (спред схлопнулся) ===
        if current_spread is not None and current_spread <= self.collapse_threshold and pnl_pct >= self.min_profit_pct:
            return True, f"Spread collapsed: {current_spread:.3f}% (entry: {trade.entry_spread:.3f}%), PnL: {pnl_pct:.3f}%"
        
        # === СИГНАЛ 3: Целевая прибыль (50% от entry spread) ===
        target_profit = trade.entry_spread * 0.5
        if pnl_pct >= target_profit:
            return True, f"Target profit: {pnl_pct:.3f}% >= {target_profit:.3f}%"
        
        # === СИГНАЛ 4: Stop-loss ===
        stop_loss_threshold = -self.min_amplitude_usd * 1.5
        if amplitude < stop_loss_threshold:
            return True, f"Stop-loss: {amplitude:.2f}$ < {stop_loss_threshold:.2f}$"
        
        # === СИГНАЛ 5: Разворот спреда ===
        if current_spread is not None and current_spread * trade.entry_spread < 0:
            return True, f"Spread reversal: {current_spread:.3f}% (entry: {trade.entry_spread:.3f}%)"
        
        # === СИГНАЛ 6: Timeout ===
        if time_held > self.max_hold_time_sec:
            return True, f"Timeout: {time_held:.0f}s (PnL: {pnl_pct:.3f}%)"
        
        return False, ""
    
    def get_statistics(self, symbol: str) -> Dict:
        """Статистика"""
        if symbol not in self.amplitude_history or not self.amplitude_history[symbol]:
            return {
                "samples": 0,
                "avg_amplitude": 0,
                "max_amplitude": 0,
                "threshold": 0
            }
        
        history = list(self.amplitude_history[symbol])
        avg_max = self.get_avg_max_amplitude(symbol)
        
        return {
            "samples": len(history),
            "avg_amplitude": statistics.mean(history),
            "max_amplitude": max(history),
            "threshold": avg_max * self.amplitude_threshold
        }
