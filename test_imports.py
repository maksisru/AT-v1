"""Проверка импортов после исправления багов"""
import sys
from pathlib import Path

# Тест 1: Импорт core.models
try:
    from core.models import Trade, ArbitragePair
    print("[OK] core.models imports")
    
    # Проверка полей Trade
    trade_fields = list(Trade.__dataclass_fields__.keys())
    required_fields = ['strategy_name', 'leverage', 'hs_spread_type', 'hs_max_hold_min']
    missing = [f for f in required_fields if f not in trade_fields]
    if missing:
        print(f"[FAIL] Trade missing fields: {missing}")
    else:
        print("[OK] Trade has all required fields")
    
    # Проверка поля ArbitragePair.effective_spread
    if 'effective_spread' in ArbitragePair.__dataclass_fields__:
        print("[OK] ArbitragePair.effective_spread exists")
    else:
        print("[FAIL] ArbitragePair.effective_spread missing")
        
except Exception as e:
    print(f"[FAIL] core.models: {e}")

# Тест 2: Импорт OpportunityAnalyzer
try:
    from core.analyzers.opportunity_analyzer import OpportunityAnalyzer
    print("[OK] OpportunityAnalyzer imports")
    
    # Проверка что funding cost параметры есть
    analyzer = OpportunityAnalyzer()
    if hasattr(analyzer, 'MAX_HOLD_TIME_SEC') and hasattr(analyzer, 'FUNDING_PERIOD_SEC'):
        print("[OK] OpportunityAnalyzer has funding time parameters")
    else:
        print("[FAIL] OpportunityAnalyzer missing funding time parameters")
        
except Exception as e:
    print(f"[FAIL] OpportunityAnalyzer: {e}")

# Тест 3: Импорт RiskManager
try:
    from core.managers.risk_manager import RiskManager
    print("[OK] RiskManager imports")
    
    # Проверка методов cooldown
    rm = RiskManager()
    if hasattr(rm, 'register_loss') and hasattr(rm, 'is_in_cooldown'):
        print("[OK] RiskManager has cooldown methods")
    else:
        print("[FAIL] RiskManager missing cooldown methods")
        
except Exception as e:
    print(f"[FAIL] RiskManager: {e}")

# Тест 4: Проверка config
try:
    from config.main_config import (
        ALLOW_MULTIPLE_POSITIONS_PER_SYMBOL,
        COOLDOWN_AFTER_LOSS_SEC
    )
    print(f"[OK] Config parameters exist")
    print(f"    ALLOW_MULTIPLE_POSITIONS_PER_SYMBOL = {ALLOW_MULTIPLE_POSITIONS_PER_SYMBOL}")
    print(f"    COOLDOWN_AFTER_LOSS_SEC = {COOLDOWN_AFTER_LOSS_SEC}")
    
except Exception as e:
    print(f"[FAIL] Config: {e}")

# Тест 5: Импорт main.py
try:
    import main
    print("[OK] main.py imports successfully")
except Exception as e:
    print(f"[FAIL] main.py: {e}")

print("\n=== Все проверки завершены ===")
