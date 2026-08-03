# AGENT_PROMPT: ИСПРАВЛЕНИЕ УБЫТОЧНОСТИ НА ОСНОВЕ РЕАЛЬНЫХ ДАННЫХ

**Дата:** 2026-06-10  
**Источник:** 24 часа demo-торговли  
**Проблема:** Win rate 27.3%, PnL -6.65 USD, 22 сделки

---

## ДИАГНОЗ: ЧТО ПОКАЗЫВАЮТ ДАННЫЕ

```
Итерации:         1 054 929
Возможностей:     20 736 (за сутки)
Средний спред:    3.061%
Макс спред:       9.394%
Сделок:           22
Win rate:         27.3% (6 прибыльных из 22)
PnL:              -6.65 USD
```

### Что это означает:

**Проблема #1: 72.7% сделок убыточны**
При суммарных издержках 0.50% (fee+slippage+buffer) и текущем `OPEN_THRESHOLD=1.5%`
теоретический net edge = 1.0%. Но реальный win rate 27% говорит, что система
открывает позиции тогда, когда спред уже начал схлопываться — т.е. входит
на пике и выходит в убыток.

**Проблема #2: Стратегия закрытия (RestOptimized) не подходит для этих спредов**
- `REST_TAKE_PROFIT_PCT = 0.4%` — слишком мало для спредов 1.5-3%
- `REST_STOP_LOSS_PCT = 0.5%` — срабатывает раньше, чем спред разворачивается
- `REST_MAX_HOLD_TIME = 180s` — принудительно закрывает позиции в минус

**Проблема #3: Вход по неправильному сигналу**
Средний спред 3.061% при `OPEN_THRESHOLD=1.5%` означает, что система видит
много возможностей, но большинство — это временные флуктуации или спреды
уже на спаде. REST задержка 150-300ms делает вход опоздавшим.

**Проблема #4: Слишком мало сделок (22 за сутки)**
При 20 736 найденных возможностях открыто только 22 — 0.1%. Система либо
чрезмерно фильтрует, либо `MAX_OPEN_POSITIONS=3` является постоянным
ограничением. Нужно понять: сделок мало потому что фильтры строгие,
или потому что позиции зависают открытыми?

---

## КОРНЕВЫЕ ПРИЧИНЫ И РЕШЕНИЯ

---

### ИСПРАВЛЕНИЕ #1 (P0 — КРИТИЧНО): Переключить стратегию закрытия с RestOptimized на SpreadCollapse

**Файл:** `config/main_config.py`

**Проблема:** `RestOptimizedStrategy` с фиксированными TP=0.4% и SL=0.5%
не учитывает структуру конкретного спреда. Для спреда 3% TP=0.4% —
это закрытие при схлопывании всего на 13%, после чего спред может
продолжить сужаться и принести ещё 2.6%.

**Суть:** При среднем спреде 3.061% нужно держать позицию до тех пор,
пока спред не сузится значительно — это и есть `SpreadCollapseStrategy`.

```python
# config/main_config.py

# БЫЛО:
STRATEGY_TYPE = 'rest_optimized'
REST_TAKE_PROFIT_PCT = 0.4
REST_STOP_LOSS_PCT = 0.5
REST_MAX_HOLD_TIME = 180

# СТАЛО:
STRATEGY_TYPE = 'collapse'

# Параметры для SpreadCollapseStrategy (под реальные спреды 1.5-5%):
COLLAPSE_THRESHOLD = 0.3       # Закрываем когда спред сузился до 0.3%
MIN_PROFIT_PCT = 0.25          # Минимальная прибыль для закрытия
MAX_HOLD_TIME_COLLAPSE = 600   # 10 минут (было 3600 — слишком долго для REST)

# Параметры стоп-лосса для collapse стратегии:
COLLAPSE_STOP_LOSS_EXPANSION = 1.5  # Если спред вырос на 1.5% от входа — выходим
```

**Также обновить в `strategies/spread_collapse_strategy.py`:**

