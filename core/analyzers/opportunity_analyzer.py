"""Opportunity Analyzer - Net Edge Strategy"""
from dataclasses import dataclass
from typing import Optional
from datetime import datetime
from core.models import ArbitragePair
from config.main_config import HIGH_FREQUENCY_SYMBOLS, HF_MIN_NET_EDGE, HF_MAX_BID_ASK_SPREAD


@dataclass
class OpportunityAnalysis:
    """Результат анализа арбитражной возможности"""
    pair: ArbitragePair
    gross_spread_pct: float
    bid_ask_spread_long_pct: float
    bid_ask_spread_short_pct: float
    estimated_fees_pct: float
    estimated_slippage_pct: float
    funding_adjustment_pct: float
    net_edge_pct: float
    approved: bool
    reason: str
    data_age_ms: float


class OpportunityAnalyzer:
    """Анализ арбитражных возможностей с учетом всех издержек"""
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        
        # Thresholds (ужесточены для REST реальности)
        self.MIN_GROSS_SPREAD = self.config.get('MIN_GROSS_SPREAD', 1.0)  # 1% минимум
        self.MIN_NET_EDGE = self.config.get('MIN_NET_EDGE', 0.3)  # 0.3% чистой прибыли
        self.MAX_GROSS_SPREAD = self.config.get('MAX_GROSS_SPREAD', 3.0)  # до 3% (было 5.0)
        self.MAX_BID_ASK_SPREAD_PER_LEG = self.config.get('MAX_BID_ASK_SPREAD_PER_LEG', 0.15)
        self.MAX_DATA_AGE_MS = self.config.get('MAX_DATA_AGE_MS', 500)  # 500ms max
        
        # ИЗМЕНЕНИЕ #4: Адаптивные пороги для высокочастотных символов
        self.HF_MIN_NET_EDGE = HF_MIN_NET_EDGE  # 0.10% для HF символов
        self.HF_MAX_BID_ASK = HF_MAX_BID_ASK_SPREAD  # 0.20% для HF символов
        
        # Trading parameters (реалистичные для REST)
        self.TAKER_FEE_PCT = self.config.get('TAKER_FEE_PCT', 0.05)  # 0.05% per side
        self.SLIPPAGE_PCT = self.config.get('SLIPPAGE_PCT', 0.05)   # 0.05% per side (REST реальность)
        self.REST_EXECUTION_BUFFER = self.config.get('REST_EXECUTION_BUFFER', 0.1)  # 0.1% буфер на REST задержку
        
        # БАГ ОШИБКА #1 FIX: Параметры для корректного расчёта funding cost
        self.MAX_HOLD_TIME_SEC = self.config.get('MAX_HOLD_TIME_SEC', 180)  # 3 минуты для REST
        self.FUNDING_PERIOD_SEC = self.config.get('FUNDING_PERIOD_SEC', 28800)  # 8 часов
    
    def analyze(self, opportunity: ArbitragePair) -> OpportunityAnalysis:
        """Полный анализ арбитражной возможности"""
        
        # 1. Gross spread
        gross_spread_pct = opportunity.spread
        
        # 2. Bid-ask spreads (если доступны)
        bid_ask_long = self._estimate_bid_ask_spread(opportunity.data_long)
        bid_ask_short = self._estimate_bid_ask_spread(opportunity.data_short)
        
        # 3. Fees (открытие + закрытие = 4 сделки)
        estimated_fees_pct = self.TAKER_FEE_PCT * 4
        
        # 4. Slippage (открытие + закрытие = 4 сделки)
        estimated_slippage_pct = self.SLIPPAGE_PCT * 4
        
        # 5. Funding adjustment (БАГ ОШИБКА #1 FIX: пропорционально времени удержания)
        funding_long = opportunity.data_long.funding_rate if opportunity.data_long else 0
        funding_short = opportunity.data_short.funding_rate if opportunity.data_short else 0
        # Корректный расчёт: funding cost * (hold_time / funding_period)
        hold_fraction = self.MAX_HOLD_TIME_SEC / self.FUNDING_PERIOD_SEC
        funding_adjustment_pct = abs(funding_long - funding_short) * 100 * hold_fraction
        
        # 6. Net edge (добавляем REST execution buffer)
        net_edge_pct = (
            gross_spread_pct 
            - estimated_fees_pct 
            - estimated_slippage_pct 
            - bid_ask_long 
            - bid_ask_short 
            - funding_adjustment_pct
            - self.REST_EXECUTION_BUFFER  # Буфер на REST задержку
        )
        
        # 7. Data age
        data_age_ms = self._calculate_data_age(opportunity)
        
        # 8. Approval logic (передаём symbol для адаптивных порогов)
        approved, reason = self._evaluate(
            gross_spread_pct,
            net_edge_pct,
            bid_ask_long,
            bid_ask_short,
            data_age_ms,
            symbol=opportunity.symbol  # ИЗМЕНЕНИЕ #4: передаём symbol
        )
        
        return OpportunityAnalysis(
            pair=opportunity,
            gross_spread_pct=gross_spread_pct,
            bid_ask_spread_long_pct=bid_ask_long,
            bid_ask_spread_short_pct=bid_ask_short,
            estimated_fees_pct=estimated_fees_pct,
            estimated_slippage_pct=estimated_slippage_pct,
            funding_adjustment_pct=funding_adjustment_pct,
            net_edge_pct=net_edge_pct,
            approved=approved,
            reason=reason,
            data_age_ms=data_age_ms
        )
    
    def _estimate_bid_ask_spread(self, market_data) -> float:
        """Оценка bid-ask spread в процентах"""
        if not market_data or not market_data.bid or not market_data.ask:
            return 0.0
        
        mid = (market_data.bid + market_data.ask) / 2
        if mid <= 0:
            return 0.0
        
        spread_pct = ((market_data.ask - market_data.bid) / mid) * 100
        return spread_pct
    
    def _calculate_data_age(self, opportunity: ArbitragePair) -> float:
        """Возраст данных в миллисекундах"""
        now = datetime.now()
        
        ages = []
        if opportunity.data_long and opportunity.data_long.timestamp:
            age_long = (now - opportunity.data_long.timestamp).total_seconds() * 1000
            ages.append(age_long)
        
        if opportunity.data_short and opportunity.data_short.timestamp:
            age_short = (now - opportunity.data_short.timestamp).total_seconds() * 1000
            ages.append(age_short)
        
        return max(ages) if ages else 0.0
    
    def _evaluate(
        self,
        gross_spread: float,
        net_edge: float,
        bid_ask_long: float,
        bid_ask_short: float,
        data_age_ms: float,
        symbol: str = ""  # ИЗМЕНЕНИЕ #4: добавлен параметр symbol
    ) -> tuple[bool, str]:
        """Оценка возможности: approve/reject + причина"""
        
        # ИЗМЕНЕНИЕ #4: Адаптивные пороги для высокочастотных символов
        is_hf = symbol in HIGH_FREQUENCY_SYMBOLS
        min_net_edge = self.HF_MIN_NET_EDGE if is_hf else self.MIN_NET_EDGE
        max_bid_ask = self.HF_MAX_BID_ASK if is_hf else self.MAX_BID_ASK_SPREAD_PER_LEG
        
        # Check 1: Stale data
        if data_age_ms > self.MAX_DATA_AGE_MS:
            return False, f"Stale data ({data_age_ms:.0f}ms > {self.MAX_DATA_AGE_MS}ms)"
        
        # Check 2: Gross spread too low
        if gross_spread < self.MIN_GROSS_SPREAD:
            return False, f"Gross spread too low ({gross_spread:.3f}% < {self.MIN_GROSS_SPREAD}%)"
        
        # Check 3: Gross spread too high (anomaly / trap)
        if gross_spread > self.MAX_GROSS_SPREAD:
            return False, f"Gross spread suspicious ({gross_spread:.3f}% > {self.MAX_GROSS_SPREAD}%) - likely stale/halted"
        
        # Check 4: High spread extra validation (5%+)
        if gross_spread > 5.0:
            # Высокие спреды требуют свежих данных
            if data_age_ms > 200:
                return False, f"High spread with old data ({gross_spread:.3f}%, age {data_age_ms:.0f}ms)"
        
        # Check 5: Bid-ask spread too wide on long leg (адаптивный порог)
        if bid_ask_long > max_bid_ask:
            return False, f"Bid-ask too wide on long leg ({bid_ask_long:.3f}% > {max_bid_ask}%)"
        
        # Check 6: Bid-ask spread too wide on short leg (адаптивный порог)
        if bid_ask_short > max_bid_ask:
            return False, f"Bid-ask too wide on short leg ({bid_ask_short:.3f}% > {max_bid_ask}%)"
        
        # Check 7: Net edge insufficient (адаптивный порог)
        if net_edge < min_net_edge:
            return False, f"Net edge insufficient ({net_edge:.3f}% < {min_net_edge}%)"
        
        # All checks passed
        suffix = " [HF]" if is_hf else ""
        return True, f"Approved: net edge {net_edge:.3f}%{suffix}"
