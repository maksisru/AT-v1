"""Конфигурация для Opportunity Analyzer"""

# Импортируем пороги из главного конфига для синхронизации
from config.main_config import OPEN_THRESHOLD, MAX_SPREAD_OPEN, MIN_NET_EDGE

# Net Edge Strategy Thresholds
OPPORTUNITY_CONFIG = {
    # Spread thresholds (синхронизировано с config.py)
    'MIN_GROSS_SPREAD': OPEN_THRESHOLD,   # = 0.6% (оптимизировано)
    'MIN_NET_EDGE': MIN_NET_EDGE,         # = 0.12% (оптимизировано)
    'MAX_GROSS_SPREAD': MAX_SPREAD_OPEN,  # = 2.5% (оптимизировано)
    
    # Market quality
    'MAX_BID_ASK_SPREAD_PER_LEG': 0.15,  # Было 0.12 — увеличено для высоколиквидных символов
    'MAX_DATA_AGE_MS': 800,       # Было 500 — увеличено: WebSocket может лагать до 500ms
    
    # Trading costs (оптимизировано для REST)
    'TAKER_FEE_PCT': 0.05,         # Комиссия taker на сделку (%)
    'SLIPPAGE_PCT': 0.05,          # Было 0.02 — увеличено для реальности REST
    'REST_EXECUTION_BUFFER': 0.10, # Добавлен буфер на REST задержки
    
    # Exit strategy
    'TAKE_PROFIT_NET': 0.15,       # Take profit на net edge (%)
    'STOP_LOSS_NET': -0.30,        # Stop loss на net edge (%)
    
    # Funding rate calculation (БАГ ОШИБКА #1 FIX)
    'MAX_HOLD_TIME_SEC': 180,      # Для расчёта funding cost (REST стратегия: 3 минуты)
    'FUNDING_PERIOD_SEC': 28800,   # 8 часов в секундах (стандартный период funding)
}
