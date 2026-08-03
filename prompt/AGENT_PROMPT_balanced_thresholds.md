# AGENT_PROMPT: СБАЛАНСИРОВАННАЯ СТРАТЕГИЯ ПОРОГОВ

**Дата:** 2026-06-09  
**Версия:** v2.0 — Balanced Strategy

---

## КОНТЕКСТ И ПРОБЛЕМА

После агрессивной оптимизации порогов от 2026-06-08 система столкнулась с проблемами:
- **Win rate упал с 57% до 11%**
- Система берёт слишком много низкокачественных возможностей
- Реальные издержки REST торговли превышают теоретический net edge

### Что было изменено (и что сломало результат):

| Параметр | Старое (WR=57%) | Агрессивное (WR=11%) | Диагноз |
|---|---|---|---|
| OPEN_THRESHOLD | 1.0% | 0.6% | ❌ Слишком низкий — система берёт мусорные спреды |
| MIN_NET_EDGE | 0.3% | 0.12% | ❌ Слишком низкий — нет запаса на проскальзывание |
| MAX_SPREAD_OPEN | 3.0% | 2.5% | ⚠️ Некритично |
| MAX_FUNDING_DIFF | 0.01 (баг) | 0.015 | ✅ Правильно, оставить |
| SLIPPAGE_PCT | 0.02% | 0.05% | ✅ Более реалистично, оставить |
| MAX_DATA_AGE_MS | 500 | 800 | ✅ Оставить |

### Корневая причина WR=11%:

**Реальные издержки REST торговли:**
```
TAKER_FEE:    0.05% × 4 сделки = 0.20%
SLIPPAGE:     0.05% × 4 сделки = 0.20%
REST_BUFFER:  0.10% (задержка исполнения)
──────────────────────────────────────
ИТОГО:        0.50%
```

При `MIN_NET_EDGE=0.12%` система одобряет сделки, где теоретический net edge = 0.12%, но **реальные издержки 0.50% гарантируют убыток**.

Дополнительно: при `OPEN_THRESHOLD=0.6%` большинство спредов существуют доли секунды и **схлопываются до исполнения REST ордера** (задержка 150-300ms).

---

## ЗАДАЧА: РЕАЛИЗОВАТЬ СБАЛАНСИРОВАННУЮ СТРАТЕГИЮ

**Цель:** восстановить win rate до 50-60%+ при увеличении числа сделок vs. старой конфигурации.

**Принцип:** не возвращаться полностью к старым порогам, а найти золотую середину между консервативностью (WR=57%, мало сделок) и агрессивностью (WR=11%, много мусора).

---

## ИЗМЕНЕНИЯ: 5 ПРИОРИТЕТНЫХ ШАГОВ

### ИЗМЕНЕНИЕ #1 (P0 — КРИТИЧНО): Скорректировать OPEN_THRESHOLD и MIN_NET_EDGE

**Файл:** `config/main_config.py`

**Логика расчёта:**

```
Суммарные издержки при REST торговле:
  TAKER_FEE:    0.05% × 4 сделки = 0.20%
  SLIPPAGE:     0.05% × 4 сделки = 0.20%
  REST_BUFFER:  0.10% (задержка исполнения)
  ──────────────────────────────────────
  ИТОГО:        0.50%

Для WR=57% при старых настройках нужен запас сверх издержек.
Старый MIN_NET_EDGE=0.3% означал: gross spread ≥ 1.0% + 0.3% net = 1.3% минимальный реальный вход.

Новый баланс:
  OPEN_THRESHOLD = 0.8%   (компромисс между 0.6% и 1.0%)
  MIN_NET_EDGE   = 0.25%  (достаточный запас: издержки 0.50% + edge 0.25%)
```

