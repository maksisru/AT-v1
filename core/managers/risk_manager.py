"""Risk Manager — управление рисками"""
from typing import Dict
import time
from datetime import datetime
from core.models import ArbitragePair
from config.main_config import (
    MAX_POSITION_SIZE, 
    MAX_OPEN_POSITIONS, 
    MAX_SPREAD_OPEN,
    POSITION_SIZE_FRACTION,
    MAX_POSITIONS_PER_EXCHANGE,
    ALLOW_MULTIPLE_POSITIONS_PER_SYMBOL,
    COOLDOWN_AFTER_LOSS_SEC,
    MAX_FUNDING_DIFF
)

# Минимальный объём ордера на каждой бирже (USD)
EXCHANGE_MIN_ORDER = {
    'mexc': 5,
    'gate': 5,
    'bybit': 10,
    'asterdex': 10
}


class RiskManager:
    """Управление рисками арбитража"""
    
    def __init__(self, initial_balance: float = 1000):
        self.balance = initial_balance
        self.open_positions: Dict[str, dict] = {}  # {pair_id: {symbol, exchange_long, exchange_short}}
        self.positions_per_exchange = {}  # Подсчет позиций по биржам
        
        # УЛУЧШЕНИЕ #2: Cooldown после убыточных сделок
        self.cooldown_pairs: Dict[str, float] = {}  # pair_key → timestamp
        self.recent_trades = []  # Список PnL для адаптивных порогов
    
    def calculate_position_size(self) -> float:
        """Расчёт размера позиции (1/10 от баланса)"""
        return self.balance * POSITION_SIZE_FRACTION
    
    def check_opportunity(self, opportunity: ArbitragePair, market_data: Dict, analysis=None) -> Dict:
        """Проверка арбитражной возможности на риски
        
        Args:
            opportunity: ArbitragePair
            market_data: Dict с рыночными данными
            analysis: OpportunityAnalysis (опционально, если уже проведен)
        """
        
        # Если есть analysis и он не одобрен - используем его причину
        if analysis and not analysis.approved:
            return {"approved": False, "reason": analysis.reason}
        
        # БАГ ОШИБКА #4 FIX: Проверка на двойные позиции по одному символу
        if not ALLOW_MULTIPLE_POSITIONS_PER_SYMBOL:
            for pos in self.open_positions.values():
                if pos['symbol'] == opportunity.symbol:
                    return {"approved": False, "reason": f"Position already open for {opportunity.symbol}"}
        
        # УЛУЧШЕНИЕ #2: Проверка cooldown после убыточной сделки
        if self.is_in_cooldown(opportunity.symbol, opportunity.exchange_long, opportunity.exchange_short):
            return {"approved": False, "reason": f"Cooldown active for {opportunity.symbol} (recent loss)"}
        
        # 1. Проверка количества открытых позиций (общее)
        if len(self.open_positions) >= MAX_OPEN_POSITIONS:
            return {"approved": False, "reason": f"Max positions reached ({MAX_OPEN_POSITIONS})"}
        
        # 2. Проверка лимита позиций на биржах
        long_positions = self.positions_per_exchange.get(opportunity.exchange_long, 0)
        short_positions = self.positions_per_exchange.get(opportunity.exchange_short, 0)
        
        if long_positions >= MAX_POSITIONS_PER_EXCHANGE:
            return {"approved": False, "reason": f"Max positions on {opportunity.exchange_long} ({MAX_POSITIONS_PER_EXCHANGE})"}
        
        if short_positions >= MAX_POSITIONS_PER_EXCHANGE:
            return {"approved": False, "reason": f"Max positions on {opportunity.exchange_short} ({MAX_POSITIONS_PER_EXCHANGE})"}
        
        # 3. Проверка спреда - используем net_edge если есть analysis
        if analysis:
            # Используем net_edge вместо gross spread
            if analysis.net_edge_pct < 0:
                return {"approved": False, "reason": f"Negative net edge ({analysis.net_edge_pct:.3f}%)"}
        else:
            # Fallback на старую проверку
            if opportunity.spread < 0.1:
                return {"approved": False, "reason": "Spread too low (<0.1%)"}
            
            if opportunity.spread > MAX_SPREAD_OPEN:
                return {"approved": False, "reason": f"Spread too high (>{MAX_SPREAD_OPEN}%) - anomaly"}
        
        # 4. Проверка funding rate (FIX: правильный порог)
        if abs(opportunity.funding_diff) > MAX_FUNDING_DIFF:
            return {
                "approved": False, 
                "reason": f"Funding rate diff too high ({abs(opportunity.funding_diff)*100:.3f}% > {MAX_FUNDING_DIFF*100:.1f}%)"
            }
        
        # 5. Проверка баланса
        position_size = self.calculate_position_size()
        if position_size < 10:  # Минимум 10 USD
            return {"approved": False, "reason": "Insufficient balance"}
        
        # 5.1. Проверка минимального объёма ордера по биржам
        min_long = EXCHANGE_MIN_ORDER.get(opportunity.exchange_long, 10)
        min_short = EXCHANGE_MIN_ORDER.get(opportunity.exchange_short, 10)
        min_required = max(min_long, min_short)
        
        if position_size < min_required:
            return {"approved": False, "reason": f"Position size ${position_size:.2f} below exchange minimum ${min_required}"}
        
        # 6. Проверка ликвидности (orderbook depth)
        liquidity_check = self._check_liquidity(opportunity, market_data, position_size)
        if not liquidity_check["approved"]:
            return liquidity_check
        
        # ✅ Одобрено
        return {
            "approved": True,
            "reason": "All checks passed",
            "position_size": position_size
        }
    
    def _check_liquidity(self, opportunity: ArbitragePair, market_data: Dict, position_size: float) -> Dict:
        """Проверка достаточной ликвидности в orderbook"""
        long_data = market_data.get(opportunity.exchange_long, {}).get(opportunity.symbol)
        short_data = market_data.get(opportunity.exchange_short, {}).get(opportunity.symbol)
        
        if not long_data or not short_data:
            return {"approved": False, "reason": "Missing market data"}
        
        # Проверяем volume (если доступен)
        # Для LONG нужно купить по ask, для SHORT — продать по bid
        if hasattr(long_data, 'volume') and long_data.volume > 0:
            # Требуем минимум 3x от размера нашей позиции
            min_volume_required = position_size * 3
            if long_data.volume < min_volume_required:
                return {"approved": False, "reason": f"Low liquidity on {opportunity.exchange_long} (volume ${long_data.volume:.0f} < ${min_volume_required:.0f})"}
        
        if hasattr(short_data, 'volume') and short_data.volume > 0:
            min_volume_required = position_size * 3
            if short_data.volume < min_volume_required:
                return {"approved": False, "reason": f"Low liquidity on {opportunity.exchange_short} (volume ${short_data.volume:.0f} < ${min_volume_required:.0f})"}
        
        return {"approved": True, "reason": "Sufficient liquidity"}
    
    def register_position(self, pair_id: str, symbol: str, exchange_long: str, exchange_short: str):
        """Регистрация открытой позиции с полными метаданными"""
        self.open_positions[pair_id] = {
            'symbol': symbol,
            'exchange_long': exchange_long,
            'exchange_short': exchange_short,
            'opened_at': datetime.now(),
        }
        # Увеличиваем счетчики для обеих бирж
        self.positions_per_exchange[exchange_long] = self.positions_per_exchange.get(exchange_long, 0) + 1
        self.positions_per_exchange[exchange_short] = self.positions_per_exchange.get(exchange_short, 0) + 1
    
    def unregister_position(self, pair_id: str):
        """Удаление закрытой позиции"""
        if pair_id not in self.open_positions:
            return
        
        pos = self.open_positions.pop(pair_id)
        
        # Уменьшаем счетчики для бирж
        for ex in [pos['exchange_long'], pos['exchange_short']]:
            if ex in self.positions_per_exchange:
                self.positions_per_exchange[ex] = max(0, self.positions_per_exchange[ex] - 1)
                if self.positions_per_exchange[ex] == 0:
                    del self.positions_per_exchange[ex]
    
    def get_open_count(self) -> int:
        """Получить количество открытых позиций"""
        return len(self.open_positions)
    
    def update_balance(self, pnl: float):
        """Обновление баланса после закрытия позиции"""
        self.balance += pnl
        print(f"💰 Balance updated: {self.balance:.2f} USD (PnL: {pnl:+.2f} USD)")
    
    def register_loss(self, symbol: str, exchange_long: str, exchange_short: str):
        """УЛУЧШЕНИЕ #2: Регистрация убыточной сделки — устанавливает cooldown"""
        key = f"{symbol}|{exchange_long}|{exchange_short}"
        self.cooldown_pairs[key] = time.time()
    
    def is_in_cooldown(self, symbol: str, exchange_long: str, exchange_short: str) -> bool:
        """УЛУЧШЕНИЕ #2: Проверка активен ли cooldown для этой пары"""
        key = f"{symbol}|{exchange_long}|{exchange_short}"
        if key not in self.cooldown_pairs:
            return False
        return (time.time() - self.cooldown_pairs[key]) < COOLDOWN_AFTER_LOSS_SEC