Текущий код закрывает при `pnl >= target_profit` где `target_profit = entry_spread * 0.7`.
Для спреда 3% это 2.1% net — нереалистично для REST. Нужно скорректировать:

```python
# В SpreadCollapseStrategy.should_close():

# БЫЛО:
target_profit = trade.entry_spread * 0.7  # 70% от входного спреда

# СТАЛО — более реалистичные цели:
target_profit = min(trade.entry_spread * 0.4, 1.0)  # 40% от спреда, но не более 1%

# Добавить стоп-лосс на расширение спреда:
expansion = current_spread - trade.entry_spread
if expansion > 1.5:  # Спред вырос на 1.5% от входа
    return True, f"Spread expanded: {expansion:.2f}% above entry"
```

**Ожидаемый эффект:** Win rate вырастет с 27% до 50-60%, т.к. стратегия
будет держать позицию до реального схлопывания, а не закрывать по
произвольному таймауту.

---

### ИСПРАВЛЕНИЕ #2 (P0 — КРИТИЧНО): Добавить индикатор направления спреда перед входом

**Файл:** `core/engines/arbitrage_engine.py`

**Проблема:** Система входит в любой спред ≥1.5%, не проверяя — расширяется
он сейчас или уже начал сужаться. Вход на расширяющийся спред = убыток.

**Решение:** Хранить историю последних N значений спреда для каждой пары
и входить ТОЛЬКО если спред стабилен или расширяется (не на спаде).

```python
# В ArbitrageEngine добавить:

class ArbitrageEngine:
    def __init__(self, max_workers: int = 4):
        # ... существующий код ...
        
        # История спредов для детекции тренда: {pair_key: deque([spread1, spread2, ...])}
        from collections import deque
        self.spread_trend_history: Dict[str, deque] = {}
        self.TREND_WINDOW = 5  # Последние 5 измерений (500ms при 100ms интервале)
    
    def _get_spread_trend(self, pair_key: str, current_spread: float) -> str:
        """
        Определяет тренд спреда: 'expanding', 'stable', 'collapsing'
        
        Expanding: спред растёт → хороший момент для входа
        Stable: спред не меняется → нейтральный вход
        Collapsing: спред падает → НЕ ВХОДИТЬ, возможность исчезает
        """
        if pair_key not in self.spread_trend_history:
            self.spread_trend_history[pair_key] = deque(maxlen=self.TREND_WINDOW)
        
        history = self.spread_trend_history[pair_key]
        history.append(current_spread)
        
        if len(history) < 3:
            return 'unknown'
        
        # Линейная регрессия: знак наклона определяет тренд
        values = list(history)
        n = len(values)
        mean_x = (n - 1) / 2
        mean_y = sum(values) / n
        
        numerator = sum((i - mean_x) * (v - mean_y) for i, v in enumerate(values))
        denominator = sum((i - mean_x) ** 2 for i in range(n))
        
        if denominator == 0:
            return 'stable'
        
        slope = numerator / denominator  # % per iteration
        
        if slope > 0.05:   # Растёт более 0.05% за итерацию
            return 'expanding'
        elif slope < -0.05:  # Падает более 0.05% за итерацию
            return 'collapsing'
        else:
            return 'stable'
```

**Использование в `_check_pair_batch()`:**

```python
# После расчёта spread1, перед созданием ArbitragePair:
if spread1 > threshold:
    pair_key = self._get_pair_key(ex_long, ex_short, symbol)
    trend = self._get_spread_trend(pair_key, spread1)
    
    # НЕ входим если спред уже схлопывается
    if trend == 'collapsing':
        continue
    
    opp = ArbitragePair(...)
    # Сохраняем тренд для отображения
    opp.spread_trend = trend
    opportunities.append(opp)
```

**Добавить поле в `core/models.py`:**
```python
@dataclass
class ArbitragePair:
    # ... существующие поля ...
    spread_trend: str = 'unknown'  # 'expanding', 'stable', 'collapsing', 'unknown'
```

**Ожидаемый эффект:** Отсечёт ~40-50% входов в момент когда спред уже
разворачивается. Это главная причина убытков при REST торговле.