**Применить:**
```python
# config/main_config.py

# БЫЛО (агрессивное, WR=11%):
OPEN_THRESHOLD = 0.6
MAX_SPREAD_OPEN = 2.5
MIN_NET_EDGE = 0.12

# СТАЛО (сбалансированное, целевой WR=50-60%):
OPEN_THRESHOLD = 0.8   # Компромисс: отсекает мусор, но берёт 0.8-1.0% спреды
MAX_SPREAD_OPEN = 3.0  # Вернуть к 3.0%: 2.5-3.0% зона хороших возможностей
MIN_NET_EDGE = 0.25    # Достаточный запас над издержками (0.50% + 0.25% = 0.75% gross min)
```

**Проверка логики:**
- При `OPEN_THRESHOLD=0.8%` и суммарных издержках 0.50% → net edge = 0.30% (выше MIN_NET_EDGE=0.25%) ✅
- При `OPEN_THRESHOLD=0.6%` и издержках 0.50% → net edge = 0.10% (ниже 0.25%) → ОТКЛОНЯЕТСЯ ✅
- Это означает: система фактически не будет брать спреды ниже 0.75-0.80% gross

---

### ИЗМЕНЕНИЕ #2 (P0 — КРИТИЧНО): Пересмотреть HF_MIN_NET_EDGE

**Файл:** `config/main_config.py`

**Проблема:** `HF_MIN_NET_EDGE=0.10%` для ESPORTSUSDT ещё хуже чем общий 0.12%. При издержках 0.50% это гарантированный убыток на каждой сделке.

```python
# БЫЛО:
HF_MIN_NET_EDGE = 0.10        # Слишком низко — убыточно
HF_MAX_BID_ASK_SPREAD = 0.20  # Оставить

# СТАЛО:
HF_MIN_NET_EDGE = 0.20        # Чуть ниже общего 0.25%, но над разумным минимумом
HF_MAX_BID_ASK_SPREAD = 0.20  # Без изменений
```

**Обоснование:** ESPORTSUSDT даёт много сделок, но при net_edge=0.10% каждая убыточна. Лучше меньше сделок, но прибыльных.

---

### ИЗМЕНЕНИЕ #3 (P1): Ужесточить проверку актуальности спреда перед открытием

**Файл:** `main.py`

**Проблема:** При `OPEN_THRESHOLD=0.6%` и REST задержке 150-300ms спред 0.6-0.8% часто схлопывается до исполнения. Система открывает позицию когда возможности уже нет.

**Текущий код в `run_arbitrage_monitoring()`:**
```python
# Текущая проверка:
if fresh_spread < opp.spread * 0.9:  # схлопнулся на 10%
    continue
```

**Новая более строгая проверка:**
```python
# СТАЛО: более строгий контроль актуальности
if long_fresh and short_fresh:
    fresh_spread = (short_fresh.bid - long_fresh.ask) / long_fresh.ask * 100

    # Проверка 1: спред не схлопнулся более чем на 15%
    if fresh_spread < opp.spread * 0.85:
        print(f"      ⚠️ Spread degraded: {opp.spread:.3f}% → {fresh_spread:.3f}%, skip")
        continue

    # Проверка 2: свежий спред сам по себе выше OPEN_THRESHOLD
    if fresh_spread < config.OPEN_THRESHOLD:
        print(f"      ⚠️ Fresh spread {fresh_spread:.3f}% below threshold, skip")
        continue

    # Проверка 3: пересчёт net edge на свежих данных
    fresh_net_edge = fresh_spread - 0.50  # суммарные издержки
    if fresh_net_edge < config.MIN_NET_EDGE:
        print(f"      ⚠️ Fresh net edge {fresh_net_edge:.3f}% insufficient, skip")
        continue
```

**Применить эту логику в ОБОИХ местах** в `run_arbitrage_monitoring()`:
1. Для regular opportunities (строка ~345)
2. Для high-spread opportunities (строка ~278)

---

### ИЗМЕНЕНИЕ #4 (P1): Добавить MIN_SPREAD_PERSISTENCE — фильтр устойчивости спреда

**Файл:** `core/engines/arbitrage_engine.py`

**Проблема:** Система реагирует на каждый тик. Спред 0.8% может существовать 50ms и исчезнуть. REST ордер занимает 150-300ms — позиция открывается когда спреда уже нет.

