"""High-Spread Classifier — определение типа спреда"""
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
from core.models import ArbitragePair


class SpreadType(Enum):
    PRICE_DIV    = "price_divergence"
    FUNDING_IMB  = "funding_imbalance"
    NEWS_SHOCK   = "news_shock"
    STALE        = "stale_data"
    UNKNOWN      = "unknown"


@dataclass
class SpreadClassification:
    spread_type: SpreadType
    tradeable: bool
    confidence: float        # 0.0–1.0
    max_hold_minutes: int
    size_multiplier: float   # 1.0 = стандарт, 0.5 = осторожно, 0.0 = не входить
    reason: str


class HighSpreadClassifier:
    """Классифицирует источник высокого спреда"""

    STALE_AGE_THRESHOLD_MS   = 3000
    AGE_DIFF_THRESHOLD_MS    = 2000
    FUNDING_IMB_THRESHOLD    = 0.003   # 0.3% в долях
    FUNDING_CLOSE_THRESHOLD  = 0.0001

    def classify(self, opportunity: ArbitragePair, market_data: dict) -> SpreadClassification:
        """Основной метод классификации"""
        now_ms = datetime.now().timestamp() * 1000
        
        data_long  = opportunity.data_long
        data_short = opportunity.data_short

        if not data_long or not data_short:
            return SpreadClassification(
                spread_type=SpreadType.UNKNOWN,
                tradeable=False,
                confidence=0.0,
                max_hold_minutes=0,
                size_multiplier=0.0,
                reason="Missing market data",
            )

        age_long  = now_ms - data_long.timestamp.timestamp() * 1000
        age_short = now_ms - data_short.timestamp.timestamp() * 1000
        age_diff  = abs(age_long - age_short)
        max_age   = max(age_long, age_short)

        # 1. Stale data check
        if max_age > self.STALE_AGE_THRESHOLD_MS:
            stale_side = opportunity.exchange_long if age_long > age_short else opportunity.exchange_short
            return SpreadClassification(
                spread_type=SpreadType.STALE,
                tradeable=False,
                confidence=1.0,
                max_hold_minutes=0,
                size_multiplier=0.0,
                reason=f"Stale tick on {stale_side}: {max_age:.0f}ms old",
            )

        funding_diff_abs = abs(
            (data_short.funding_rate or 0) - (data_long.funding_rate or 0)
        )

        # 2. News shock check
        if age_diff > self.AGE_DIFF_THRESHOLD_MS and max_age < self.STALE_AGE_THRESHOLD_MS:
            return SpreadClassification(
                spread_type=SpreadType.NEWS_SHOCK,
                tradeable=True,
                confidence=0.6,
                max_hold_minutes=10,
                size_multiplier=0.5,
                reason=f"Tick age asymmetry {age_diff:.0f}ms: possible news event",
            )

        # 3. Funding imbalance check
        if funding_diff_abs > self.FUNDING_IMB_THRESHOLD:
            effective_edge = opportunity.spread - funding_diff_abs * 100
            if effective_edge < 2.0:
                return SpreadClassification(
                    spread_type=SpreadType.FUNDING_IMB,
                    tradeable=False,
                    confidence=0.8,
                    max_hold_minutes=0,
                    size_multiplier=0.0,
                    reason=f"Funding imbalance {funding_diff_abs*100:.3f}% erodes edge to {effective_edge:.2f}%",
                )
            return SpreadClassification(
                spread_type=SpreadType.FUNDING_IMB,
                tradeable=True,
                confidence=0.7,
                max_hold_minutes=60,
                size_multiplier=0.75,
                reason=f"Funding imbalance {funding_diff_abs*100:.3f}%, effective edge {effective_edge:.2f}%",
            )

        # 4. Clean price divergence
        if funding_diff_abs < self.FUNDING_CLOSE_THRESHOLD:
            return SpreadClassification(
                spread_type=SpreadType.PRICE_DIV,
                tradeable=True,
                confidence=0.85,
                max_hold_minutes=120,
                size_multiplier=1.0,
                reason="Clean price divergence: funding diff < 0.01%",
            )

        # Fallback
        return SpreadClassification(
            spread_type=SpreadType.UNKNOWN,
            tradeable=True,
            confidence=0.5,
            max_hold_minutes=30,
            size_multiplier=0.5,
            reason="Mixed signals, entering with reduced size",
        )
