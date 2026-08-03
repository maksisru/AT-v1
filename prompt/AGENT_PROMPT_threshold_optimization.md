# AGENT_PROMPT: ОПТИМИЗАЦИЯ ПОРОГОВ НА ОСНОВЕ РЕАЛЬНЫХ ДАННЫХ

**Дата анализа:** 2026-06-08  
**Источник данных:** `spreads_20260608_043222.csv` + `spreads_20260608_062803.csv`  
**Итого строк:** 7 776 (период ~3 часа, 04:36–09:33 UTC)  

---

## КОНТЕКСТ: ЧТО ПОКАЗАЛИ РЕАЛЬНЫЕ ДАННЫЕ

### Распределение gross_spread_pct (по реальным наблюдениям):

```
0.5–0.7%  :  2 434 строк  (31.3%)   ← здесь БОЛЬШИНСТВО возможностей
0.7–1.0%  :  2 108 строк  (27.1%)
1.0–1.5%  :  2 045 строк  (26.3%)
1.5–2.0%  :    605 строк  ( 7.8%)
2.0–3.0%  :    449 строк  ( 5.8%)
3.0–5.0%  :    134 строк  ( 1.7%)
5.0%+     :      1 строка ( 0.0%)
```

**Вывод:** 58.4% всех возможностей находится в диапазоне 0.5–1.0%. Текущий MIN=1.0% **отрезает 58% рынка**.

### Реальные net_edge при суммарных издержках 0.50% (fees 0.20% + slippage 0.20% + REST buffer 0.10%):

```
Медиана net_edge  = 0.396%
Среднее net_edge  = 0.576%
p25               = 0.154%
p75               = 0.786%
Строк с net>0     = 7 770 / 7 776 (99.9%)
```

### Сравнение конфигураций (симуляция на 3 часах данных → в сутки):

| Конфигурация | MIN gross | MAX gross | min_net | Оппортунити/день | Avg net edge | Est. PnL/день* |
|---|---|---|---|---|---|---|
| **Текущая** | 1.0% | 3.0% | 0.30% | ~25 120 | 0.995% | высокий |
| **Aggressive** ✅ | 0.6% | 2.5% | 0.15% | ~44 288 | 0.628% | **+11% vs текущей** |
| Sweet Spot | 0.8% | 2.5% | 0.25% | ~33 448 | 0.759% | сопоставимо |
| Conservative | 0.7% | 2.0% | 0.20% | ~38 472 | 0.614% | чуть ниже |
| High-Only | 2.0% | 5.0% | 0.50% | ~4 688 | 2.217% | -58% |

*При $100 позиция, 5x плечо, 60% win rate

### Критический баг с funding_diff в risk_manager.py:

```python
# ТЕКУЩИЙ КОД В risk_manager.py:
if abs(opportunity.funding_diff) > 0.01:  # "1%"
    return {"approved": False, "reason": "Funding rate diff too high (>1%)"}
```

**Проблема:** `funding_diff_pct` в CSV хранится в долях (0.023 = 2.3%). Значение `0.01` это **0.01%**, а не 1%.  
Реальный диапазон в данных: 0.000 – 0.023 (т.е. 0–2.3%).  
С порогом `0.01` отклоняется **47.5% всех возможностей** — даже валидных.  
С порогом `0.02` отклоняется только 3.0% (реально аномальные).

### Топ-символы:

```
ESPORTSUSDT   :  5 804 строк (74.6%) — доминирующий символ
ALLOUSDT      :    460 строк
PIPPINUSDT    :    335 строк
LABUSDT       :    310 строк
CLOUSDT       :    204 строк
```

ESPORTSUSDT активен на парах gate→mexc, bybit→mexc, gate→bybit. Ему нужен отдельный whitelist.

### Доминирующие пары бирж:

```
gate→mexc   : 33.6%
bybit→mexc  : 30.8%
gate→bybit  : 15.6%
mexc→gate   :  8.3%
mexc→bybit  :  6.5%
bybit→gate  :  5.2%
```

---

## ЗАДАЧА ДЛЯ АГЕНТА: 5 ИЗМЕНЕНИЙ В ПОРЯДКЕ ПРИОРИТЕТА

---

### ИЗМЕНЕНИЕ #1 (P0 — КРИТИЧНО): Исправить баг с funding_diff порогом

**Файл:** `config/main_config.py` и `core/managers/risk_manager.py`

**Проблема:** Текущий порог `0.01` интерпретируется как "1%", но funding_diff хранится в долях (0.01 = 1%). Реальные данные показывают max = 0.023. С текущим порогом система отвергает 47.5% валидных возможностей.

