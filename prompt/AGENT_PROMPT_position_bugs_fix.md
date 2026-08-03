# AGENT_PROMPT: КРИТИЧЕСКИЕ БАГИ — ПОТЕРЯ ПОЗИЦИЙ И HIGH-SPREAD

**Дата:** 2026-06-11  
**Источник:** Реальные логи Telegram  
**Статус системы:** Win rate 85-100%, НО критический баг потери позиций

---

## ДИАГНОЗ ПО ЛОГАМ

### Хронология бага с PLAYUSDT:

```
09:00:06 — ✅ Позиция открыта PLAYUSDT (спред 1.566%)
09:00:XX — 📊 Статистика: PnL +4.88 (было +23.00! = -18.12 USD просадка)
             ← позиция НЕ закрыта, висит открытой
             ← Win Rate упал с 100% до 83.3% (6 из 6 прибыльных, но total=6)
             ← значит первая PLAYUSDT считается как убыточная/открытая сделка

09:18:44 — ✅ Позиция открыта PLAYUSDT СНОВА (спред 1.633%)
             ← ALLOW_MULTIPLE_POSITIONS_PER_SYMBOL=False нарушено!
             ← Значит первая позиция пропала из position_manager.positions

09:18:45 — ✅ Позиция закрыта (0.9 сек, reversal)
```

### Вывод:
1. Позиция PLAYUSDT 09:00 открылась → **выпала из position_manager** (баг)
2. Она продолжает тянуть реальный баланс в минус (открыта на бирже)
3. Risk manager не видит её → разрешает открыть вторую PLAYUSDT
4. Итого: одна "призрачная" позиция висит вечно

### Причина "Спред выход: 0.000%" у WLDUSDT:
Collapse стратегия закрыла позицию при `current_spread <= collapse_threshold (0.1%)`.
Спред стал 0% — это либо реальное схлопывание (нормально), либо
потеря данных одной из бирж (нулевой bid или ask). Нужно различать эти случаи.

---

## БАГ #1 (P0 — КРИТИЧНО): Позиции выпадают из position_manager

### Где ломается

**Симптом:** Позиция открыта на бирже, но `position_manager.positions` её не содержит.
Риск: позиция висит вечно, деньги заморожены.

**Наиболее вероятные места поломки:**

**Вариант A:** Исключение во время `register_position()` после `execute_arbitrage()`:
```python
# main.py — текущий код:
success, pair_id = await self.trading_engine.execute_arbitrage(opp, position_size, strategy_name)

if success:
    trade = self.trading_engine.get_position(pair_id)
    self.position_manager.register_position(trade)      # ← если здесь Exception
    self.risk_manager.register_position(pair_id, ...)   # ← позиция открыта но не зарегистрирована
```

**Вариант B:** Гонка между `monitor_positions()` и регистрацией:
```python
# monitor_positions вызывается параллельно через asyncio.create_task()
# Если monitor успевает вызвать close_position до register_position → позиция теряется
monitor_task = asyncio.create_task(self.position_manager.monitor_positions(market_data))
# ... анализ ...
await self.trading_engine.execute_arbitrage(...)  # позиция открыта
await monitor_task  # monitor уже завершился, но мог захватить неполное состояние
```

**Вариант C:** Exception в `position_manager.close_position()` прерывает удаление:
```python
# Если calculate_net_pnl() или telegram.send() бросает исключение
# del self.positions[pair_id] не выполняется → позиция "зависает"
# При следующем мониторинге снова пытается закрыть → цикл
```

### Исправления

**Файл: `main.py`** — обернуть регистрацию в try/except с компенсацией:

```python
# БЫЛО:
if success:
    trade = self.trading_engine.get_position(pair_id)
    self.position_manager.register_position(trade)
    self.risk_manager.register_position(pair_id, opp.symbol, opp.exchange_long, opp.exchange_short)

# СТАЛО:
if success:
    try:
        trade = self.trading_engine.get_position(pair_id)
        if trade is None:
            # trading_engine потерял позицию — критическая ошибка
            logger.error(f"CRITICAL: trade {pair_id} not found after execute_arbitrage")
            await self.telegram.log_error("Lost Trade", f"{opp.symbol} {pair_id[:8]}: position opened but not tracked")
        else:
            self.position_manager.register_position(trade)
            self.risk_manager.register_position(
                pair_id, opp.symbol, opp.exchange_long, opp.exchange_short
            )
            logger.info(f"Position registered: {opp.symbol} {pair_id[:8]}")
    except Exception as e:
        logger.error(f"CRITICAL: failed to register position {pair_id}: {e}")
        await self.telegram.log_error(
            "Registration Failed",
            f"{opp.symbol}: position OPEN on exchange but NOT tracked! Manual close required. pair_id={pair_id}"
        )
        # Аварийная попытка закрыть позицию
        try:
            await self.trading_engine.close_position(pair_id)
        except Exception as close_e:
            logger.error(f"Emergency close also failed: {close_e}")
```

**Файл: `main.py`** — убрать параллельность monitor и execute:

```python
# БЫЛО (гонка возможна):
monitor_task = asyncio.create_task(self.position_manager.monitor_positions(market_data))
opportunities = await asyncio.get_event_loop().run_in_executor(...)
await monitor_task
# ... дальше execute_arbitrage ...

# СТАЛО (сначала мониторинг, потом открытие):
# Сначала закрываем что нужно закрыть
await self.position_manager.monitor_positions(market_data)

# Только потом анализируем и открываем новые
opportunities = await asyncio.get_event_loop().run_in_executor(...)
# ... execute_arbitrage ...
```

**Файл: `core/managers/position_manager.py`** — защита close_position от частичного выполнения:

```python
async def close_position(self, pair_id: str, market_data: Dict, reason: str):
    """Закрытие позиции — атомарная операция"""
    if pair_id not in self.positions:
        return
    
    trade = self.positions[pair_id]
    
    # ВАЖНО: сначала удаляем из positions, ПОТОМ делаем всё остальное
    # Это предотвращает повторное закрытие при следующем мониторинге
    del self.positions[pair_id]
    
    logger.info(f"Closing position {pair_id[:8]} ({trade.symbol}), reason: {reason}")
    
    try:
        success = await self.trading_engine.close_position(pair_id)
        
        if not success:
            logger.error(f"trading_engine.close_position failed for {pair_id}")
            # Позиция уже удалена из менеджера но может висеть на бирже
            await self.telegram.log_error(
                "Close Failed",
                f"{trade.symbol}: close order failed! Check exchange manually. pair_id={pair_id}"
            )
        
        # Расчёт PnL (в try отдельно — не должен влиять на закрытие)
        try:
            await self._calculate_and_log_pnl(trade, market_data, reason, success)
        except Exception as e:
            logger.error(f"PnL calculation failed for {pair_id}: {e}")
            # Позиция уже закрыта, это некритично
    
    except Exception as e:
        logger.error(f"CRITICAL: close_position exception for {pair_id}: {e}")
        await self.telegram.log_error(
            "Close Exception",
            f"{trade.symbol}: exception during close! pair_id={pair_id}, error={e}"
        )

async def _calculate_and_log_pnl(self, trade, market_data, reason, success):
    """Вынесенный расчёт PnL — ошибка здесь не влияет на закрытие позиции"""
    from core.analyzers.pnl_calculator import calculate_net_pnl
    
    long_data = market_data.get(trade.exchange_long, {}).get(trade.symbol)
    short_data = market_data.get(trade.exchange_short, {}).get(trade.symbol)
    
    if long_data and short_data:
        pnl_result = calculate_net_pnl(
            entry_price_long=trade.entry_price_long,
            entry_price_short=trade.entry_price_short,
            current_price_long=long_data.bid,
            current_price_short=short_data.ask,
            position_size_usd=trade.position_size_usd,
            leverage=5,
            fee_rate=0.0005,
        )
        pnl_usd = pnl_result['net_usd']
        current_spread = (short_data.bid - long_data.ask) / long_data.ask * 100
    else:
        pnl_usd = 0.0
        current_spread = 0.0
        logger.warning(f"No market data for PnL calc: {trade.symbol}")
    
    trade.close_spread = current_spread
    trade.pnl = pnl_usd
    trade.status = 'closed'
    trade.close_time = datetime.now()
    
    hold_time = (trade.close_time - trade.open_time).total_seconds()
    self.total_pnl += pnl_usd
    self.closed_positions.append(trade)
    
    if self.risk_manager:
        self.risk_manager.update_balance(pnl_usd)
        self.risk_manager.unregister_position(trade.pair_id)
        if pnl_usd < 0:
            self.risk_manager.register_loss(
                trade.symbol, trade.exchange_long, trade.exchange_short
            )
    
    emoji = "✅" if pnl_usd > 0 else "❌"
    print(f"\n   {emoji} {trade.symbol} PnL: {pnl_usd:+.2f} USD | {hold_time:.1f}s | {reason}")
    
    await self.telegram.log_position_closed(
        symbol=trade.symbol,
        spread_open=trade.entry_spread,
        spread_close=current_spread,
        pnl=pnl_usd,
        hold_time=hold_time,
        reason=reason
    )
```

