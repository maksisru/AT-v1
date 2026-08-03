"""Главная конфигурация арбитражной системы"""

# Биржи (3 working exchanges)
EXCHANGES = ['mexc', 'gate', 'bybit']

# === ЧЕРНЫЙ СПИСОК СИМВОЛОВ ===
# Тикеры с аномальными данными (рыночные коллизии, делистинги, сплиты)
# Полностью исключаются из обработки на уровне WebSocket-агрегатора
BLACKLISTED_SYMBOLS = [
    "EDGEUSDT",  # Аномалия: Gate=0.06532, Bybit=0.4655 (7.13x разница)
]

# === WHITELIST ВЫСОКОЧАСТОТНЫХ СИМВОЛОВ ===
# Символы с доказанной активностью и стабильными спредами (по реальным данным)
HIGH_FREQUENCY_SYMBOLS = [
    "ESPORTSUSDT",   # 74.6% потока данных, стабильные спреды 0.5-1.5%
    "ALLOUSDT",      # 5.9% потока
    "PIPPINUSDT",    # 4.3% потока
    "LABUSDT",       # 4.0% потока
    "CLOUSDT",       # 2.6% потока
]

# Для HF символов — строже общего (ЭКСТРЕМАЛЬНО КОНСЕРВАТИВНАЯ)
HF_MIN_NET_EDGE = 0.50           # Выше общего — только идеальные условия
HF_MAX_BID_ASK_SPREAD = 0.10     # Очень строгий порог ликвидности

# === СТРАТЕГИЯ ОТКРЫТИЯ (REST-оптимизировано) ===
# Для REST торговли требуются более высокие спреды
# из-за задержек исполнения (100-300ms на 2 ордера)

# ЭКСТРЕМАЛЬНО КОНСЕРВАТИВНАЯ СТРАТЕГИЯ (только идеальные возможности)
# Издержки REST: 0.20% fees + 0.20% slippage + 0.10% buffer = 0.50%
OPEN_THRESHOLD = 1.5   # Только спреды >1.5%
MAX_SPREAD_OPEN = 5.0  # Расширен для редких больших возможностей
MIN_NET_EDGE = 0.50    # Тройной запас над издержками (0.50% + 0.50% = 1.0% min gross)

# Фильтр устойчивости спредов (максимально ужесточён)
MIN_SPREAD_PERSISTENCE = 4  # Спред должен держаться 4 итерации (400ms)

# Aggressive mode (использовать с осторожностью!)
AGGRESSIVE_MODE = False
AGGRESSIVE_MAX_SPREAD = 5.0  # Если True, макс спред 5% вместо 3%

# === СТРАТЕГИЯ ЗАКРЫТИЯ (SpreadCollapse для больших спредов) ===
STRATEGY_TYPE = 'collapse'  # Изменено: было 'rest_optimized' (WR=27%), теперь 'collapse'

# SpreadCollapse Strategy (для спредов 1.5-5%)
COLLAPSE_THRESHOLD = 0.3       # Закрываем когда спред сузился до 0.3%
MIN_PROFIT_PCT = 0.25          # Минимальная прибыль для закрытия
MAX_HOLD_TIME_COLLAPSE = 600   # 10 минут (было 3600 для старой стратегии)
COLLAPSE_STOP_LOSS_EXPANSION = 1.5  # Стоп при расширении спреда на 1.5%

# REST Optimized Strategy (устаревшая, оставлена для fallback)
REST_TAKE_PROFIT_PCT = 0.4
REST_STOP_LOSS_PCT = 0.5
REST_MAX_HOLD_TIME = 180
REST_TRAILING_ACTIVATION = 0.5
# Amplitude Strategy
AMPLITUDE_WINDOW = 50
AMPLITUDE_THRESHOLD = 0.7
MIN_AMPLITUDE_USD = 5.0
STOP_LOSS_MULTIPLIER = 2.0
MAX_HOLD_TIME_SEC = 300  # 5 минут

# Collapse Strategy
COLLAPSE_THRESHOLD = 0.1     # Спред схлопнулся до 0.1%
MIN_PROFIT_PCT = 0.05        # Минимальная прибыль 0.05%
MAX_HOLD_TIME_COLLAPSE = 3600  # 1 час

# === РИСК-МЕНЕДЖМЕНТ ===
POSITION_SIZE_FRACTION = 0.1    # 10% от баланса на позицию
MAX_OPEN_POSITIONS = 3          # Максимум 3 позиции одновременно
MAX_POSITIONS_PER_EXCHANGE = 3  # Максимум 3 позиции на одной бирже
MAX_LEVERAGE = 5                # Плечо 5x (было 10x - снижено для безопасности)
                                # При 10x: риск ликвидации -10%, прибыль выше в 2 раза

# БАГ ОШИБКА #4 FIX: Защита от двойных позиций по одному символу
ALLOW_MULTIPLE_POSITIONS_PER_SYMBOL = False  # Запрещаем несколько позиций по одному символу

# УЛУЧШЕНИЕ #2: Cooldown после убыточной сделки
COOLDOWN_AFTER_LOSS_SEC = 300  # 5 минут
                                # При 5x: риск ликвидации -20%, баланс риск/прибыль ✅
MIN_LIQUIDITY_MULTIPLIER = 1.5

# FIX: funding_diff порог (в долях, не процентах)
MAX_FUNDING_DIFF = 0.015  # 1.5% в долях — фильтрует только топ 3% аномальных

# === HIGH-SPREAD STRATEGY ===
HIGH_SPREAD_MODE        = True   # Включить / выключить
HIGH_SPREAD_MIN_PCT     = 4.0    # Минимальный спред для этой стратегии
HIGH_SPREAD_MAX_HOLD    = 90     # Минут (жёсткий лимит)
HIGH_SPREAD_LEVERAGE    = 3      # Меньше плеча — рынки тонкие
HIGH_SPREAD_POS_FRAC    = 0.06   # 6% от баланса на позицию
HIGH_SPREAD_MAX_POS     = 3      # Максимум позиций одновременно

# === TELEGRAM УВЕДОМЛЕНИЯ ===
# ⚠️ ВАЖНО: Токен и chat_id должны быть в .env файле!
# Получите ваш chat_id через @userinfobot в Telegram
# Пример .env:
#   TELEGRAM_BOT_TOKEN=1234567890:ABCdef...
#   TELEGRAM_CHAT_ID=123456789
TELEGRAM_BOT_TOKEN = None  # Читается из .env
TELEGRAM_CHAT_ID = None    # Читается из .env

# Устаревшие (для совместимости)
MAX_POSITION_SIZE = 1000
PROFIT_THRESHOLD_K = 0.8
CLOSE_THRESHOLD = 50

# Мониторинг
SPREAD_HISTORY_LENGTH = 100
LATENCY_WARNING_MS = 500

# WebSocket
WS_RECONNECT_DELAY = 5
WS_PING_INTERVAL = 30
