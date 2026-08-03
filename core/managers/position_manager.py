"""Position Manager — управление открытыми позициями"""
import asyncio
from typing import Dict, List
from datetime import datetime
from core.models import Trade, MarketData
from strategies.strategy_selector import StrategySelector


class PositionManager:
    """Автоматическое управление открытыми позициями"""
    
    def __init__(self, trading_engine, strategy_selector, telegram_logger, risk_manager=None):
        self.trading_engine = trading_engine
        self.strategy_selector = strategy_selector
        self.telegram = telegram_logger
        self.risk_manager = risk_manager  # Опционально для обновления баланса
        self.positions: Dict[str, Trade] = {}
        self.total_pnl = 0.0
        self.closed_positions = []
    
    def register_position(self, trade: Trade):
        """Регистрация новой позиции"""
        self.positions[trade.pair_id] = trade
        print(f"   ✅ Позиция зарегистрирована: {trade.symbol} ({trade.pair_id[:8]})")
    
    async def monitor_positions(self, market_data: Dict[str, Dict[str, MarketData]]):
        """Мониторинг и автоматическое закрытие позиций"""
        if not self.positions:
            return
        
        for pair_id, trade in list(self.positions.items()):
            try:
                should_close, reason = self.strategy_selector.should_close(trade, market_data)
                
                if should_close:
                    await self.close_position(pair_id, market_data, reason)
            except Exception as e:
                print(f"⚠️  Ошибка мониторинга позиции {trade.symbol}: {e}")
                await self.telegram.log_error("Position Monitoring", f"{trade.symbol}: {str(e)}")
    
    async def close_position(self, pair_id: str, market_data: Dict, reason: str):
        """Закрытие позиции — атомарная операция"""
        if pair_id not in self.positions:
            return
        
        trade = self.positions[pair_id]
        
        # ИСПРАВЛЕНИЕ БАГ #1: Удаляем ПЕРВЫМ действием
        # Это предотвращает повторное закрытие при следующем мониторинге
        del self.positions[pair_id]
        
        print(f"\n🔄 Закрытие позиции: {trade.symbol} ({pair_id[:8]})")
        print(f"   Причина: {reason}")
        
        try:
            # Закрываем на биржах
            success = await self.trading_engine.close_position(pair_id)
            
            if not success:
                print(f"   ❌ trading_engine.close_position failed for {pair_id[:8]}")
                await self.telegram.log_error(
                    "Close Failed",
                    f"{trade.symbol}: close order failed! Check exchange manually. pair_id={pair_id[:8]}"
                )
            
            # Расчёт PnL (в отдельном try — не должен влиять на закрытие)
            try:
                await self._calculate_and_log_pnl(trade, market_data, reason, success)
            except Exception as e:
                print(f"   ⚠️ PnL calculation failed: {e}")
        
        except Exception as e:
            print(f"   ❌ CRITICAL: close_position exception: {e}")
            await self.telegram.log_error(
                "Close Exception",
                f"{trade.symbol}: exception during close! pair_id={pair_id[:8]}, error={e}"
            )
    
    async def _calculate_and_log_pnl(self, trade, market_data, reason, success):
        """Вынесенный расчёт PnL — ошибка здесь не влияет на закрытие позиции"""
        from core.analyzers.pnl_calculator import calculate_net_pnl
        
        long_data = market_data.get(trade.exchange_long, {}).get(trade.symbol)
        short_data = market_data.get(trade.exchange_short, {}).get(trade.symbol)
        
        if long_data and short_data:
            # Используем унифицированный расчёт PnL
            pnl_result = calculate_net_pnl(
                entry_price_long=trade.entry_price_long,
                entry_price_short=trade.entry_price_short,
                current_price_long=long_data.bid,
                current_price_short=short_data.ask,
                position_size_usd=trade.position_size_usd,
                leverage=5,
                fee_rate=0.0005,
            )
            
            pnl_pct = pnl_result['gross_pct']
            pnl_usd = pnl_result['net_usd']
            
            # Текущий спред
            current_spread = (short_data.bid - long_data.ask) / long_data.ask * 100
        else:
            pnl_usd = 0.0
            current_spread = 0.0
            print(f"   ⚠️ No market data for PnL calc: {trade.symbol}")
        
        # Обновляем трейд
        trade.close_spread = current_spread
        trade.pnl = pnl_usd
        trade.status = 'closed'
        trade.close_time = datetime.now()
        
        hold_time = (trade.close_time - trade.open_time).total_seconds()
        
        self.total_pnl += pnl_usd
        self.closed_positions.append(trade)
        
        # Обновляем баланс в risk manager
        if self.risk_manager:
            self.risk_manager.update_balance(pnl_usd)
            # Удаляем позицию из risk manager
            self.risk_manager.unregister_position(trade.pair_id)
            
            # Регистрируем cooldown при убытке
            if pnl_usd < 0:
                self.risk_manager.register_loss(
                    trade.symbol, 
                    trade.exchange_long, 
                    trade.exchange_short
                )
        
        # Вывод
        emoji = "✅" if pnl_usd > 0 else "❌"
        print(f"   {emoji} PnL: {pnl_usd:+.2f} USD")
        print(f"   ⏱️  Время: {hold_time:.1f}s")
        print(f"   💹 Спред: {trade.entry_spread:.3f}% → {current_spread:.3f}%")
        
        # Telegram
        await self.telegram.log_position_closed(
            symbol=trade.symbol,
            spread_open=trade.entry_spread,
            spread_close=current_spread,
            pnl=pnl_usd,
            hold_time=hold_time,
            reason=reason
        )
        
        # Отправляем обновлённую статистику после закрытия
        stats = self.get_statistics()
        await self.telegram.log_daily_stats(
            total_trades=stats['total_trades'],
            profitable=stats['profitable'],
            total_pnl=stats['total_pnl'],
            win_rate=stats['win_rate'],
            avg_hold_time=stats['avg_hold_time']
        )
    
    def get_statistics(self) -> Dict:
        """Статистика по позициям"""
        if not self.closed_positions:
            return {
                "total_trades": 0,
                "profitable": 0,
                "total_pnl": 0,
                "win_rate": 0,
                "avg_hold_time": 0
            }
        
        profitable = sum(1 for t in self.closed_positions if t.pnl > 0)
        avg_hold = sum(
            (t.close_time - t.open_time).total_seconds() 
            for t in self.closed_positions
        ) / len(self.closed_positions)
        
        return {
            "total_trades": len(self.closed_positions),
            "profitable": profitable,
            "total_pnl": self.total_pnl,
            "win_rate": profitable / len(self.closed_positions) * 100,
            "avg_hold_time": avg_hold
        }
