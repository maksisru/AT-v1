# DIFF: Ключевые изменения кода

## 1. config/main_config.py

```diff
 # === СТРАТЕГИЯ ОТКРЫТИЯ (REST-оптимизировано) ===

-OPEN_THRESHOLD = 1.0  # Минимальный спред для открытия
-MAX_SPREAD_OPEN = 3.0  # Максимальный спред (выше — вероятно ловушка)
-MIN_NET_EDGE = 0.3     # Минимальная чистая прибыль после всех издержек
+# ОПТИМИЗАЦИЯ на основе реальных данных (spreads_20260608_*.csv):
+# 58.4% возможностей в диапазоне 0.5-1.0%, median net_edge=0.396%
+OPEN_THRESHOLD = 0.6  # Было 1.0 — снижено: 58% рынка было недоступно
+MAX_SPREAD_OPEN = 2.5  # Было 3.0 — снижено: выше 2.5% только 7.5% данных
+MIN_NET_EDGE = 0.12    # Было 0.3 — снижено: реальный median net_edge = 0.396%
```

```diff
 # === ЧЕРНЫЙ СПИСОК СИМВОЛОВ ===
 BLACKLISTED_SYMBOLS = [
     "EDGEUSDT",
 ]

+# === WHITELIST ВЫСОКОЧАСТОТНЫХ СИМВОЛОВ ===
+# Символы с доказанной активностью и стабильными спредами
+HIGH_FREQUENCY_SYMBOLS = [
+    "ESPORTSUSDT",   # 74.6% потока данных
+    "ALLOUSDT",      # 5.9% потока
+    "PIPPINUSDT",    # 4.3% потока
+    "LABUSDT",       # 4.0% потока
+    "CLOUSDT",       # 2.6% потока
+]
+
+# Для HF символов — более агрессивные пороги
+HF_MIN_NET_EDGE = 0.10           # Чуть ниже общего (0.12%)
+HF_MAX_BID_ASK_SPREAD = 0.20     # Выше общего (0.15%)
```

```diff
 # === РИСК-МЕНЕДЖМЕНТ ===
 COOLDOWN_AFTER_LOSS_SEC = 300
 MIN_LIQUIDITY_MULTIPLIER = 1.5

+# FIX: funding_diff порог (в долях, не процентах)
+MAX_FUNDING_DIFF = 0.015  # 1.5% — фильтрует только топ 3% аномальных
```

---

## 2. config/opportunity_config.py

```diff
 OPPORTUNITY_CONFIG = {
-    'MIN_GROSS_SPREAD': OPEN_THRESHOLD,   # = 1.0%
-    'MIN_NET_EDGE': MIN_NET_EDGE,         # = 0.3%
-    'MAX_GROSS_SPREAD': MAX_SPREAD_OPEN,  # = 3.0%
+    'MIN_GROSS_SPREAD': OPEN_THRESHOLD,   # = 0.6% (оптимизировано)
+    'MIN_NET_EDGE': MIN_NET_EDGE,         # = 0.12% (оптимизировано)
+    'MAX_GROSS_SPREAD': MAX_SPREAD_OPEN,  # = 2.5% (оптимизировано)
     
-    'MAX_BID_ASK_SPREAD_PER_LEG': 0.12,
-    'MAX_DATA_AGE_MS': 1000,
+    'MAX_BID_ASK_SPREAD_PER_LEG': 0.15,  # Было 0.12 — для HF символов
+    'MAX_DATA_AGE_MS': 800,              # Было 500 — WebSocket latency
     
-    'TAKER_FEE_PCT': 0.05,
-    'SLIPPAGE_PCT': 0.02,
+    'TAKER_FEE_PCT': 0.05,               # Без изменений
+    'SLIPPAGE_PCT': 0.05,                # Было 0.02 — реальность REST
+    'REST_EXECUTION_BUFFER': 0.10,       # Новый параметр
```

---

## 3. core/managers/risk_manager.py

```diff
 from config.main_config import (
     MAX_POSITION_SIZE, 
     MAX_OPEN_POSITIONS, 
     MAX_SPREAD_OPEN,
     POSITION_SIZE_FRACTION,
     MAX_POSITIONS_PER_EXCHANGE,
     ALLOW_MULTIPLE_POSITIONS_PER_SYMBOL,
-    COOLDOWN_AFTER_LOSS_SEC
+    COOLDOWN_AFTER_LOSS_SEC,
+    MAX_FUNDING_DIFF
 )
```

```diff
-        # 4. Проверка funding rate
-        if abs(opportunity.funding_diff) > 0.01:  # 1%
-            return {"approved": False, "reason": "Funding rate diff too high (>1%)"}
+        # 4. Проверка funding rate (FIX: правильный порог)
+        if abs(opportunity.funding_diff) > MAX_FUNDING_DIFF:
+            return {
+                "approved": False, 
+                "reason": f"Funding rate diff too high ({abs(opportunity.funding_diff)*100:.3f}% > {MAX_FUNDING_DIFF*100:.1f}%)"
+            }
```