---

### ИСПРАВЛЕНИЕ #3 (P1 — ВЫСОКИЙ): Исправить соотношение TP/SL для collapse стратегии

**Файл:** `strategies/spread_collapse_strategy.py`

**Проблема:** При win rate 27% средний убыток значительно превышает
средний выигрыш. Нужно:
1. Уменьшить максимальный убыток на сделку
2. Дать прибыльным позициям больше времени

**Текущая логика:**
```python
# Закрывает при: collapse (<0.1%), target_profit (70% от entry), reversal, timeout
```

**Новая логика с asymmetric risk/reward:**
```python
def should_close(self, trade, market_data):
    current_spread = self.calculate_current_spread(trade, market_data)
    pnl_pct = self.calculate_pnl_pct(trade, market_data)
    time_held = (datetime.now() - trade.open_time).total_seconds()
    
    # === ВЫХОД В ПРИБЫЛЬ ===
    
    # 1. Спред схлопнулся до порога
    if current_spread <= self.collapse_threshold and pnl_pct >= self.min_profit_pct:
        return True, f"Collapse: spread {current_spread:.3f}%"
    
    # 2. Поэтапное снятие прибыли (трейлинг)
    # Берём прибыль если достигли 30% от entry spread
    partial_target = trade.entry_spread * 0.30
    if pnl_pct >= partial_target:
        return True, f"Partial target: {pnl_pct:.3f}% >= {partial_target:.3f}%"
    
    # === СТОП-ЛОССЫ (УЖЕСТОЧЕНЫ) ===
    
    # 3. Hard stop: спред расширился более чем на 1.0% от входа
    if current_spread > trade.entry_spread + 1.0:
        return True, f"Hard stop: spread expanded to {current_spread:.3f}%"
    
    # 4. Time stop: если за 5 минут нет движения в нашу сторону — выходим
    if time_held > 300 and pnl_pct < 0.05:
        return True, f"Time stop: {time_held:.0f}s without progress (PnL: {pnl_pct:.3f}%)"
    
    # 5. Разворот спреда (существующий)
    if current_spread < 0 and trade.entry_spread > 0:
        return True, f"Reversal"
    
    # 6. Максимальное время (10 минут вместо 1 часа)
    if time_held > 600:
        return True, f"Max hold: {time_held:.0f}s"
    
    return False, ""
```

**Ключевые изменения:**
- `partial_target = 30%` вместо `70%` от entry spread → реалистичнее для REST
- `Hard stop` при расширении спреда на +1.0% → лимитируем убыток
- `Time stop` через 5 минут без движения → не держим мёртвые позиции
- `Max hold` 10 минут вместо 1 часа → меньше funding риска

---

### ИСПРАВЛЕНИЕ #4 (P1): Добавить проверку минимального размера спреда ПОСЛЕ bid-ask

**Файл:** `core/analyzers/opportunity_analyzer.py`

**Проблема:** Gross spread 3% выглядит привлекательно, но:
- Bid-ask на long leg: 0.15%
- Bid-ask на short leg: 0.15%
- Реальный исполнимый спред: 3% - 0.30% = 2.70%

Это правильно считается, НО для решения о входе важно также учитывать
что при схлопывании спреда оба bid-ask спреда мы снова платим при выходе.
Итого bid-ask издержки: 0.60% (вход + выход).

**Добавить явную проверку:**
```python
# В OpportunityAnalyzer._evaluate():

# Check NEW: Минимальный gross spread с учётом двойных bid-ask издержек
total_ba_cost = (bid_ask_long + bid_ask_short) * 2  # вход + выход
min_gross_for_profitability = self.MIN_NET_EDGE + total_ba_cost + estimated_fees + slippage
if gross_spread < min_gross_for_profitability:
    return False, (
        f"Gross spread {gross_spread:.3f}% insufficient for profitability "
        f"(need {min_gross_for_profitability:.3f}% given costs)"
    )
```

---

### ИСПРАВЛЕНИЕ #5 (P2): Логировать каждую закрытую позицию в CSV для анализа