**Исправление в `config/main_config.py`:**
```python
# БЫЛО:
# Неявный порог 0.01 в risk_manager

# СТАЛО — добавить константу:
MAX_FUNDING_DIFF = 0.015   # 1.5% в долях — фильтрует только топ 3% аномальных
```

**Исправление в `core/managers/risk_manager.py`:**
```python
# БЫЛО:
if abs(opportunity.funding_diff) > 0.01:
    return {"approved": False, "reason": "Funding rate diff too high (>1%)"}

# СТАЛО:
from config.main_config import MAX_FUNDING_DIFF
if abs(opportunity.funding_diff) > MAX_FUNDING_DIFF:
    return {
        "approved": False,
        "reason": f"Funding rate diff too high ({abs(opportunity.funding_diff)*100:.3f}% > {MAX_FUNDING_DIFF*100:.1f}%)"
    }
```

**Ожидаемый эффект:** +47% дополнительных возможностей, ранее ошибочно отфильтрованных.

**Проверка:**
```python
# Должно быть: funding_diff=0.009 → ОДОБРЕНО (было: ОТКЛОНЕНО)
# Должно быть: funding_diff=0.020 → ОТКЛОНЕНО
```

---

### ИЗМЕНЕНИЕ #2 (P1 — ВЫСОКИЙ): Снизить MIN_GROSS_SPREAD и скорректировать MIN_NET_EDGE

**Файл:** `config/main_config.py` и `config/opportunity_config.py`

**Обоснование на данных:**
- 58.4% возможностей в диапазоне 0.5–1.0%
- При суммарных издержках 0.5% и MIN gross=0.6%, реальный net_edge = 0.1–0.5% — торгуемо
- `Aggressive` конфигурация даёт на ~11% больше estimated PnL чем текущая

**Исправление в `config/main_config.py`:**
```python
# БЫЛО:
OPEN_THRESHOLD = 1.0   # Минимальный спред для открытия
MAX_SPREAD_OPEN = 3.0  # Максимальный спред
MIN_NET_EDGE = 0.3     # Минимальная чистая прибыль

# СТАЛО:
OPEN_THRESHOLD = 0.6   # ↓ снизили: 58% рынка было недоступно
MAX_SPREAD_OPEN = 2.5  # ↓ снизили: спреды >2.5% редки (только 7.5% данных) и рискованны
MIN_NET_EDGE = 0.12    # ↓ снизили: при gross 0.6-1.0% net_edge реально 0.1-0.5%
```

**Исправление в `config/opportunity_config.py`:**
```python
OPPORTUNITY_CONFIG = {
    'MIN_GROSS_SPREAD': 0.6,    # было 1.0 → снижено на данных
    'MIN_NET_EDGE': 0.12,       # было 0.3 → снижено: соответствует реальному распределению
    'MAX_GROSS_SPREAD': 2.5,    # было 3.0 → снижено: выше рискованно
    'MAX_BID_ASK_SPREAD_PER_LEG': 0.15,   # без изменений
    'MAX_DATA_AGE_MS': 500,               # без изменений
    'TAKER_FEE_PCT': 0.05,
    'SLIPPAGE_PCT': 0.05,
    'REST_EXECUTION_BUFFER': 0.10,
    'MAX_HOLD_TIME_SEC': 180,
    'FUNDING_PERIOD_SEC': 28800,
}
```

**Ожидаемый эффект:** В 1.75x больше одобренных возможностей при сопоставимом или лучшем среднем net_edge.

---

### ИЗМЕНЕНИЕ #3 (P1 — ВЫСОКИЙ): Скорректировать MAX_SPREAD_OPEN и добавить blacklist аномальных символов

**Файл:** `config/main_config.py`

**Обоснование:** 
- Спреды >2.5% составляют только 7.5% данных
- ESPORTSUSDT (74.6% всего потока) — доминирует, его нужно разрешить явно
- Аномалии EDGEUSDT уже в blacklist — нужно добавить проверку на низколиквидные символы с нестабильными спредами

**Исправление в `config/main_config.py`:**
```python
# БЫЛО:
MAX_SPREAD_OPEN = 3.0

# СТАЛО:
MAX_SPREAD_OPEN = 2.5   # Реальные данные: выше 2.5% — только 7.5% наблюдений

# Добавить whitelist символов с доказанной активностью:
HIGH_FREQUENCY_SYMBOLS = [
    "ESPORTSUSDT",    # 74.6% потока данных, стабильный спред
    "ALLOUSDT",
    "PIPPINUSDT",
    "LABUSDT",
    "CLOUSDT",
]

# Для HIGH_FREQUENCY_SYMBOLS можно использовать более агрессивные пороги:
HF_MIN_NET_EDGE = 0.10   # Чуть ниже чем общий, т.к. высокая частота компенсирует
```

