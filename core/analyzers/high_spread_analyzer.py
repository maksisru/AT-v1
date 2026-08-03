"""High-Spread Analyzer — анализ high-spread возможностей"""
from dataclasses import dataclass
from typing import Optional
from datetime import datetime
from core.models import ArbitragePair
from core.analyzers.high_spread_classifier import SpreadClassification, SpreadType


@dataclass
class HighSpreadAnalysis:
    pair: ArbitragePair
    classification: SpreadClassification
    gross_spread_pct: float
    estimated_fees_pct: float
    estimated_slippage_pct: float
    funding_cost_pct: float
    bid_ask_long_pct: float
    bid_ask_short_pct: float
    net_edge_pct: float
    liquidity_long_usd: float
    liquidity_short_usd: float
    liquidity_ratio: float
    data_age_long_ms: float
    data_age_short_ms: float
    approved: bool
    reject_reason: Optional[str]
    effective_position_size: float


HIGH_SPREAD_CONFIG = {
    "MIN_GROSS_SPREAD":       4.0,
    "MIN_NET_EDGE":           2.0,
    "MAX_GROSS_SPREAD":      25.0,
    "MAX_DATA_AGE_MS":      200.0,
    "MAX_BID_ASK_PER_LEG":    1.0,
    "MIN_LIQUIDITY_RATIO":    5.0,
    "LIQUIDITY_DEPTH_LEVELS": 5,
    "TAKER_FEE_PCT":          0.05,
    "SLIPPAGE_BASE_PCT":      0.10,
    "SLIPPAGE_SHOCK_MULT":    2.0,
    "FUNDING_PERIOD_HOURS":   8.0,
    "BASE_POSITION_FRACTION": 0.08,
    "MAX_POSITION_USD":     500.0,
}


class HighSpreadAnalyzer:
    """Анализатор high-spread возможностей"""

    def __init__(self, config: dict = None, position_size_usd: float = 100.0):
        self.cfg = config or HIGH_SPREAD_CONFIG
        self.base_position_size = position_size_usd

    def analyze(
        self,
        opportunity: ArbitragePair,
        classification: SpreadClassification,
        orderbook_long: dict = None,
        orderbook_short: dict = None,
    ) -> HighSpreadAnalysis:
        """Полный анализ возможности"""
        now_ms = datetime.now().timestamp() * 1000

        # Data age
        age_long  = now_ms - opportunity.data_long.timestamp.timestamp() * 1000
        age_short = now_ms - opportunity.data_short.timestamp.timestamp() * 1000

        # Bid-ask spreads
        ba_long  = self._bid_ask_pct(opportunity.data_long)
        ba_short = self._bid_ask_pct(opportunity.data_short)

        # Fees: 4 legs
        fees = self.cfg["TAKER_FEE_PCT"] * 4

        # Slippage: выше для news shock
        slippage_mult = (
            self.cfg["SLIPPAGE_SHOCK_MULT"]
            if classification.spread_type == SpreadType.NEWS_SHOCK
            else 1.0
        )
        slippage = self.cfg["SLIPPAGE_BASE_PCT"] * 4 * slippage_mult

        # Funding cost для времени удержания
        hold_fraction = classification.max_hold_minutes / (self.cfg["FUNDING_PERIOD_HOURS"] * 60)
        funding_rate_diff = abs(
            (opportunity.data_short.funding_rate or 0)
            - (opportunity.data_long.funding_rate or 0)
        )
        funding_cost = funding_rate_diff * 100 * hold_fraction

        # Net edge
        net_edge = (
            opportunity.spread
            - fees
            - slippage
            - ba_long
            - ba_short
            - funding_cost
        )

        # Liquidity
        liq_long  = self._calc_liquidity(orderbook_long,  "asks")
        liq_short = self._calc_liquidity(orderbook_short, "bids")
        effective_pos = self.base_position_size * classification.size_multiplier
        liq_ratio = (
            min(liq_long, liq_short) / effective_pos
            if effective_pos > 0 else 0.0
        )

        # Effective position size
        effective_pos = min(effective_pos, self.cfg["MAX_POSITION_USD"])

        # Approval
        approved, reason = self._evaluate(
            gross_spread=opportunity.spread,
            net_edge=net_edge,
            classification=classification,
            ba_long=ba_long,
            ba_short=ba_short,
            age_long=age_long,
            age_short=age_short,
            liq_ratio=liq_ratio,
        )

        return HighSpreadAnalysis(
            pair=opportunity,
            classification=classification,
            gross_spread_pct=opportunity.spread,
            estimated_fees_pct=fees,
            estimated_slippage_pct=slippage,
            funding_cost_pct=funding_cost,
            bid_ask_long_pct=ba_long,
            bid_ask_short_pct=ba_short,
            net_edge_pct=net_edge,
            liquidity_long_usd=liq_long,
            liquidity_short_usd=liq_short,
            liquidity_ratio=liq_ratio,
            data_age_long_ms=age_long,
            data_age_short_ms=age_short,
            approved=approved,
            reject_reason=reason if not approved else None,
            effective_position_size=effective_pos,
        )

    def _bid_ask_pct(self, data) -> float:
        if not data or not data.bid or not data.ask or data.bid <= 0:
            return 0.0
        mid = (data.bid + data.ask) / 2
        return (data.ask - data.bid) / mid * 100

    def _calc_liquidity(self, orderbook: dict, side: str) -> float:
        """Считает USD-объём по топ-N уровням стакана"""
        if not orderbook or side not in orderbook:
            return 0.0
        levels = orderbook.get(side, [])
        depth = self.cfg["LIQUIDITY_DEPTH_LEVELS"]
        total = 0.0
        for price, size in levels[:depth]:
            total += float(price) * float(size)
        return total

    def _evaluate(
        self,
        gross_spread, net_edge, classification,
        ba_long, ba_short, age_long, age_short, liq_ratio,
    ):
        if not classification.tradeable:
            return False, f"Classifier: {classification.reason}"

        if age_long > self.cfg["MAX_DATA_AGE_MS"]:
            return False, f"Stale long tick: {age_long:.0f}ms"
        if age_short > self.cfg["MAX_DATA_AGE_MS"]:
            return False, f"Stale short tick: {age_short:.0f}ms"

        if gross_spread < self.cfg["MIN_GROSS_SPREAD"]:
            return False, f"Gross spread {gross_spread:.2f}% < {self.cfg['MIN_GROSS_SPREAD']}%"
        if gross_spread > self.cfg["MAX_GROSS_SPREAD"]:
            return False, f"Gross spread {gross_spread:.2f}% > {self.cfg['MAX_GROSS_SPREAD']}%: likely trap"

        if ba_long > self.cfg["MAX_BID_ASK_PER_LEG"]:
            return False, f"Bid-ask long {ba_long:.3f}% > {self.cfg['MAX_BID_ASK_PER_LEG']}%"
        if ba_short > self.cfg["MAX_BID_ASK_PER_LEG"]:
            return False, f"Bid-ask short {ba_short:.3f}% > {self.cfg['MAX_BID_ASK_PER_LEG']}%"

        if net_edge < self.cfg["MIN_NET_EDGE"]:
            return False, f"Net edge {net_edge:.2f}% < {self.cfg['MIN_NET_EDGE']}%"

        if liq_ratio < self.cfg["MIN_LIQUIDITY_RATIO"]:
            return False, f"Liquidity ratio {liq_ratio:.1f}x < {self.cfg['MIN_LIQUIDITY_RATIO']}x"

        if classification.confidence < 0.5:
            return False, f"Low confidence: {classification.confidence:.2f}"

        return True, None
