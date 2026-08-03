"""Strategy Selector — динамический выбор стратегии по спреду"""
from strategies import AmplitudeStrategy, BalancedStrategy, SpreadCollapseStrategy
from strategies.rest_optimized_strategy import RestOptimizedStrategy
from core.analyzers.high_spread_exit_strategy import HighSpreadExitStrategy
from core.analyzers.high_spread_classifier import SpreadType
from config.main_config import STRATEGY_TYPE, REST_TAKE_PROFIT_PCT, REST_STOP_LOSS_PCT, REST_MAX_HOLD_TIME, REST_TRAILING_ACTIVATION, HIGH_SPREAD_MODE, HIGH_SPREAD_MIN_PCT


class StrategySelector:
    """Выбор стратегии закрытия в зависимости от размера спреда"""
    
    def __init__(self):
        # Инициализируем все стратегии
        self.amplitude = AmplitudeStrategy()
        self.balanced = BalancedStrategy()
        self.collapse = SpreadCollapseStrategy()
        self.rest_optimized = RestOptimizedStrategy(
            take_profit_pct=REST_TAKE_PROFIT_PCT,
            stop_loss_pct=REST_STOP_LOSS_PCT,
            max_hold_time_sec=REST_MAX_HOLD_TIME,
            trailing_stop_activation=REST_TRAILING_ACTIVATION
        )
        self.high_spread = HighSpreadExitStrategy()
    
    def select_strategy(self, spread: float):
        """
        Выбор стратегии по конфигурации или по спреду:
        - high_spread: для спредов ≥ 4%
        - rest_optimized: REST-оптимизированная (рекомендуется)
        - amplitude: амплитудная (0.7-2%)
        - balanced: сбалансированная (2-5%)
        - collapse: схлопывание (5%+)
        """
        # High-spread стратегия имеет приоритет
        if HIGH_SPREAD_MODE and spread >= HIGH_SPREAD_MIN_PCT:
            return self.high_spread, "high_spread"
        
        # Если в конфиге указана rest_optimized - используем её
        if STRATEGY_TYPE == 'rest_optimized':
            return self.rest_optimized, "rest_optimized"
        
        # Иначе выбираем по спреду
        if spread < 2.0:
            return self.amplitude, "amplitude"
        elif spread < 5.0:
            return self.balanced, "balanced"
        else:
            return self.collapse, "collapse"
    
    def should_close(self, trade, market_data):
        """Проверка закрытия через стратегию которая была при открытии"""
        strategy_name = getattr(trade, 'strategy_name', 'balanced')
        
        # High-spread стратегия с метаданными
        if strategy_name == 'high_spread':
            spread_type_str = getattr(trade, 'hs_spread_type', None)
            max_hold_min = getattr(trade, 'hs_max_hold_min', 60)
            
            # Конвертируем строку обратно в enum
            spread_type = SpreadType.UNKNOWN
            if spread_type_str:
                try:
                    spread_type = SpreadType(spread_type_str)
                except ValueError:
                    pass
            
            signal = self.high_spread.should_close(
                trade,
                market_data,
                spread_type=spread_type,
                entry_spread=trade.entry_spread,
                max_hold_minutes=max_hold_min,
            )
            return signal.should_close, signal.reason
        
        # Остальные стратегии
        if strategy_name == 'rest_optimized':
            return self.rest_optimized.should_close(trade, market_data)
        elif strategy_name == 'amplitude':
            return self.amplitude.should_close(trade, market_data)
        elif strategy_name == 'collapse':
            return self.collapse.should_close(trade, market_data)
        else:
            return self.balanced.should_close(trade, market_data)