**Добавить в `core/managers/risk_manager.py`:**
```python
from config.main_config import HIGH_FREQUENCY_SYMBOLS, HF_MIN_NET_EDGE

# В check_opportunity() — перед стандартными проверками:
is_hf_symbol = opportunity.symbol in HIGH_FREQUENCY_SYMBOLS
# Если символ высокочастотный — позволяем чуть более низкий net_edge
# (это уже учтено в opportunity_analyzer через MIN_NET_EDGE=0.12, данный блок для будущего)
```

---

### ИЗМЕНЕНИЕ #4 (P2): Добавить adaptive_threshold для ESPORTSUSDT и топ-символов

**Файл:** `core/analyzers/opportunity_analyzer.py`

**Обоснование:** ESPORTSUSDT генерирует 74.6% потока. У него avg gross spread = 1.046%, что означает при издержках 0.5% → avg net_edge = 0.546%. Имеет смысл обрабатывать его с отдельным (более низким) порогом bid-ask, т.к. он торгуется активно.

**Исправление в `opportunity_analyzer.py`:**
```python
from config.main_config import HIGH_FREQUENCY_SYMBOLS

class OpportunityAnalyzer:
    def __init__(self, config=None):
        # ... существующий код ...
        # Для высокочастотных символов — увеличенный допуск на bid-ask
        self.HF_MAX_BID_ASK = self.config.get('HF_MAX_BID_ASK_SPREAD_PER_LEG', 0.20)

    def _evaluate(self, gross_spread, net_edge, bid_ask_long, bid_ask_short, data_age_ms, symbol=""):
        # Определяем пороги для данного символа
        is_hf = symbol in HIGH_FREQUENCY_SYMBOLS
        max_ba = self.HF_MAX_BID_ASK if is_hf else self.MAX_BID_ASK_SPREAD_PER_LEG
        min_net = (self.MIN_NET_EDGE * 0.8) if is_hf else self.MIN_NET_EDGE  # -20% для HF

        # ... остальная логика evaluate с max_ba и min_net ...
```

**Также передавать symbol в analyze():**
```python
def analyze(self, opportunity: ArbitragePair) -> OpportunityAnalysis:
    # ... существующий код ...
    approved, reason = self._evaluate(
        gross_spread_pct, net_edge_pct,
        bid_ask_long, bid_ask_short,
        data_age_ms,
        symbol=opportunity.symbol  # ← добавить
    )
```

---

### ИЗМЕНЕНИЕ #5 (P3): Настроить MAX_DATA_AGE_MS под реальные условия

**Файл:** `config/opportunity_config.py`

**Обоснование:** При интервале анализа 100ms (из `performance_config.py`) и WebSocket latency 10-50ms, данные старше 500ms уже устарели. Но для высокочастотных символов с большим потоком (ESPORTSUSDT) нормально иметь данные возраста 200-300ms. Текущий MAX=500ms слишком строг для них.

**Исправление:**
```python
# В opportunity_config.py:
OPPORTUNITY_CONFIG = {
    # ...
    'MAX_DATA_AGE_MS': 800,   # было 500 → увеличить: WebSocket может лагать до 500ms
    # ...
}
```

---

## ИТОГОВАЯ ТАБЛИЦА ИЗМЕНЕНИЙ

| # | Файл | Параметр | Было | Стало | Обоснование |
|---|---|---|---|---|---|
| 1 | `risk_manager.py` | funding_diff порог | `> 0.01` | `> 0.015` | Баг: отклоняло 47.5% валидных оппортунити |
| 2 | `main_config.py` | `OPEN_THRESHOLD` | `1.0` | `0.6` | 58% рынка было недоступно |
| 2 | `main_config.py` | `MIN_NET_EDGE` | `0.3` | `0.12` | Реальный median net_edge = 0.396% |
| 2 | `main_config.py` | `MAX_SPREAD_OPEN` | `3.0` | `2.5` | Выше 2.5% только 7.5% данных |
| 3 | `main_config.py` | `HIGH_FREQUENCY_SYMBOLS` | нет | добавить | ESPORTSUSDT = 74.6% потока |
| 4 | `opportunity_analyzer.py` | symbol-aware thresholds | нет | добавить | Разные активы — разные условия ликвидности |
| 5 | `opportunity_config.py` | `MAX_DATA_AGE_MS` | `500` | `800` | WebSocket latency реально до 500ms |

---

## ВАЖНЫЕ ПРЕДУПРЕЖДЕНИЯ

### ⚠️ Единицы измерения funding_diff — критично проверить

