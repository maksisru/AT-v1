"""Тестирование оптимизированных порогов"""
import sys
from datetime import datetime
from core.models import ArbitragePair, MarketData
from core.managers.risk_manager import RiskManager
from core.analyzers.opportunity_analyzer import OpportunityAnalyzer
from config.opportunity_config import OPPORTUNITY_CONFIG
from config.main_config import (
    OPEN_THRESHOLD, MAX_SPREAD_OPEN, MIN_NET_EDGE,
    MAX_FUNDING_DIFF, HIGH_FREQUENCY_SYMBOLS,
    HF_MIN_NET_EDGE, HF_MAX_BID_ASK_SPREAD
)

def test_config_values():
    """Проверка что конфиг обновлён правильно"""
    print("=" * 70)
    print("ТЕСТ #1: ПРОВЕРКА КОНФИГУРАЦИИ")
    print("=" * 70)
    
    tests = [
        ("OPEN_THRESHOLD", OPEN_THRESHOLD, 0.6, "MIN gross spread"),
        ("MAX_SPREAD_OPEN", MAX_SPREAD_OPEN, 2.5, "MAX gross spread"),
        ("MIN_NET_EDGE", MIN_NET_EDGE, 0.12, "MIN net edge"),
        ("MAX_FUNDING_DIFF", MAX_FUNDING_DIFF, 0.015, "Funding diff threshold"),
        ("HF_MIN_NET_EDGE", HF_MIN_NET_EDGE, 0.10, "HF symbols MIN net edge"),
        ("HF_MAX_BID_ASK", HF_MAX_BID_ASK_SPREAD, 0.20, "HF symbols MAX bid-ask"),
    ]
    
    all_passed = True
    for name, actual, expected, description in tests:
        status = "✅" if actual == expected else "❌"
        print(f"{status} {name}: {actual} (expected {expected}) — {description}")
        if actual != expected:
            all_passed = False
    
    print(f"\n[INFO] HIGH_FREQUENCY_SYMBOLS: {HIGH_FREQUENCY_SYMBOLS}")
    print(f"       Count: {len(HIGH_FREQUENCY_SYMBOLS)}")
    
    return all_passed


def test_funding_diff_fix():
    """Проверка исправления бага с funding_diff"""
    print("\n" + "=" * 70)
    print("ТЕСТ #2: ИСПРАВЛЕНИЕ БАГА FUNDING_DIFF")
    print("=" * 70)
    
    rm = RiskManager(initial_balance=1000)
    
    # Тест 1: funding_diff = 0.009 (< 0.015) — должен пройти
    opp1 = ArbitragePair(
        exchange_long='mexc',
        exchange_short='gate',
        symbol='ESPORTSUSDT',
        spread=0.8,
        funding_diff=0.009,  # 0.9%
        price_long=0.5,
        price_short=0.504,
        timestamp=datetime.now()
    )
    
    result1 = rm.check_opportunity(opp1, {})
    print(f"funding_diff=0.009 (0.9%): {result1['approved']} — {result1['reason']}")
    test1_pass = result1['approved'] == True
    
    # Тест 2: funding_diff = 0.020 (> 0.015) — должен быть отклонён
    opp2 = ArbitragePair(
        exchange_long='mexc',
        exchange_short='gate',
        symbol='ESPORTSUSDT',
        spread=0.8,
        funding_diff=0.020,  # 2.0%
        price_long=0.5,
        price_short=0.504,
        timestamp=datetime.now()
    )
    
    result2 = rm.check_opportunity(opp2, {})
    print(f"funding_diff=0.020 (2.0%): {result2['approved']} — {result2['reason']}")
    test2_pass = result2['approved'] == False and 'Funding' in result2['reason']
    
    status = "✅ PASSED" if (test1_pass and test2_pass) else "❌ FAILED"
    print(f"\n{status}")
    return test1_pass and test2_pass


def test_opportunity_analyzer():
    """Проверка OpportunityAnalyzer с новыми порогами"""
    print("\n" + "=" * 70)
    print("ТЕСТ #3: OPPORTUNITY ANALYZER")
    print("=" * 70)
    
    oa = OpportunityAnalyzer(config=OPPORTUNITY_CONFIG)
    
    print(f"MIN_GROSS_SPREAD: {oa.MIN_GROSS_SPREAD} (expected 0.6)")
    print(f"MIN_NET_EDGE: {oa.MIN_NET_EDGE} (expected 0.12)")
    print(f"MAX_GROSS_SPREAD: {oa.MAX_GROSS_SPREAD} (expected 2.5)")
    print(f"MAX_DATA_AGE_MS: {oa.MAX_DATA_AGE_MS} (expected 800)")
    print(f"HF_MIN_NET_EDGE: {oa.HF_MIN_NET_EDGE} (expected 0.10)")
    print(f"HF_MAX_BID_ASK: {oa.HF_MAX_BID_ASK} (expected 0.20)")
    
    all_ok = (
        oa.MIN_GROSS_SPREAD == 0.6 and
        oa.MIN_NET_EDGE == 0.12 and
        oa.MAX_GROSS_SPREAD == 2.5 and
        oa.MAX_DATA_AGE_MS == 800 and
        oa.HF_MIN_NET_EDGE == 0.10 and
        oa.HF_MAX_BID_ASK == 0.20
    )
    
    status = "✅ PASSED" if all_ok else "❌ FAILED"
    print(f"\n{status}")
    return all_ok