**Решение:** Считать возможность валидной только если спред держится N последовательных итераций анализа.

**Добавить в `ArbitrageEngine`:**
```python
class ArbitrageEngine:
    def __init__(self, max_workers: int = 4):
        # ... существующий код ...
        
        # Счётчик устойчивости спредов: {pair_key: consecutive_count}
        self.spread_persistence: Dict[str, int] = {}
        self.spread_persistence_lock = threading.Lock()
    
    def _get_pair_key(self, ex_long: str, ex_short: str, symbol: str) -> str:
        return f"{ex_long}|{ex_short}|{symbol}"
    
    def _check_spread_persistence(self, pair_key: str, spread: float, 
                                   threshold: float, min_count: int = 2) -> bool:
        """
        Возвращает True только если спред выше threshold
        наблюдается min_count итераций подряд.
        
        min_count=2 при интервале 100ms = спред держится 200ms+
        Это фильтрует мгновенные флуктуации.
        """
        with self.spread_persistence_lock:
            if spread >= threshold:
                self.spread_persistence[pair_key] = self.spread_persistence.get(pair_key, 0) + 1
                return self.spread_persistence[pair_key] >= min_count
            else:
                # Спред упал — сбрасываем счётчик
                self.spread_persistence[pair_key] = 0
                return False
```

**Использование в `_check_pair_batch()`:**
```python
# В _check_pair_batch(), после расчёта spread1:
if spread1 > threshold:
    pair_key = self._get_pair_key(ex_long, ex_short, symbol)
    
    # Проверяем устойчивость спреда (минимум 2 итерации подряд)
    MIN_PERSISTENCE = 2  # можно вынести в config
    if not self._check_spread_persistence(pair_key, spread1, threshold, MIN_PERSISTENCE):
        continue  # Спред только появился — ждём подтверждения
    
    # Дальше — обычная логика создания ArbitragePair
    opp = ArbitragePair(...)
    opportunities.append(opp)
```

**Добавить в `config/main_config.py`:**
```python
# Минимальное число подряд итераций для подтверждения спреда
MIN_SPREAD_PERSISTENCE = 2  # при 100ms интервале = 200ms устойчивости
```

**Эффект:** Отфильтровывает ~40-60% "мусорных" одноитерационных спредов, которые исчезают до исполнения REST ордера.

---

### ИЗМЕНЕНИЕ #5 (P2): Подтвердить MAX_POSITIONS_PER_SYMBOL для ESPORTSUSDT

**Файл:** `config/main_config.py` и `core/managers/risk_manager.py`

**Проблема:** ESPORTSUSDT генерирует 74.6% потока. При сниженных порогах система может открывать 3 позиции одновременно по одному символу на разных парах бирж — это концентрированный риск.

**Проверить в `config/main_config.py`:**
```python
# Должно быть:
ALLOW_MULTIPLE_POSITIONS_PER_SYMBOL = False  # ← проверить что False
```

**Убедиться в `core/managers/risk_manager.py` в `check_opportunity()`:**
```python
# Проверка должна уже быть:
for pos in self.open_positions.values():
    if pos['symbol'] == opportunity.symbol:
        return {
            "approved": False,
            "reason": f"Symbol {opportunity.symbol} already has open position (risk concentration)"
        }
```

Если проверки нет — добавить.

---

## ИТОГОВАЯ ТАБЛИЦА: ЧТО МЕНЯЕМ

| Параметр | WR=57% (старое) | WR=11% (агрессивное) | Сбалансированное | Действие |
|---|---|---|---|---|
| OPEN_THRESHOLD | 1.0% | 0.6% | **0.8%** | ✏️ Изменить |
| MAX_SPREAD_OPEN | 3.0% | 2.5% | **3.0%** | ✏️ Вернуть |
| MIN_NET_EDGE | 0.3% | 0.12% | **0.25%** | ✏️ Изменить |
| MAX_FUNDING_DIFF | 0.01 (баг) | 0.015 | **0.015** | ✅ Оставить |
| SLIPPAGE_PCT | 0.02% | 0.05% | **0.05%** | ✅ Оставить |
| REST_EXECUTION_BUFFER | нет | 0.10% | **0.10%** | ✅ Оставить |
| MAX_DATA_AGE_MS | 500ms | 800ms | **800ms** | ✅ Оставить |
| HF_MIN_NET_EDGE | нет | 0.10% | **0.20%** | ✏️ Изменить |
| MIN_SPREAD_PERSISTENCE | нет | нет | **2 итерации** | ➕ Добавить |
| Fresh spread check | 90% | 90% | **85% + доп. фильтры** | ✏️ Ужесточить |