В `risk_manager.py` передаётся `opportunity.funding_diff` из `ArbitragePair`. Нужно убедиться, что это те же единицы что в CSV (`funding_diff_pct`): значения 0.000–0.023 (доли, не проценты). Если `ArbitrageEngine` умножает на 100 перед присвоением — порог должен быть `1.5` (не `0.015`). Проверить через:

```python
# В ArbitrageEngine._check_pair_batch():
print(f"DEBUG funding_diff assigned: {funding_diff_1}")
```

### ⚠️ ESPORTSUSDT: ликвидность

74.6% потока — один символ. При позиции $100 × 5x = $500 notional это приемлемо, но при масштабировании ($1000+) нужно проверить глубину стакана. Рекомендуется добавить `MIN_LIQUIDITY_RATIO = 3.0` в `RiskManager._check_liquidity()` для символов с малым объёмом.

### ⚠️ Период наблюдения: только 04:36–09:33 UTC

Данные собраны за 3 часа утреннего UTC-времени (Азиатская/Европейская сессия). Паттерны могут меняться в Американскую сессию (14:00–22:00 UTC). Рекомендуется собрать ещё 24+ часов перед live-торговлей с новыми порогами.

---

## ЧЕКЛИСТ ПОСЛЕ ВНЕСЕНИЯ ИЗМЕНЕНИЙ

```bash
# 1. Проверить импорты
python -c "import main; print('OK')"

# 2. Тест risk_manager с новым funding порогом
python -c "
from core.managers.risk_manager import RiskManager
from core.models import ArbitragePair, MarketData
from datetime import datetime

rm = RiskManager(initial_balance=1000)
# funding_diff = 0.009 (ниже нового порога 0.015) — должен пройти
opp = ArbitragePair('mexc','gate','ESPORTSUSDT',0.8,0.009,0.5,0.503,datetime.now())
result = rm.check_opportunity(opp, {})
print('funding_diff=0.009:', result['approved'], result.get('reason',''))

# funding_diff = 0.020 (выше порога) — должен быть отклонён
opp2 = ArbitragePair('mexc','gate','ESPORTSUSDT',0.8,0.020,0.5,0.503,datetime.now())
result2 = rm.check_opportunity(opp2, {})
print('funding_diff=0.020:', result2['approved'], result2.get('reason',''))
"

# 3. Тест opportunity_analyzer с новыми порогами
python -c "
from core.analyzers.opportunity_analyzer import OpportunityAnalyzer
from config.opportunity_config import OPPORTUNITY_CONFIG
oa = OpportunityAnalyzer(config=OPPORTUNITY_CONFIG)
print('MIN_GROSS_SPREAD:', oa.MIN_GROSS_SPREAD, '(expected 0.6)')
print('MIN_NET_EDGE:', oa.MIN_NET_EDGE, '(expected 0.12)')
print('MAX_GROSS_SPREAD:', oa.MAX_GROSS_SPREAD, '(expected 2.5)')
"

# 4. Запустить demo 30 минут и проверить % одобренных оппортунити
# Ожидается: было ~10-15% одобрено, стало ~40-60% одобрено
python main.py
```

---

## ОЖИДАЕМЫЕ РЕЗУЛЬТАТЫ ПОСЛЕ ОПТИМИЗАЦИИ

```
БЫЛО (текущие пороги):
  Скорость: 10-15% оппортунити проходят фильтры
  Причины отклонения: ~47% из-за funding_diff (баг), ~35% из-за MIN=1.0%
  Примерно: 5-10 сделок/час

СТАНЕТ (новые пороги):
  Скорость: ~60-70% оппортунити проходят фильтры  
  Оппортунити/час: 40,000+ (из которых MAX_OPEN_POSITIONS=3 ограничивает одновременные)
  Примерно: 15-25 сделок/час при MAX_OPEN_POSITIONS=3
  Avg net edge: ~0.5-0.7% (при издержках 0.5%)
```

---

## ПАРАМЕТРЫ ДЛЯ A/B ТЕСТИРОВАНИЯ (опционально)

Если хочется проверить без полного переключения — запустить два процесса:

```python
# process_A: main.py с текущими настройками (baseline)
# process_B: main.py с новыми настройками

# В config/main_config.py добавить флаг:
AB_TEST_MODE = "B"  # "A" = текущие, "B" = оптимизированные

# И в opportunity_config.py:
if AB_TEST_MODE == "B":
    OPPORTUNITY_CONFIG['MIN_GROSS_SPREAD'] = 0.6
    OPPORTUNITY_CONFIG['MIN_NET_EDGE'] = 0.12
    # ...
```

Сравнить win_rate, avg_pnl, total_trades через 24 часа.