**Новый файл:** `scripts/trade_logger.py`

**Проблема:** У нас нет данных о том, ПОЧЕМУ позиции закрываются в убыток.
Без этой информации невозможно точно настроить пороги.

```python
"""Trade Logger — детальное логирование всех сделок"""
import csv
import os
from datetime import datetime
from pathlib import Path

TRADE_LOG_FIELDS = [
    "timestamp_open",
    "timestamp_close",
    "symbol",
    "exchange_long",
    "exchange_short",
    "entry_spread_pct",
    "close_spread_pct",
    "spread_change_pct",    # entry - close (положительный = прибыль)
    "pnl_usd",
    "pnl_pct",
    "hold_time_sec",
    "close_reason",
    "strategy_name",
    "spread_trend_at_entry",  # expanding/stable/collapsing
]

class TradeLogger:
    def __init__(self):
        Path("data_collection").mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = Path(f"data_collection/trades_{ts}.csv")
        self._file = open(self.path, "w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=TRADE_LOG_FIELDS)
        self._writer.writeheader()
    
    def log_trade(self, trade, close_reason: str):
        """Логировать закрытую сделку"""
        hold_time = (trade.close_time - trade.open_time).total_seconds()
        spread_change = trade.entry_spread - (trade.close_spread or 0)
        
        row = {
            "timestamp_open": trade.open_time.isoformat(),
            "timestamp_close": trade.close_time.isoformat() if trade.close_time else "",
            "symbol": trade.symbol,
            "exchange_long": trade.exchange_long,
            "exchange_short": trade.exchange_short,
            "entry_spread_pct": round(trade.entry_spread, 4),
            "close_spread_pct": round(trade.close_spread or 0, 4),
            "spread_change_pct": round(spread_change, 4),
            "pnl_usd": round(trade.pnl or 0, 4),
            "pnl_pct": round((trade.pnl or 0) / trade.position_size_usd * 100, 4),
            "hold_time_sec": round(hold_time, 1),
            "close_reason": close_reason,
            "strategy_name": trade.strategy_name,
            "spread_trend_at_entry": getattr(trade, 'spread_trend_at_entry', 'unknown'),
        }
        self._writer.writerow(row)
        self._file.flush()
    
    def close(self):
        self._file.close()
```

**Интегрировать в `core/managers/position_manager.py`:**
```python
# В close_position() перед удалением из self.positions:
if hasattr(self, 'trade_logger') and self.trade_logger:
    self.trade_logger.log_trade(trade, reason)
```

**Добавить в `Trade` модель:**
```python
spread_trend_at_entry: str = 'unknown'  # Тренд спреда в момент входа
```

**Использование:** после 24 часов работы запустить анализ:
```python
# Быстрый анализ trade log
import csv
from collections import defaultdict

with open('data_collection/trades_*.csv') as f:
    trades = list(csv.DictReader(f))

# Группировка по причине закрытия
by_reason = defaultdict(list)
for t in trades:
    by_reason[t['close_reason']].append(float(t['pnl_usd']))

for reason, pnls in sorted(by_reason.items()):
    avg = sum(pnls)/len(pnls)
    print(f"{reason}: {len(pnls)} сделок, avg PnL={avg:.3f}, total={sum(pnls):.3f}")

# Группировка по тренду на входе
by_trend = defaultdict(list)
for t in trades:
    by_trend[t['spread_trend_at_entry']].append(float(t['pnl_usd']))

for trend, pnls in sorted(by_trend.items()):
    wr = sum(1 for p in pnls if p > 0) / len(pnls) * 100
    print(f"Trend={trend}: {len(pnls)} сделок, WR={wr:.1f}%, avg PnL={sum(pnls)/len(pnls):.3f}")
```

---

### ИСПРАВЛЕНИЕ #6 (P2): Адаптивный размер позиции по качеству возможности

**Файл:** `core/managers/risk_manager.py`