---

## ПОРЯДОК ВЫПОЛНЕНИЯ

```
1. config/main_config.py              — изменения #1, #2, #4 (константы)
2. config/opportunity_config.py       — синхронизация с новыми порогами
3. main.py                            — изменение #3 (fresh spread проверка)
4. core/engines/arbitrage_engine.py   — изменение #4 (persistence filter)
5. core/managers/risk_manager.py      — изменение #5 (проверить блокировку)
```


---

## ПРОВЕРКА ПОСЛЕ ИЗМЕНЕНИЙ

### 1. Автоматическая проверка констант

```bash
py -c "
from config.main_config import OPEN_THRESHOLD, MIN_NET_EDGE, MAX_SPREAD_OPEN, HF_MIN_NET_EDGE
assert OPEN_THRESHOLD == 0.8,  f'OPEN_THRESHOLD={OPEN_THRESHOLD}, expected 0.8'
assert MIN_NET_EDGE == 0.25,   f'MIN_NET_EDGE={MIN_NET_EDGE}, expected 0.25'
assert MAX_SPREAD_OPEN == 3.0, f'MAX_SPREAD_OPEN={MAX_SPREAD_OPEN}, expected 3.0'
assert HF_MIN_NET_EDGE == 0.20, f'HF_MIN_NET_EDGE={HF_MIN_NET_EDGE}, expected 0.20'
print('✅ OK — все пороги выставлены правильно')
"
```

### 2. Demo режим (тестирование 30+ минут)

```bash
py main.py
```

**Что проверять в логах:**

✅ **Признаки правильной работы:**
- Одобрено 20-40% возможностей (не 60-70% как при агрессивных порогах)
- Спреды 0.6-0.79% систематически ОТКЛОНЯЮТСЯ (причина: "Net edge insufficient")
- Спреды ≥0.80% рассматриваются
- Появляется сообщение "Spread degraded" или "Fresh spread below threshold" — фильтр работает
- Win rate в demo приближается к 50%+ (за 30+ минут наблюдения)

❌ **Признаки проблем:**
- Одобряется >60% — пороги всё ещё слишком низкие
- Win rate <30% после 20+ сделок — нужно ещё поднять MIN_NET_EDGE до 0.30%

### 3. Анализ устойчивости спредов

Добавить временное логирование в `arbitrage_engine.py` после проверки persistence:

```python
# Временно для отладки:
if self._check_spread_persistence(pair_key, spread1, threshold, MIN_PERSISTENCE):
    print(f"  ✓ Spread PERSISTENT: {symbol} {spread1:.2f}% (count={self.spread_persistence[pair_key]})")
else:
    print(f"  ⏳ Spread PENDING: {symbol} {spread1:.2f}% (count={self.spread_persistence.get(pair_key, 0)})")
```

Должно показывать, что ~40-60% спредов отсеиваются на этапе persistence.

---

## FALLBACK: ЕСЛИ WIN RATE ОСТАЁТСЯ НИЗКИМ

Если после этих изменений win rate не восстановится до 50%+ за 30+ минут наблюдения, выполнить **консервативный откат**:

```python
# FALLBACK конфигурация (гарантированно консервативный):
OPEN_THRESHOLD = 1.0           # Полный откат к старому
MIN_NET_EDGE = 0.30            # Полный откат к старому
MAX_SPREAD_OPEN = 3.0          # Оставить
MAX_FUNDING_DIFF = 0.015       # Исправленный баг — оставить
MIN_SPREAD_PERSISTENCE = 2     # Новое — оставить
HF_MIN_NET_EDGE = 0.25         # Немного ниже общего
```

