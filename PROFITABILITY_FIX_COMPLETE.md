# ИСПРАВЛЕНИЯ ДЛЯ УВЕЛИЧЕНИЯ WIN RATE: ВЫПОЛНЕНО

**Дата:** 2026-06-10 23:13  
**Источник:** prompt/AGENT_PROMPT_profitability_fix.md  
**Проблема:** Win rate 27.3%, PnL -6.65 USD за 24 часа

---

## ВЫПОЛНЕННЫЕ КРИТИЧНЫЕ ИСПРАВЛЕНИЯ (P0-P1)

### ✅ ИСПРАВЛЕНИЕ #1: Переключение на SpreadCollapse стратегию

**Файл:** `config/main_config.py`

**Изменения:**
```python
# БЫЛО:
STRATEGY_TYPE = 'rest_optimized'
REST_TAKE_PROFIT_PCT = 0.4
REST_STOP_LOSS_PCT = 0.5
REST_MAX_HOLD_TIME = 180

# СТАЛО:
STRATEGY_TYPE = 'collapse'
COLLAPSE_THRESHOLD = 0.3
MIN_PROFIT_PCT = 0.25
MAX_HOLD_TIME_COLLAPSE = 600  # 10 минут
COLLAPSE_STOP_LOSS_EXPANSION = 1.5
```

**Обоснование:** RestOptimizedStrategy с фиксированными TP=0.4% закрывала позиции слишком рано при среднем спреде 3.061%. SpreadCollapse держит позицию до реального схлопывания.

---

### ✅ ИСПРАВЛЕНИЕ #2: Детектор тренда спредов

**Файлы:** 
- `core/engines/arbitrage_engine.py`
- `core/models.py`
- `core/engines/trading_engine.py`

**Добавленная функциональность:**

1. **ArbitrageEngine**: Трекинг последних 5 значений спреда для каждой пары
2. **Линейная регрессия** определяет тренд: `expanding`, `stable`, `collapsing`
3. **Фильтр**: Позиции НЕ открываются если `trend == 'collapsing'`
4. **Модели**: Добавлены поля `spread_trend` (ArbitragePair) и `spread_trend_at_entry` (Trade)

**Код:**
```python
def _get_spread_trend(self, pair_key: str, current_spread: float) -> str:
    # Линейная регрессия по последним 5 измерениям
    slope = numerator / denominator
    
    if slope > 0.05:   # Растёт
        return 'expanding'
    elif slope < -0.05:  # Падает
        return 'collapsing'
    else:
        return 'stable'
```

**Обоснование:** Вход на collapsing спред = вход на пике → убыток. Это главная причина WR=27%.

**Ожидаемый эффект:** Фильтрация ~40-50% входов в момент разворота спреда.

---

### ✅ ИСПРАВЛЕНИЕ #3: Asymmetric TP/SL для collapse стратегии

**Файл:** `strategies/spread_collapse_strategy.py`

**Изменения:**

**БЫЛО:**
```python
target_profit = trade.entry_spread * 0.7  # 70% от entry (нереально для REST)
timeout = 3600s  # 1 час
```

**СТАЛО:**
```python
# Поэтапное снятие прибыли
partial_target = min(trade.entry_spread * 0.30, 1.0)  # 30% или max 1%

# Ужесточённые стоп-лоссы:
1. Hard stop: spread > entry + 1.0%
2. Time stop: 300s без прогресса (PnL < 0.05%)
3. Max hold: 600s (10 минут)
```

**Обоснование:** 
- TP=70% от 3% спреда = 2.1% profit — нереалистично для REST
- TP=30% от 3% = 0.9% — достижимо
- Ограничение убытка: расширение спреда на 1% → выход
- Не держим мёртвые позиции >5 минут

**Ожидаемый эффект:** Уменьшение среднего убытка на сделку, рост win rate.

---

## ОЖИДАЕМЫЕ РЕЗУЛЬТАТЫ

### До исправлений:
```
Win rate:       27.3%
Сделок:         22 за сутки
PnL:            -6.65 USD
Avg spread:     3.061%
```

### После исправлений (прогноз):
```
Win rate:       50-60%      (+100-120%)
Сделок:         15-25       (меньше, но качественных)
PnL:            +5 до +15 USD
Причина роста:  
  - Фильтр collapsing трендов: +15-20% WR
  - SpreadCollapse стратегия: +10-15% WR
  - Asymmetric TP/SL:         +5-10% WR
```

---