---

## БАГ #2 (P0): "Призрачные" позиции — добавить watchdog

**Файл: `main.py`** — добавить периодическую сверку позиций:

```python
# Добавить в ArbitrageSystem:

async def watchdog_positions(self):
    """
    Периодически проверяет что все зарегистрированные позиции
    реально существуют в trading_engine.
    Запускать каждые 60 секунд.
    """
    while self.running:
        await asyncio.sleep(60)
        
        pm_positions = set(self.position_manager.positions.keys())
        te_positions = set(self.trading_engine.open_positions.keys())
        rm_positions = set(self.risk_manager.open_positions.keys())
        
        # Позиции которые есть в trading_engine но нет в position_manager
        orphaned = te_positions - pm_positions
        if orphaned:
            for pair_id in orphaned:
                trade = self.trading_engine.open_positions[pair_id]
                logger.error(f"WATCHDOG: orphaned position {pair_id[:8]} ({trade.symbol})")
                await self.telegram.log_error(
                    "Watchdog: Orphaned Position",
                    f"{trade.symbol} pair_id={pair_id[:8]}: in trading_engine but not in position_manager. Closing."
                )
                # Аварийное закрытие
                await self.trading_engine.close_position(pair_id)
        
        # Позиции в position_manager но не в trading_engine
        ghost = pm_positions - te_positions
        if ghost:
            for pair_id in ghost:
                trade = self.position_manager.positions[pair_id]
                logger.error(f"WATCHDOG: ghost position {pair_id[:8]} ({trade.symbol})")
                await self.telegram.log_error(
                    "Watchdog: Ghost Position",
                    f"{trade.symbol}: in position_manager but not in trading_engine. Removing."
                )
                del self.position_manager.positions[pair_id]
                self.risk_manager.unregister_position(pair_id)
        
        # Расхождение risk_manager
        rm_ghost = rm_positions - pm_positions
        for pair_id in rm_ghost:
            self.risk_manager.unregister_position(pair_id)

# В методе run() — запустить watchdog:
async def run(self, duration_seconds=None):
    self.running = True
    try:
        await self.run_market_data_collection()
        await asyncio.sleep(10)
        
        # Запускаем watchdog параллельно
        watchdog_task = asyncio.create_task(self.watchdog_positions())
        
        if duration_seconds:
            try:
                await asyncio.wait_for(self.run_arbitrage_monitoring(), timeout=duration_seconds)
            except asyncio.TimeoutError:
                pass
        else:
            await self.run_arbitrage_monitoring()
    finally:
        self.running = False
        watchdog_task.cancel()
        await self.cleanup()
```

---

## БАГ #3 (P1): Спред 0.000% при закрытии — различать схлопывание и потерю данных

**Файл: `strategies/spread_collapse_strategy.py`**

