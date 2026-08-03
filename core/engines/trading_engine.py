"""Trading Engine — исполнение ордеров и управление позициями"""
import asyncio
from typing import Dict
from core.models import ArbitragePair, Trade
from exchanges.base import BaseExchange
from datetime import datetime
import uuid


class TradingEngine:
    """Управление торговыми операциями"""
    
    def __init__(self, exchanges: Dict[str, BaseExchange], demo_mode: bool = True):
        self.exchanges = exchanges
        self.demo_mode = demo_mode
        self.open_positions: Dict[str, Trade] = {}
    
    async def execute_arbitrage(self, opportunity: ArbitragePair, position_size: float, strategy_name: str = 'balanced') -> tuple[bool, str]:
        """Открытие арбитражной позиции"""
        pair_id = str(uuid.uuid4())
        
        if self.demo_mode:
            # Демо режим: симулируем успешное открытие
            trade = Trade(
                pair_id=pair_id,
                exchange_long=opportunity.exchange_long,
                exchange_short=opportunity.exchange_short,
                symbol=opportunity.symbol,
                entry_price_long=opportunity.price_long,
                entry_price_short=opportunity.price_short,
                entry_spread=opportunity.spread,
                position_size_usd=position_size,
                open_spread=opportunity.spread,
                strategy_name=strategy_name,
                open_time=datetime.now(),
                spread_trend_at_entry=getattr(opportunity, 'spread_trend', 'unknown')
            )
            self.open_positions[pair_id] = trade
            return True, pair_id
        
        # Продакшн режим: реальные ордера
        try:
            # Параллельное открытие позиций
            results = await asyncio.gather(
                self.exchanges[opportunity.exchange_short].place_order(
                    opportunity.symbol, 'SHORT', position_size
                ),
                self.exchanges[opportunity.exchange_long].place_order(
                    opportunity.symbol, 'LONG', position_size
                ),
                return_exceptions=True
            )
            
            # Проверка успешности
            if any(isinstance(r, Exception) for r in results):
                await self._rollback_orders(results, opportunity, position_size)
                return False, "Order execution failed"
            
            # Сохранение позиции
            trade = Trade(
                pair_id=pair_id,
                exchange_long=opportunity.exchange_long,
                exchange_short=opportunity.exchange_short,
                symbol=opportunity.symbol,
                entry_price_long=opportunity.price_long,
                entry_price_short=opportunity.price_short,
                entry_spread=opportunity.spread,
                position_size_usd=position_size,
                open_spread=opportunity.spread,
                strategy_name=strategy_name,
                open_time=datetime.now(),
                spread_trend_at_entry=getattr(opportunity, 'spread_trend', 'unknown')
            )
            self.open_positions[pair_id] = trade
            
            return True, pair_id
            
        except Exception as e:
            print(f"   ❌ Ошибка открытия: {e}")
            return False, str(e)
    
    async def close_position(self, pair_id: str) -> bool:
        """Закрытие арбитражной позиции"""
        if pair_id not in self.open_positions:
            return False
        
        trade = self.open_positions[pair_id]
        
        if self.demo_mode:
            # Демо режим: симулируем закрытие
            trade.status = 'closed'
            trade.close_time = datetime.now()
            # БАГ #7 FIX: Очищаем запись из open_positions
            if pair_id in self.open_positions:
                del self.open_positions[pair_id]
            return True
        
        # Продакшн режим
        try:
            results = await asyncio.gather(
                self.exchanges[trade.exchange_short].close_position(trade.symbol, 'SHORT'),
                self.exchanges[trade.exchange_long].close_position(trade.symbol, 'LONG'),
                return_exceptions=True
            )
            
            if not any(isinstance(r, Exception) for r in results):
                trade.status = 'closed'
                trade.close_time = datetime.now()
                # БАГ #7 FIX: Очищаем запись из open_positions
                if pair_id in self.open_positions:
                    del self.open_positions[pair_id]
                return True
                
        except Exception as e:
            print(f"   ❌ Ошибка закрытия: {e}")
        
        return False
    
    async def _rollback_orders(self, results, opportunity, position_size):
        """Откат при неудачном открытии"""
        for i, result in enumerate(results):
            if not isinstance(result, Exception):
                exchange = opportunity.exchange_short if i == 0 else opportunity.exchange_long
                side = 'SHORT' if i == 0 else 'LONG'
                await self.exchanges[exchange].close_position(opportunity.symbol, side)
    
    def get_position(self, pair_id: str) -> Trade:
        """Получение позиции по ID"""
        return self.open_positions.get(pair_id)
    
    def get_all_positions(self) -> Dict[str, Trade]:
        """Получение всех открытых позиций"""
        return self.open_positions
