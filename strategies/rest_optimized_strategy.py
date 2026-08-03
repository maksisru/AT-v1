"""REST-оптимизированная стратегия закрытия"""
from typing import Dict
from datetime import datetime
from core.models import Trade, MarketData


class RestOptimizedStrategy:
    """Простая стратегия для REST торговли с фиксированными уровнями"""
    
    def __init__(self,
                 take_profit_pct: float = 0.4,
                 stop_loss_pct: float = 0.3,
                 max_hold_time_sec: float = 180,
                 trailing_stop_activation: float = 0.5):
        """
        Args:
            take_profit_pct: Фиксированный тейк-профит (%)
            stop_loss_pct: Фиксированный стоп-лосс (%)
            max_hold_time_sec: Максимальное время удержания (секунды)
            trailing_stop_activation: Активация трейлинг-стопа при прибыли (%)
        """
        self.take_profit_pct = take_profit_pct
        self.stop_loss_pct = stop_loss_pct
        self.max_hold_time_sec = max_hold_time_sec
        self.trailing_stop_activation = trailing_stop_activation
        
        # Храним максимальную прибыль для трейлинга
        self.max_profit_seen: Dict[str, float] = {}
    
    def calculate_pnl(self, trade: Trade, market_data: Dict[str, Dict[str, MarketData]]) -> float:
        """Расчёт текущего PnL в процентах (используя pnl_calculator)"""
        from core.analyzers.pnl_calculator import calculate_net_pnl
        
        long_data = market_data.get(trade.exchange_long, {}).get(trade.symbol)
        short_data = market_data.get(trade.exchange_short, {}).get(trade.symbol)
        
        if not long_data or not short_data:
            return 0.0
        
        # Используем унифицированный расчёт
        result = calculate_net_pnl(
            entry_price_long=trade.entry_price_long,
            entry_price_short=trade.entry_price_short,
            current_price_long=long_data.bid,
            current_price_short=short_data.ask,
            position_size_usd=trade.position_size_usd,
            leverage=5,
            fee_rate=0.0005,
        )
        
        return result['net_pct']
    
    def should_close(self, trade: Trade, market_data: Dict[str, Dict[str, MarketData]]) -> tuple[bool, str]:
        """Проверка условий закрытия"""
        
        # 1. Расчёт PnL
        pnl_pct = self.calculate_pnl(trade, market_data)
        
        # Обновляем максимальную прибыль
        if trade.pair_id not in self.max_profit_seen:
            self.max_profit_seen[trade.pair_id] = pnl_pct
        else:
            self.max_profit_seen[trade.pair_id] = max(self.max_profit_seen[trade.pair_id], pnl_pct)
        
        max_profit = self.max_profit_seen[trade.pair_id]
        
        # 2. Take Profit
        if pnl_pct >= self.take_profit_pct:
            return True, f"✅ Take Profit: {pnl_pct:.3f}% ≥ {self.take_profit_pct}%"
        
        # 3. Stop Loss
        if pnl_pct <= -self.stop_loss_pct:
            return True, f"❌ Stop Loss: {pnl_pct:.3f}% ≤ -{self.stop_loss_pct}%"
        
        # 4. Trailing Stop (активируется после достижения порога)
        if max_profit >= self.trailing_stop_activation:
            drawdown = max_profit - pnl_pct
            # Закрываем если откатились на 0.2% от максимума
            if drawdown >= 0.2:
                return True, f"📉 Trailing Stop: откат {drawdown:.3f}% от макс {max_profit:.3f}%"
        
        # 5. Time-based exit
        hold_time = (datetime.now() - trade.open_time).total_seconds()
        if hold_time >= self.max_hold_time_sec:
            return True, f"⏰ Max Hold Time: {hold_time:.0f}s, PnL: {pnl_pct:.3f}%"
        
        return False, f"💼 Держим: PnL={pnl_pct:.3f}%, Max={max_profit:.3f}%, Time={hold_time:.0f}s"
    
    def cleanup_trade(self, pair_id: str):
        """Очистка данных после закрытия позиции"""
        if pair_id in self.max_profit_seen:
            del self.max_profit_seen[pair_id]