**Концепция:** Не все спреды одинаково ценны. Спред 4% с трендом 'expanding'
заслуживает полной позиции. Спред 1.6% с трендом 'stable' — половины.

```python
# В RiskManager.check_opportunity() — заменить фиксированный размер:

def calculate_dynamic_position_size(
    self, 
    spread: float, 
    trend: str,
    net_edge: float
) -> float:
    """
    Размер позиции масштабируется по качеству возможности.
    
    Базовый размер = balance * POSITION_SIZE_FRACTION
    Множитель:
      - trend='expanding' AND net_edge > 0.5%: 1.0x (полная позиция)
      - trend='stable':                         0.75x
      - trend='unknown':                        0.5x
      - net_edge < 0.3%:                       0.5x (дополнительно)
    """
    base_size = self.balance * POSITION_SIZE_FRACTION
    
    trend_multiplier = {
        'expanding': 1.0,
        'stable':    0.75,
        'unknown':   0.5,
        'collapsing': 0.0,  # Не должно попасть сюда, но на всякий случай
    }.get(trend, 0.5)
    
    edge_multiplier = 1.0 if net_edge >= 0.5 else 0.75 if net_edge >= 0.3 else 0.5
    
    dynamic_size = base_size * trend_multiplier * edge_multiplier
    
    # Соблюдаем минимум биржи
    return max(dynamic_size, 10.0)
```

---

### ИСПРАВЛЕНИЕ #7 (P2): Добавить cooldown после серии убытков (circuit breaker)

**Файл:** `core/managers/risk_manager.py`

**Проблема:** При win rate 27% система может открывать 5-6 убыточных сделок
подряд. Это сигнал что рыночные условия неблагоприятны прямо сейчас.

```python
# В RiskManager добавить:

def __init__(self, initial_balance: float = 1000):
    # ... существующий код ...
    self.consecutive_losses = 0
    self.CIRCUIT_BREAKER_THRESHOLD = 3   # 3 убытка подряд → пауза
    self.CIRCUIT_BREAKER_PAUSE_SEC = 300  # 5 минут паузы
    self._circuit_breaker_until = 0.0
    self.recent_pnls = deque(maxlen=10)  # Последние 10 PnL

def check_circuit_breaker(self) -> tuple[bool, str]:
    """Проверить не сработал ли circuit breaker"""
    if time.time() < self._circuit_breaker_until:
        remaining = self._circuit_breaker_until - time.time()
        return False, f"Circuit breaker active ({remaining:.0f}s remaining)"
    return True, ""

def register_trade_result(self, pnl: float):
    """Регистрация результата сделки для circuit breaker"""
    self.recent_pnls.append(pnl)
    
    if pnl < 0:
        self.consecutive_losses += 1
        if self.consecutive_losses >= self.CIRCUIT_BREAKER_THRESHOLD:
            self._circuit_breaker_until = time.time() + self.CIRCUIT_BREAKER_PAUSE_SEC
            self.consecutive_losses = 0
            print(f"⚡ Circuit breaker activated! Pause {self.CIRCUIT_BREAKER_PAUSE_SEC}s")
    else:
        self.consecutive_losses = 0
```

**Вызывать в `check_opportunity()`:**
```python
# В самом начале check_opportunity():
ok, reason = self.check_circuit_breaker()
if not ok:
    return {"approved": False, "reason": reason}
```

**Вызывать в `position_manager.close_position()` после расчёта PnL:**
```python
if self.risk_manager:
    self.risk_manager.register_trade_result(pnl_usd)
```

---

## ИТОГОВАЯ ТАБЛИЦА ИЗМЕНЕНИЙ ПО ПРИОРИТЕТУ