Это вернёт систему к проверенному win rate 57%, но с исправленными багами.

---

## ОЖИДАЕМЫЕ РЕЗУЛЬТАТЫ

**Сбалансированная конфигурация (целевые показатели):**

```
Win rate:           50-60%     (было 11% агрессивное, 57% старое)
Сделок в час:       8-15       (было 5-10 старое, 15-25 агрессивное)
Avg net edge:       0.25-0.40% (реальный, после издержек)
Avg gross spread:   0.80-1.50%
Открытий в день:    ~100-200   (против ~400 агрессивного)

Отфильтровано по persistence:  40-60% кандидатов
Отфильтровано по fresh_spread: 15-25% кандидатов
```

*Условия: $100 позиция, 5x плечо*

---

## ВАЖНО: ЧТО НЕ ТРОГАТЬ

✅ Сохранить без изменений:
- `MAX_FUNDING_DIFF = 0.015` — исправление бага, не трогать
- `SLIPPAGE_PCT = 0.05` — реалистичное значение для REST, не трогать
- `REST_EXECUTION_BUFFER = 0.10` — правильный буфер, не трогать
- `HIGH_FREQUENCY_SYMBOLS` список — оставить, он не влияет на win rate напрямую
- `MAX_DATA_AGE_MS = 800` — оставить
- Весь код `high_spread_classifier`, `high_spread_analyzer` — не трогать
- `BLACKLISTED_SYMBOLS` — не менять

---

## КРАТКИЙ ЧЕКЛИСТ ДЛЯ АГЕНТА

```
[ ] 1. config/main_config.py
    [ ] OPEN_THRESHOLD = 0.8
    [ ] MIN_NET_EDGE = 0.25
    [ ] MAX_SPREAD_OPEN = 3.0
    [ ] HF_MIN_NET_EDGE = 0.20
    [ ] MIN_SPREAD_PERSISTENCE = 2

[ ] 2. config/opportunity_config.py
    [ ] Синхронизировать пороги с main_config

[ ] 3. main.py
    [ ] Ужесточить fresh_spread проверку (85% + 3 доп. условия)
    [ ] Применить в ДВУХ местах (regular + high-spread)

[ ] 4. core/engines/arbitrage_engine.py
    [ ] Добавить spread_persistence механизм
    [ ] Интегрировать в _check_pair_batch()

[ ] 5. core/managers/risk_manager.py
    [ ] Проверить ALLOW_MULTIPLE_POSITIONS_PER_SYMBOL = False

[ ] 6. Тестирование
    [ ] Автопроверка констант
    [ ] Demo 30+ минут
    [ ] Win rate >50%
```

---

## ТЕХНИЧЕСКИЕ ДЕТАЛИ

### Расчёт persistence при 100ms интервале

```
MIN_SPREAD_PERSISTENCE = 2
Интервал анализа = 100ms (performance_config.ANALYSIS_INTERVAL)

Минимальное время жизни спреда = 2 × 100ms = 200ms

REST задержка на открытие 2 позиций = 150-300ms

→ Спред должен существовать минимум 200ms
→ Это фильтрует мгновенные флуктуации <200ms
→ К моменту исполнения (250ms avg) спред скорее всего ещё жив
```

### Математика net edge

```
Gross spread = 0.8%
Издержки:
  - TAKER_FEE: 0.05% × 4 = 0.20%
  - SLIPPAGE:  0.05% × 4 = 0.20%
  - REST_BUF:  0.10%
  ──────────────────────
  ИТОГО:       0.50%

Net edge = 0.8% - 0.5% = 0.30%

Проверка:
  0.30% >= MIN_NET_EDGE (0.25%)  ✅ ОДОБРЕНО

При gross=0.7%:
  Net = 0.7% - 0.5% = 0.20%
  0.20% < 0.25%  ❌ ОТКЛОНЕНО
```

---

**КОНЕЦ ПРОМПТА**