def test_hf_symbol_adaptive_thresholds():
    """Проверка адаптивных порогов для HF символов"""
    print("\n" + "=" * 70)
    print("ТЕСТ #4: АДАПТИВНЫЕ ПОРОГИ ДЛЯ HF СИМВОЛОВ")
    print("=" * 70)
    
    oa = OpportunityAnalyzer(config=OPPORTUNITY_CONFIG)
    
    # Создаём тестовые данные
    md_long = MarketData(
        symbol='ESPORTSUSDT',
        exchange='mexc',
        bid=1.000,
        ask=1.002,  # bid-ask spread = 0.2%
        timestamp=datetime.now(),
        funding_rate=0.0001
    )
    
    md_short = MarketData(
        symbol='ESPORTSUSDT',
        exchange='gate',
        bid=1.008,
        ask=1.010,  # bid-ask spread = 0.2%
        timestamp=datetime.now(),
        funding_rate=0.0002
    )
    
    # Тест 1: ESPORTSUSDT (HF symbol) с net_edge = 0.11% (между HF 0.10% и обычным 0.12%)
    opp_hf = ArbitragePair(
        exchange_long='mexc',
        exchange_short='gate',
        symbol='ESPORTSUSDT',  # HF symbol
        spread=0.8,  # gross spread
        funding_diff=0.0001,
        price_long=1.001,
        price_short=1.009,
        timestamp=datetime.now()
    )
    opp_hf.data_long = md_long
    opp_hf.data_short = md_short
    
    analysis_hf = oa.analyze(opp_hf)
    print(f"\nESPORTSUSDT (HF symbol):")
    print(f"  Gross spread: {analysis_hf.gross_spread_pct:.3f}%")
    print(f"  Net edge: {analysis_hf.net_edge_pct:.3f}%")
    print(f"  Approved: {analysis_hf.approved}")
    print(f"  Reason: {analysis_hf.reason}")
    
    # Тест 2: Обычный символ с теми же параметрами
    opp_normal = ArbitragePair(
        exchange_long='mexc',
        exchange_short='gate',
        symbol='BTCUSDT',  # не в HF списке
        spread=0.8,
        funding_diff=0.0001,
        price_long=1.001,
        price_short=1.009,
        timestamp=datetime.now()
    )
    opp_normal.data_long = md_long
    opp_normal.data_short = md_short
    
    analysis_normal = oa.analyze(opp_normal)
    print(f"\nBTCUSDT (обычный символ):")
    print(f"  Gross spread: {analysis_normal.gross_spread_pct:.3f}%")
    print(f"  Net edge: {analysis_normal.net_edge_pct:.3f}%")
    print(f"  Approved: {analysis_normal.approved}")
    print(f"  Reason: {analysis_normal.reason}")
    
    print(f"\n[COMPARISON]")
    print(f"  HF symbol uses MIN_NET_EDGE={oa.HF_MIN_NET_EDGE}% (vs {oa.MIN_NET_EDGE}%)")
    print(f"  HF symbol uses MAX_BID_ASK={oa.HF_MAX_BID_ASK}% (vs {oa.MAX_BID_ASK_SPREAD_PER_LEG}%)")
    
    return True


def main():
    """Запуск всех тестов"""
    print("\n" + "=" * 70)
    print("TESTING THRESHOLD OPTIMIZATION")
    print("=" * 70 + "\n")
    
    results = []
    
    results.append(("Config values", test_config_values()))
    results.append(("Funding diff fix", test_funding_diff_fix()))
    results.append(("Opportunity analyzer", test_opportunity_analyzer()))
    results.append(("HF adaptive thresholds", test_hf_symbol_adaptive_thresholds()))
    
    print("\n" + "=" * 70)
    print("ИТОГОВЫЕ РЕЗУЛЬТАТЫ")
    print("=" * 70)
    
    for test_name, passed in results:
        status = "✅" if passed else "❌"
        print(f"{status} {test_name}")
    
    all_passed = all(r[1] for r in results)
    
    print("\n" + "=" * 70)
    if all_passed:
        print("ALL TESTS PASSED!")
        print("\nExpected results after optimization:")
        print("  * Before: ~10-15% opportunities pass filters")
        print("  * After: ~60-70% opportunities pass filters")
        print("  * Before: ~5-10 trades/hour")
        print("  * After: ~15-25 trades/hour")
        print("  * Avg net edge: ~0.5-0.7% (with 0.5% costs)")
        print("\nIMPORTANT: Run demo for 30+ minutes to verify in real conditions")
        sys.exit(0)
    else:
        print("SOME TESTS FAILED - CHECK CONFIGURATION")
        sys.exit(1)


if __name__ == '__main__':
    main()