---

## 4. core/analyzers/opportunity_analyzer.py

```diff
 from core.models import ArbitragePair
+from config.main_config import HIGH_FREQUENCY_SYMBOLS, HF_MIN_NET_EDGE, HF_MAX_BID_ASK_SPREAD
```

```diff
     def __init__(self, config: dict = None):
         self.config = config or {}
         
         self.MIN_GROSS_SPREAD = self.config.get('MIN_GROSS_SPREAD', 1.0)
         self.MIN_NET_EDGE = self.config.get('MIN_NET_EDGE', 0.3)
         self.MAX_GROSS_SPREAD = self.config.get('MAX_GROSS_SPREAD', 3.0)
         self.MAX_BID_ASK_SPREAD_PER_LEG = self.config.get('MAX_BID_ASK_SPREAD_PER_LEG', 0.15)
         self.MAX_DATA_AGE_MS = self.config.get('MAX_DATA_AGE_MS', 500)
         
+        # ИЗМЕНЕНИЕ #4: Адаптивные пороги для высокочастотных символов
+        self.HF_MIN_NET_EDGE = HF_MIN_NET_EDGE
+        self.HF_MAX_BID_ASK = HF_MAX_BID_ASK_SPREAD
```

```diff
-        # 8. Approval logic
+        # 8. Approval logic (передаём symbol для адаптивных порогов)
         approved, reason = self._evaluate(
             gross_spread_pct,
             net_edge_pct,
             bid_ask_long,
             bid_ask_short,
-            data_age_ms
+            data_age_ms,
+            symbol=opportunity.symbol
         )
```

```diff
     def _evaluate(
         self,
         gross_spread: float,
         net_edge: float,
         bid_ask_long: float,
         bid_ask_short: float,
-        data_age_ms: float
+        data_age_ms: float,
+        symbol: str = ""
     ) -> tuple[bool, str]:
         """Оценка возможности: approve/reject + причина"""
         
+        # ИЗМЕНЕНИЕ #4: Адаптивные пороги для HF символов
+        is_hf = symbol in HIGH_FREQUENCY_SYMBOLS
+        min_net_edge = self.HF_MIN_NET_EDGE if is_hf else self.MIN_NET_EDGE
+        max_bid_ask = self.HF_MAX_BID_ASK if is_hf else self.MAX_BID_ASK_SPREAD_PER_LEG
+        
-        # Check 5: Bid-ask spread too wide on long leg
-        if bid_ask_long > self.MAX_BID_ASK_SPREAD_PER_LEG:
+        # Check 5: Bid-ask spread too wide on long leg (адаптивный порог)
+        if bid_ask_long > max_bid_ask:
-            return False, f"Bid-ask too wide on long leg ({bid_ask_long:.3f}% > {self.MAX_BID_ASK_SPREAD_PER_LEG}%)"
+            return False, f"Bid-ask too wide on long leg ({bid_ask_long:.3f}% > {max_bid_ask}%)"
         
-        # Check 6: Bid-ask spread too wide on short leg
-        if bid_ask_short > self.MAX_BID_ASK_SPREAD_PER_LEG:
+        # Check 6: Bid-ask spread too wide on short leg (адаптивный порог)
+        if bid_ask_short > max_bid_ask:
-            return False, f"Bid-ask too wide on short leg ({bid_ask_short:.3f}% > {self.MAX_BID_ASK_SPREAD_PER_LEG}%)"
+            return False, f"Bid-ask too wide on short leg ({bid_ask_short:.3f}% > {max_bid_ask}%)"
         
-        # Check 7: Net edge insufficient
-        if net_edge < self.MIN_NET_EDGE:
+        # Check 7: Net edge insufficient (адаптивный порог)
+        if net_edge < min_net_edge:
-            return False, f"Net edge insufficient ({net_edge:.3f}% < {self.MIN_NET_EDGE}%)"
+            return False, f"Net edge insufficient ({net_edge:.3f}% < {min_net_edge}%)"
         
-        return True, f"Approved: net edge {net_edge:.3f}%"
+        suffix = " [HF]" if is_hf else ""
+        return True, f"Approved: net edge {net_edge:.3f}%{suffix}"
```

---

## Новые файлы

### test_threshold_optimization.py
Автоматический тестовый скрипт, проверяет:
- Конфигурация обновлена правильно
- Баг funding_diff исправлен
- OpportunityAnalyzer использует новые пороги
- Адаптивные пороги работают для HF символов

### THRESHOLD_OPTIMIZATION_REPORT.md
Полный отчет о проведённой оптимизации с обоснованиями

### OPTIMIZATION_QUICK_CHECK.md
Краткая сводка для быстрой проверки результатов
