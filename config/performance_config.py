"""Высокопроизводительная конфигурация для мощного железа"""

# === ПРОИЗВОДИТЕЛЬНОСТЬ ===
# Для мощного железа увеличиваем параллелизм
MAX_WORKERS = 8                    # ThreadPoolExecutor для анализа
SYMBOLS_PER_EXCHANGE = 50          # До 50 пар на биржу (вместо 10)
ANALYSIS_INTERVAL = 0.1            # Анализ каждые 100ms (вместо 300ms)
QUEUE_MAXSIZE = 5000               # Больший буфер данных

# === WEBSOCKET ===
WS_RECONNECT_DELAY = 1
WS_MAX_RECONNECT_DELAY = 60
WS_PING_INTERVAL = 20
WS_TIMEOUT = 30

# === КЭШИРОВАНИЕ ===
CACHE_TTL = 1                      # Время жизни кэша (секунды)
USE_MARKET_DATA_CACHE = True       # Кэширование рыночных данных

# === МОНИТОРИНГ ===
STATS_INTERVAL = 30                # Статистика каждые 30 сек
OPPORTUNITY_DISPLAY_INTERVAL = 2   # Показ возможностей каждые 2 сек
TOP_OPPORTUNITIES = 10             # Показывать топ-10 (вместо 5)
