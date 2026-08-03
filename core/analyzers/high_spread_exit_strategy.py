"""High-Spread Exit Strategy — стратегия выхода для high-spread арбитража"""
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Tuple
from core.models import Trade, MarketData
from core.analyzers.high_spread_classifier import SpreadType


@dataclass
class ExitSignal:
    should_close: bool
    reason: str
    urgency: str    # "normal" | "urgent" | "emergency"


class HighSpreadExitStrategy:
    """Стратегия выхода для high-spread арбитража"""

    # Параметры по типу спреда
    PARAMS = {
        SpreadType.PRICE_DIV: {
            "target_closure_ratio":  0.60,
            "emergency_expansion":   1.50,
            "trailing_activation":   0.40,
            "trailing_distance":     0.30,
        },
        SpreadType.FUNDING_IMB: {
            "target_closure_ratio":  0.50,
            "emergency_expansion":   1.00,
            "trailing_activation":   0.30,
            "trailing_distance":     0.20,
        },
        SpreadType.NEWS_SHOCK: {
            "target_closure_ratio":  0.40,
            "emergency_expansion":   0.80,
            "trailing_activation":   0.25,
            "trailing_distance":     0.15,
        },
        SpreadType.UNKNOWN: {
            "target_closure_ratio":  0.45,
            "emergency_expansion":   1.00,
            "trailing_activation":   0.30,
            "trailing_distance":     0.25,
        },
    }

    FUNDING_WARNING_MINUTES = 30
    FUNDING_PERIOD_MINUTES  = 480

    def __init__(self):
        self._peak_spread_reduction: Dict[str, float] = {}

    def should_close(
        self,
        trade: Trade,
        market_data: Dict[str, Dict[str, MarketData]],
        spread_type: SpreadType = SpreadType.UNKNOWN,
        entry_spread: float = None,
        max_hold_minutes: int = 60,
    ) -> ExitSignal:
        """Проверка условий закрытия"""
        params = self.PARAMS.get(spread_type, self.PARAMS[SpreadType.UNKNOWN])
        entry_spread = entry_spread or trade.entry_spread
        now = datetime.now()
        hold_minutes = (now - trade.open_time).total_seconds() / 60

        # Текущий спред
        long_data  = market_data.get(trade.exchange_long,  {}).get(trade.symbol)
        short_data = market_data.get(trade.exchange_short, {}).get(trade.symbol)

        if not long_data or not short_data:
            return ExitSignal(
                should_close=True,
                reason="Missing market data",
                urgency="emergency",
            )

        current_spread = (short_data.bid - long_data.ask) / long_data.ask * 100
        spread_reduction = entry_spread - current_spread

        # Обновляем пик сужения
        pair_id = trade.pair_id
        prev_peak = self._peak_spread_reduction.get(pair_id, float("-inf"))
        if spread_reduction > prev_peak:
            self._peak_spread_reduction[pair_id] = spread_reduction

        peak_reduction = self._peak_spread_reduction.get(pair_id, 0.0)
        target_reduction = entry_spread * params["target_closure_ratio"]

        # 1. Emergency: спред расширился
        expansion = -spread_reduction
        if expansion > params["emergency_expansion"]:
            return ExitSignal(
                should_close=True,
                reason=f"Emergency: spread expanded {expansion:.2f}% beyond entry {entry_spread:.2f}%",
                urgency="emergency",
            )

        # 2. Time limit
        if hold_minutes >= max_hold_minutes:
            return ExitSignal(
                should_close=True,
                reason=f"Time limit: {hold_minutes:.0f}min >= {max_hold_minutes}min",
                urgency="urgent",
            )

        # 3. Funding warning
        if spread_type == SpreadType.FUNDING_IMB:
            minutes_to_funding = self._minutes_to_next_funding(now)
            if minutes_to_funding <= self.FUNDING_WARNING_MINUTES and spread_reduction > 0:
                return ExitSignal(
                    should_close=True,
                    reason=f"Funding in {minutes_to_funding:.0f}min, locking in {spread_reduction:.2f}%",
                    urgency="urgent",
                )

        # 4. Profit target
        if spread_reduction >= target_reduction:
            return ExitSignal(
                should_close=True,
                reason=f"Target: spread reduced {spread_reduction:.2f}% (target {target_reduction:.2f}%)",
                urgency="normal",
            )

        # 5. Trailing close
        trailing_activation = entry_spread * params["trailing_activation"]
        if peak_reduction >= trailing_activation:
            drawback = peak_reduction - spread_reduction
            if drawback >= params["trailing_distance"]:
                return ExitSignal(
                    should_close=True,
                    reason=f"Trailing: peak {peak_reduction:.2f}%, drawback {drawback:.2f}%",
                    urgency="normal",
                )

        return ExitSignal(
            should_close=False,
            reason=f"Holding: spread {current_spread:.2f}% (entry {entry_spread:.2f}%, reduced {spread_reduction:.2f}%, time {hold_minutes:.0f}/{max_hold_minutes}min)",
            urgency="normal",
        )

    def cleanup(self, pair_id: str):
        """Очистка состояния трейлинга"""
        self._peak_spread_reduction.pop(pair_id, None)

    @staticmethod
    def _minutes_to_next_funding(now: datetime) -> float:
        """UTC-время до следующего funding settlement"""
        utc_hour = now.utctimetuple().tm_hour
        utc_min  = now.utctimetuple().tm_min
        current_minutes = utc_hour * 60 + utc_min
        funding_times = [0, 480, 960]  # 0:00, 8:00, 16:00
        for ft in funding_times:
            if ft > current_minutes:
                return ft - current_minutes
        return 1440 - current_minutes