```python
def calculate_current_spread(self, trade, market_data):
    long_data = market_data.get(trade.exchange_long, {}).get(trade.symbol)
    short_data = market_data.get(trade.exchange_short, {}).get(trade.symbol)
    
    if not long_data or not short_data:
        return None
    
    # НОВАЯ ПРОВЕРКА: нулевые цены = потеря данных, не спред
    if long_data.bid <= 0 or long_data.ask <= 0:
        logger.warning(f"Zero prices on {trade.exchange_long} for {trade.symbol}")
        return None
    if short_data.bid <= 0 or short_data.ask <= 0:
        logger.warning(f"Zero prices on {trade.exchange_short} for {trade.symbol}")
        return None
    
    # НОВАЯ ПРОВЕРКА: данные свежие?
    from datetime import datetime
    now_ms = datetime.now().timestamp() * 1000
    age_long = now_ms - long_data.timestamp.timestamp() * 1000
    age_short = now_ms - short_data.timestamp.timestamp() * 1000
    
    if age_long > 3000 or age_short > 3000:
        # Данные старше 3 секунд — не закрываем позицию по ним
        logger.warning(f"Stale data for close: {trade.symbol}, ages: {age_long:.0f}/{age_short:.0f}ms")
        return None  # None = не принимать решение о закрытии
    
    current_spread = (short_data.bid - long_data.ask) / long_data.ask * 100
    return current_spread

def should_close(self, trade, market_data):
    current_spread = self.calculate_current_spread(trade, market_data)
    
    # None = нет валидных данных = не закрываем
    if current_spread is None:
        return False, ""
    
    # ... остальная логика ...
```

---

## БАГ #4 (P1): HIGH-SPREAD не работает — диагностика и исправление

### Почему high-spread не работает

По логам видно только regular сделки (WLDUSDT 1.555%, PLAYUSDT 1.566%).
High-spread (>4%) не открывается. Причин несколько:

**Причина A: `opp.effective_spread` всегда 0**

В `ArbitrageEngine._check_pair_batch()`:
```python
opp = ArbitragePair(
    ...
    effective_spread=spread1 - abs(funding_diff_1) * 100  # ← Проверить эту строку
)
```

Если `funding_diff_1` уже в процентах (0.01 = 1%), то умножение на 100 даёт 1.0,
и `effective_spread = spread1 - 1.0` — что для спреда 1.5% даёт 0.5%, ниже порога 4%.

**Проверить:**
```python
# Добавить временный print в _check_pair_batch():
if spread1 > 3.0:
    print(f"DEBUG HIGH: {symbol} spread={spread1:.3f}%, funding_diff={funding_diff_1:.6f}, "
          f"effective={spread1 - abs(funding_diff_1) * 100:.3f}%, "
          f"threshold={config.HIGH_SPREAD_MIN_PCT}")
```

**Причина B: `MAX_SPREAD_OPEN` отрезает high-spread в opportunity_analyzer**

```python
# В opportunity_analyzer._evaluate():
if gross_spread > self.MAX_GROSS_SPREAD:  # = 2.5% или 3.0%
    return False, "Gross spread suspicious..."
```

High-spread возможности (4%+) отклоняются как "аномалии" ещё до попадания
в high-spread ветку кода! Нужно разделить потоки.

**Причина C: Порядок проверки в main.py**

```python
# В run_arbitrage_monitoring():
for opp in opportunities:
    if config.HIGH_SPREAD_MODE and opp.effective_spread >= config.HIGH_SPREAD_MIN_PCT:
        high_spread_opps.append(opp)
    else:
        regular_opps.append(opp)
```

Если `effective_spread` вычислен неправильно (см. Причину A),
все спреды попадают в `regular_opps` и отклоняются там.

### Исправления для HIGH-SPREAD

**Файл: `config/main_config.py`** — добавить явный флаг обхода opportunity_analyzer:

```python
# HIGH-SPREAD возможности НЕ должны проходить через стандартный OpportunityAnalyzer
# у них свой HighSpreadAnalyzer с другими порогами
HIGH_SPREAD_BYPASS_OPPORTUNITY_ANALYZER = True
```