## ПРОВЕРКА

### 1. Проверка конфигурации:
```bash
py -c "
from config.main_config import STRATEGY_TYPE, COLLAPSE_THRESHOLD, MIN_PROFIT_PCT
assert STRATEGY_TYPE == 'collapse', f'Expected collapse, got {STRATEGY_TYPE}'
assert COLLAPSE_THRESHOLD == 0.3, f'Expected 0.3, got {COLLAPSE_THRESHOLD}'
assert MIN_PROFIT_PCT == 0.25, f'Expected 0.25, got {MIN_PROFIT_PCT}'
print('✅ SpreadCollapse стратегия активна')
"
```

### 2. Проверка тренд-детектора:
```bash
py -c "
from core.engines.arbitrage_engine import ArbitrageEngine
engine = ArbitrageEngine()
assert hasattr(engine, 'spread_trend_history'), 'Trend detector не добавлен'
assert hasattr(engine, '_get_spread_trend'), 'Метод _get_spread_trend отсутствует'
print('✅ Тренд-детектор спредов установлен')
"
```

### 3. Проверка моделей:
```bash
py -c "
from core.models import ArbitragePair, Trade
from datetime import datetime
opp = ArbitragePair('a','b','c',1,0,1,1,datetime.now())
assert hasattr(opp, 'spread_trend'), 'ArbitragePair.spread_trend отсутствует'
print('✅ Модели обновлены')
"
```

### 4. Demo тест (2 часа):
```bash
py main.py
```

**Признаки успешной работы:**
- ✅ Логи показывают `trend='expanding'` или `'stable'` (не `'collapsing'`)
- ✅ Закрытия по причине "Partial target" (не "Time stop")
- ✅ Меньше "Hard stop" закрытий
- ✅ Win rate >40% после 15+ сделок

---

## НЕ РЕАЛИЗОВАННЫЕ ИСПРАВЛЕНИЯ (можно добавить позже)

### P1: ИСПРАВЛЕНИЕ #4 — Проверка gross с учётом двойных bid-ask
**Файл:** `core/analyzers/opportunity_analyzer.py`  
**Эффект:** +5-10% WR  
**Сложность:** Низкая

### P2: ИСПРАВЛЕНИЕ #5 — Trade logger в CSV
**Файл:** `scripts/trade_logger.py` (новый)  
**Эффект:** Диагностика  
**Сложность:** Низкая

### P2: ИСПРАВЛЕНИЕ #6 — Динамический размер позиции
**Файл:** `core/managers/risk_manager.py`  
**Эффект:** +5% капитала  
**Сложность:** Средняя

### P2: ИСПРАВЛЕНИЕ #7 — Circuit breaker
**Файл:** `core/managers/risk_manager.py`  
**Эффект:** Защита от серий убытков  
**Сложность:** Низкая

---

## КЛЮЧЕВЫЕ ИЗМЕНЕНИЯ В ЛОГИКЕ

### До:
```
1. Система видит спред 3%
2. Открывает позицию (без проверки тренда)
3. Спред уже падает → 2.5% → 2.0% → убыток
4. RestOptimized закрывает через 180s с -0.3%
```

### После:
```
1. Система видит спред 3%
2. Проверяет тренд: если collapsing → SKIP
3. Открывает только если expanding/stable
4. Collapse стратегия держит до partial_target (0.9%)
5. Hard stop при расширении >1% защищает от больших убытков
```

---

## ДОПОЛНИТЕЛЬНАЯ ДИАГНОСТИКА

После 24 часов работы проверить:

### 1. Распределение по трендам:
```python
# В логах должно быть примерно:
expanding: 30-40% входов (лучшие)
stable:    50-60% входов (нормальные)
collapsing: 0% входов (отфильтрованы)
```

### 2. Причины закрытия:
```python
# Ожидаемое распределение:
Partial target:  40-50% (прибыль)
Hard stop:       20-30% (защита)
Time stop:       15-20% (нейтрально)
Collapse:        10-15% (идеально)
Max hold:        5-10%  (мусор)
```

### 3. Win rate по трендам:
```python
# Ожидается:
expanding: 70-80% WR (лучшие входы)
stable:    50-60% WR (нормальные)
unknown:   30-40% WR (первые итерации)
```

---

**Статус:** ✅ Критичные исправления #1-#3 применены  
**Цель:** Win rate 50-60% (против 27.3%)  
**Следующий шаг:** Demo тест 2+ часа, анализ результатов
