# Стратегия амплитудного арбитража

## Концепция

### Основная идея
Не ждём схлопывания спреда, а **многократно торгуем внутри колебаний** цен между биржами.

### Пример работы
```
Момент T0:
  Bybit:  BTC = 65,100 (лонг)
  Gate:   BTC = 65,200 (шорт)
  Спред = 100$

Момент T1 (через 2 сек):
  Bybit:  BTC = 65,110 (+10$) ✅
  Gate:   BTC = 65,193 (-7$)  ✅
  Амплитуда = +10$ - 7$ = +3$
  
→ ЗАКРЫВАЕМ → Фиксируем +3$ прибыль → ОТКРЫВАЕМ СНОВА
```

---

## Параметры стратегии

### 1. Размер позиции
```python
POSITION_SIZE_FRACTION = 0.1  # 1/10 от баланса
MAX_OPEN_POSITIONS = 3        # Максимум одновременно
```

### 2. Амплитудный анализ
```python
AMPLITUDE_WINDOW = 50         # Количество тиков для расчёта средней амплитуды
AMPLITUDE_THRESHOLD = 0.7     # Закрываем при 70% от средней макс амплитуды
MIN_AMPLITUDE = 5             # Минимальная прибыль в USD для закрытия
```

### 3. Условия открытия
```python
MIN_SPREAD_OPEN = 0.3         # Минимальный спред для входа (%)
MAX_SPREAD_OPEN = 2.0         # Максимальный спред (слишком большой = риск)
```

---

## Алгоритм

### Открытие позиции

```
1. Обнаружен спред > MIN_SPREAD_OPEN
2. Проверка: открытых позиций < MAX_OPEN_POSITIONS
3. Расчёт размера: position_size = balance * 0.1
4. Открытие LONG на бирже A, SHORT на бирже B
5. Сохранение:
   - entry_price_long
   - entry_price_short
   - entry_spread
   - entry_time
```

### Отслеживание амплитуды

Для каждой открытой позиции в реальном времени:

```python
# Текущий PnL на каждой стороне
pnl_long  = (current_price_A - entry_price_long) * position_size / entry_price_long
pnl_short = (entry_price_short - current_price_B) * position_size / entry_price_short

# Совокупная амплитуда
amplitude = pnl_long + pnl_short
```

### Закрытие позиции

```python
# История амплитуд за последние N тиков
amplitude_history = [amp1, amp2, amp3, ...]

# Средняя максимальная амплитуда
avg_max_amplitude = percentile(amplitude_history, 90)

# Условие закрытия
if amplitude >= avg_max_amplitude * AMPLITUDE_THRESHOLD:
    close_position()
    reopen_if_spread_still_exists()
```

---

## Защитные механизмы

### 1. Stop-Loss
```python
if amplitude < -MIN_AMPLITUDE * 2:  # Убыток больше 2x минимальной прибыли
    close_position()
    cooldown = 60  # Не открывать эту пару 60 сек
```

### 2. Timeout
```python
if time_since_open > 300:  # 5 минут держим позицию
    close_position()  # Принудительно закрываем
```

### 3. Spread reversal
```python
current_spread = calculate_current_spread()
if sign(current_spread) != sign(entry_spread):  # Спред развернулся
    close_position()  # Немедленно выходим
```

---

## Пример расчёта

### Исходные данные
- Баланс: 1000 USDT
- Position size: 1000 * 0.1 = 100 USDT
- Leverage: 10x → реальный объём = 1000 USDT

### Сценарий 1: Успешная амплитуда
```
Открытие:
  Long  @ 65,100 USDT (Bybit)
  Short @ 65,200 USDT (Gate)
  Спред = 100 USDT

Через 3 секунды:
  Long  @ 65,110 (+10 USDT, +0.015%)
  Short @ 65,193 (-7 USDT, +0.011%)
  
PnL:
  Long:  +0.015% * 1000 = +0.15 USDT
  Short: +0.011% * 1000 = +0.11 USDT
  Total: +0.26 USDT (чистая прибыль)

Средняя макс амплитуда: 0.35 USDT
Threshold (70%): 0.245 USDT
Текущая: 0.26 USDT → ЗАКРЫВАЕМ ✅
```

### Сценарий 2: Ранний выход
```
Через 1 секунду:
  Long  @ 65,102 (+2 USDT)
  Short @ 65,199 (-1 USDT)
  Amplitude: +0.03 USDT

0.03 < 0.245 → НЕ ЗАКРЫВАЕМ, ждём дальше
```

---

## Метрики для оптимизации

### Ключевые показатели
1. **Win rate** — % прибыльных закрытий
2. **Avg hold time** — среднее время удержания позиции
3. **Profit per trade** — средняя прибыль на сделку
4. **Daily turnover** — количество циклов открытие-закрытие в день

### Целевые значения
- Win rate: > 70%
- Avg hold time: 5-30 секунд
- Profit per trade: > 0.2 USDT
- Daily turnover: > 50 циклов

---

## Оптимизация параметров

Через backtesting подбираем:

1. **AMPLITUDE_THRESHOLD** (0.5 - 0.9)
   - Меньше → чаще закрываем → меньше прибыль, но выше win rate
   - Больше → реже закрываем → больше прибыль, но ниже win rate

2. **AMPLITUDE_WINDOW** (20 - 100)
   - Меньше → быстрее адаптация к новым условиям
   - Больше → стабильнее оценка, но медленнее реакция

3. **MIN_SPREAD_OPEN** (0.2% - 0.5%)
   - Меньше → больше возможностей, но меньше спред
   - Больше → меньше возможностей, но надёжнее

---

## Риски и ограничения

### 1. Комиссии
```
Maker: 0.02% × 2 = 0.04%
Taker: 0.05% × 2 = 0.10%

Минимальный спред для безубытка: 0.14%
```

### 2. Slippage
При рыночных ордерах может быть проскальзывание 0.01-0.03%

### 3. Funding rate
Если держим >8 часов, начисляется funding (обычно 0.01-0.1% каждые 8ч)

**Решение:** Держим позиции <5 минут → funding не влияет

---

## Итоговая формула закрытия

```python
def should_close_position(position, market_data, amplitude_history):
    # 1. Текущая амплитуда
    amplitude = calculate_amplitude(position, market_data)
    
    # 2. Средняя максимальная амплитуда
    avg_max = percentile(amplitude_history, 90)
    
    # 3. Порог закрытия
    threshold = avg_max * AMPLITUDE_THRESHOLD
    
    # 4. Условия закрытия
    if amplitude >= threshold and amplitude >= MIN_AMPLITUDE:
        return True  # ✅ Фиксируем прибыль
    
    if amplitude < -MIN_AMPLITUDE * 2:
        return True  # ❌ Stop-loss
    
    if time_since_open > 300:
        return True  # ⏱️ Timeout
    
    return False
```