**Файл: `main.py`** — исправить логику разделения потоков:

```python
# БЫЛО — проверяет effective_spread который может быть 0:
if config.HIGH_SPREAD_MODE and opp.effective_spread >= config.HIGH_SPREAD_MIN_PCT:
    high_spread_opps.append(opp)

# СТАЛО — проверяет gross spread (надёжнее):
if config.HIGH_SPREAD_MODE and opp.spread >= config.HIGH_SPREAD_MIN_PCT:
    high_spread_opps.append(opp)
else:
    regular_opps.append(opp)
```

**Файл: `core/engines/arbitrage_engine.py`** — исправить расчёт effective_spread:

```python
# В _check_pair_batch(), при создании ArbitragePair:

# Сначала разобраться с единицами funding_diff:
# Если funding_rate приходит как 0.0001 (= 0.01%), то:
funding_diff_1 = data_short.funding_rate - data_long.funding_rate
# funding_diff_1 = 0.0002 (в долях)
# В % = 0.02%
# effective_spread = spread_pct - funding_diff_in_pct
effective_spread_1 = spread1 - abs(funding_diff_1) * 100  # 0.0002 * 100 = 0.02%

# Добавить проверку что effective_spread разумный:
if effective_spread_1 < 0:
    effective_spread_1 = 0.0

opp = ArbitragePair(
    ...
    funding_diff=funding_diff_1,      # В долях (как приходит от биржи)
    effective_spread=effective_spread_1,  # В процентах
)
```

**Файл: `main.py`** — добавить диагностический вывод для high-spread:

```python
# В начале цикла, перед разделением:
if iteration % 1000 == 0:  # Каждые ~100 секунд
    hs_candidates = [o for o in opportunities if o.spread >= config.HIGH_SPREAD_MIN_PCT]
    print(f"[DIAG] HS candidates: {len(hs_candidates)}, "
          f"HS mode: {config.HIGH_SPREAD_MODE}, "
          f"threshold: {config.HIGH_SPREAD_MIN_PCT}%")
    for c in hs_candidates[:3]:
        print(f"       {c.symbol}: gross={c.spread:.3f}%, "
              f"effective={c.effective_spread:.3f}%, "
              f"funding={c.funding_diff:.6f}")
```

---

## ИТОГОВЫЙ ЧЕКЛИСТ

### Исправить немедленно (P0):

```
[ ] 1. position_manager.close_position() — удалять из self.positions ПЕРВЫМ действием
[ ] 2. main.py — убрать asyncio.create_task для monitor, сделать await
[ ] 3. main.py — try/except вокруг register_position с аварийным закрытием
[ ] 4. Добавить watchdog_positions() запускаемый каждые 60 секунд
```

### Исправить срочно (P1):

```
[ ] 5. spread_collapse_strategy.py — проверка нулевых цен и stale data
[ ] 6. main.py — разделение по opp.spread, а не opp.effective_spread
[ ] 7. arbitrage_engine.py — диагностический print для high-spread кандидатов
[ ] 8. Проверить единицы funding_diff (доли или проценты)
```

### Проверка после исправлений:

```bash
# Запустить demo на 30 минут
python main.py

# В логах должно быть:
# ✅ НЕТ повторного открытия одного символа
# ✅ Watchdog не находит orphaned/ghost позиций
# ✅ [DIAG] показывает high-spread кандидатов
# ✅ High-spread позиции реально открываются
# ✅ Telegram уведомляет об ошибках регистрации (если они есть)
```

---

## ОЖИДАЕМЫЙ РЕЗУЛЬТАТ

```
До исправлений:
  - Иногда позиции зависают → убытки -18 USD за раз
  - High-spread не работает → упущено ~30% потенциальных сделок
  - Win rate 85% но реальный PnL нестабилен

После исправлений:
  - Каждая открытая позиция гарантированно закрывается
  - Watchdog ловит любые расхождения за 60 секунд
  - High-spread добавит 1-3 сделки в день с большим net edge
  - Win rate 85-100% стабильно без неожиданных просадок
```