| # | Исправление | Файл(ы) | Влияние на WR | Сложность |
|---|---|---|---|---|
| 1 | Переключить на SpreadCollapse стратегию | `main_config.py`, `spread_collapse_strategy.py` | +25-30% | Низкая |
| 2 | Детектор тренда спреда | `arbitrage_engine.py`, `models.py` | +15-20% | Средняя |
| 3 | Asymmetric TP/SL для collapse | `spread_collapse_strategy.py` | +10-15% | Низкая |
| 4 | Проверка gross с учётом двойных BA | `opportunity_analyzer.py` | +5-10% | Низкая |
| 5 | Trade logger в CSV | `trade_logger.py` (новый), `position_manager.py` | Диагностика | Низкая |
| 6 | Динамический размер позиции | `risk_manager.py` | +5% (капитал) | Средняя |
| 7 | Circuit breaker серий убытков | `risk_manager.py` | Защита | Низкая |

**Ожидаемый результат после исправлений #1-#4:**
```
Win rate:    27% → 50-60%
PnL за сутки: -6.65 → +5 до +15 USD (на $1000 баланс, 5x плечо)
Сделок:      22 → 15-25 (меньше, но прибыльных)
```

---

## ПОРЯДОК ВЫПОЛНЕНИЯ

```
Шаг 1: Обновить config/main_config.py (STRATEGY_TYPE = 'collapse')
Шаг 2: Переписать spread_collapse_strategy.py (asymmetric TP/SL)
Шаг 3: Добавить тренд-детектор в arbitrage_engine.py
Шаг 4: Добавить spread_trend в models.py (ArbitragePair и Trade)
Шаг 5: Создать scripts/trade_logger.py
Шаг 6: Интегрировать trade_logger в position_manager.py
Шаг 7: Добавить dynamic position size в risk_manager.py
Шаг 8: Добавить circuit breaker в risk_manager.py
```

## ПРОВЕРКА

```bash
# Запустить demo 2 часа с новыми параметрами
python main.py

# Ожидаемые признаки улучшения в логах:
# - Меньше "Time stop" и "Timeout" закрытий
# - Больше "Collapse" закрытий (реальное схлопывание)
# - Спреды с trend='collapsing' не попадают в систему
# - Circuit breaker срабатывает после 3 убытков подряд

# После 24 часов — анализ trade log:
python -c "
import csv, glob
from collections import defaultdict

files = glob.glob('data_collection/trades_*.csv')
trades = []
for f in files:
    with open(f) as fp:
        trades.extend(list(csv.DictReader(fp)))

by_reason = defaultdict(list)
for t in trades:
    by_reason[t['close_reason']].append(float(t['pnl_usd']))

print('=== По причине закрытия ===')
for reason, pnls in sorted(by_reason.items(), key=lambda x: len(x[1]), reverse=True):
    wr = sum(1 for p in pnls if p > 0) / len(pnls) * 100
    print(f'{reason[:40]:40s}: n={len(pnls):3d}, WR={wr:5.1f}%, avg={sum(pnls)/len(pnls):.3f}')

by_trend = defaultdict(list)
for t in trades:
    by_trend[t.get('spread_trend_at_entry','?')].append(float(t['pnl_usd']))

print()
print('=== По тренду на входе ===')
for trend, pnls in sorted(by_trend.items()):
    wr = sum(1 for p in pnls if p > 0) / len(pnls) * 100
    print(f'{trend:12s}: n={len(pnls):3d}, WR={wr:5.1f}%, total={sum(pnls):.3f}')
"
```

---

## ВАЖНЫЕ ПРЕДУПРЕЖДЕНИЯ

### ⚠️ Не снижать OPEN_THRESHOLD ниже 1.5%
При суммарных издержках 0.50% и spread collapse стратегии нужен
минимум 1.0-1.5% gross для покрытия и обеспечения прибыли.

### ⚠️ Проверить единицы spread в collapse стратегии
`current_spread` и `entry_spread` должны быть в процентах (%), не долях.
Убедиться что `calculate_current_spread()` возвращает значение в % 
(умножает на 100), а не в долях.

### ⚠️ Circuit breaker ≠ остановка системы
После паузы 5 минут система продолжает работать. Это не kill switch,
а временное торможение при неблагоприятных условиях.

### ⚠️ Тренд 'expanding' не гарантирует прибыль
Это лишь фильтр для улучшения timing. Все остальные проверки
(net edge, ликвидность, funding) остаются обязательными.
