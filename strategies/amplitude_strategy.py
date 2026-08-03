"""Амплитудная стратегия закрытия позиций"""
from typing import Dict, List
from collections import deque
from datetime import datetime
import statistics
from core.models import Trade, MarketData


class AmplitudeStrategy:
    """Стратегия закрытия на основе амплитудных колебаний"""
    
    def __init__(self, 
                 amplitude_window: int = 50,
                 amplitude_threshold: float = 0.7,
                 min_amplitude_usd: float = 5.0,
                 stop_loss_multiplier: float = 2.0,
                 max_hold_time_sec: float = 300):
        
        self.amplitude_window = amplitude_window
        self.amplitude_threshold = amplitude_threshold
        self.min_amplitude_usd = min_amplitude_usd
        self.stop_loss_multiplier = stop_loss_multiplier
        self.max_hold_time_sec = max_hold_time_sec
        
        # История амплитуд для каждого символа
        self.amplitude_history: Dict[str, deque] = {}
    
    def calculate_amplitude(self, trade: Trade, market_data: Dict[str, Dict[str, MarketData]]) -> float:
        """Расчёт текущей амплитуды позиции (совокупный PnL)"""
        from core.analyzers.pnl_calculator import calculate_net_pnl
        
        # Получаем текущие цены
        long_data = market_data.get(trade.exchange_long, {}).get(trade.symbol)
        short_data = market_data.get(trade.exchange_short, {}).get(trade.symbol)
        
        if not long_data or not short_data:
            return 0.0
        
        # Используем унифицированный калькулятор PnL
        result = calculate_net_pnl(
            entry_price_long=trade.entry_price_long,
            entry_price_short=trade.entry_price_short,
            current_price_long=long_data.bid,
            current_price_short=short_data.ask,
            position_size_usd=trade.position_size_usd,
            leverage=getattr(trade, 'leverage', 10),
            fee_rate=0.0005
        )
        
        amplitude_usd = result['net_usd']
        
        return amplitude_usd
    
    def update_amplitude_history(self, symbol: str, amplitude: float):
        """Обновление истории амплитуд"""
        if symbol not in self.amplitude_history:
            self.amplitude_history[symbol] = deque(maxlen=self.amplitude_window)
        
        self.amplitude_history[symbol].append(amplitude)
    
    def get_avg_max_amplitude(self, symbol: str) -> float:
        """Получение средней максимальной амплитуды (90-й перцентиль)"""
        if symbol not in self.amplitude_history or len(self.amplitude_history[symbol]) < 10:
            return self.min_amplitude_usd * 2  # Начальное значение
        
        history = list(self.amplitude_history[symbol])
        return statistics.quantiles(history, n=10)[8]  # 90-й перцентиль
    
    def should_close(self, trade: Trade, market_data: Dict[str, Dict[str, MarketData]]) -> tuple[bool, str]:
        """Проверка условий закрытия позиции"""
        # Текущая амплитуда
        amplitude = self.calculate_amplitude(trade, market_data)
        
        # Обновляем историю
        self.update_amplitude_history(trade.symbol, amplitude)
        
        # Время удержания
        time_held = (datetime.now() - trade.open_time).total_seconds()
        
        # === УСЛОВИЕ 1: Достигнут целевой профит ===
        avg_max = self.get_avg_max_amplitude(trade.symbol)
        threshold = avg_max * self.amplitude_threshold
        
        if amplitude >= threshold and amplitude >= self.min_amplitude_usd:
            return True, f"Target profit: {amplitude:.2f}$ >= {threshold:.2f}$"
        
        # === УСЛОВИЕ 2: Stop-Loss ===
        stop_loss_threshold = -self.min_amplitude_usd * self.stop_loss_multiplier
        if amplitude < stop_loss_threshold:
            return True, f"Stop-loss: {amplitude:.2f}$ < {stop_loss_threshold:.2f}$"
        
        # === УСЛОВИЕ 3: Timeout ===
        if time_held > self.max_hold_time_sec:
            return True, f"Timeout: {time_held:.0f}s > {self.max_hold_time_sec}s (PnL: {amplitude:.2f}$)"
        
        # === УСЛОВИЕ 4: Разворот спреда ===
        current_spread = self._calculate_current_spread(trade, market_data)
        if current_spread is not None and current_spread * trade.entry_spread < 0:
            return True, f"Spread reversal (entry: {trade.entry_spread:.4f}%, now: {current_spread:.4f}%)"
        
        return False, ""
    
    def _calculate_current_spread(self, trade: Trade, market_data: Dict) -> float:
        """Расчёт текущего спреда"""
        long_data = market_data.get(trade.exchange_long, {}).get(trade.symbol)
        short_data = market_data.get(trade.exchange_short, {}).get(trade.symbol)
        
        if not long_data or not short_data:
            return None
        
        # Текущий спред (bid короткой биржи - ask длинной биржи)
        spread = (short_data.bid - long_data.ask) / long_data.ask * 100
        return spread
    
    def get_statistics(self, symbol: str) -> Dict:
        """Статистика по символу"""
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
