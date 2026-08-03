"""Unit tests для критических функций"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from core.utils.order_utils import calculate_order_qty, map_order_side
from core.analyzers.pnl_calculator import calculate_net_pnl, calculate_pnl_from_spread


class TestOrderUtils:
    """Тесты для order_utils.py"""
    
    def test_qty_btc(self):
        """Тест расчёта количества для BTC"""
        qty = calculate_order_qty('BTCUSDT', position_size_usd=100, price=63000, leverage=5)
        assert abs(qty - 0.00793) < 0.0001, f"Expected ~0.00793, got {qty}"
    
    def test_qty_not_raw_usd(self):
        """КРИТИЧЕСКИЙ: qty не должен равняться сырому USD"""
        qty = calculate_order_qty('BTCUSDT', position_size_usd=100, price=63000, leverage=5)
        assert qty != 100, "CRITICAL: qty must not equal raw USD amount"
    
    def test_qty_eth(self):
        """Тест расчёта для ETH"""
        qty = calculate_order_qty('ETHUSDT', position_size_usd=100, price=3000, leverage=5)
        expected = 100 * 5 / 3000
        assert abs(qty - expected) < 0.01
    
    def test_bybit_side_mapping(self):
        """Тест маппинга сторон для Bybit"""
        assert map_order_side('bybit', 'LONG',  is_close=False) == 'Buy'
        assert map_order_side('bybit', 'SHORT', is_close=False) == 'Sell'
        assert map_order_side('bybit', 'LONG',  is_close=True)  == 'Sell'
        assert map_order_side('bybit', 'SHORT', is_close=True)  == 'Buy'
    
    def test_mexc_side_mapping(self):
        """Тест маппинга сторон для MEXC"""
        assert map_order_side('mexc', 'LONG',  is_close=False) == 1  # open long
        assert map_order_side('mexc', 'SHORT', is_close=False) == 3  # open short
        assert map_order_side('mexc', 'LONG',  is_close=True)  == 4  # close long
        assert map_order_side('mexc', 'SHORT', is_close=True)  == 2  # close short
    
    def test_gate_side_mapping(self):
        """Тест маппинга сторон для Gate"""
        assert map_order_side('gate', 'LONG',  is_close=False) == 1
        assert map_order_side('gate', 'SHORT', is_close=False) == -1
        assert map_order_side('gate', 'LONG',  is_close=True)  == -1
        assert map_order_side('gate', 'SHORT', is_close=True)  == 1


class TestPnLCalculator:
    """Тесты для pnl_calculator.py"""
    
    def test_calculate_net_pnl_profit(self):
        """Тест расчёта PnL для прибыльной позиции"""
        result = calculate_net_pnl(
            entry_price_long=100,
            entry_price_short=101,
            current_price_long=101,  # +1%
            current_price_short=100,  # +1%
            position_size_usd=100,
            leverage=5,
            fee_rate=0.0005,
        )
        
        # Gross: 1% + 1% = 2%
        assert abs(result['gross_pct'] - 2.0) < 0.01
        
        # Gross USD: 2% * 500 (notional) = 10 USD
        assert abs(result['gross_usd'] - 10.0) < 0.1
        
        # Fees: 500 * 0.0005 * 4 = 1 USD
        assert abs(result['fees_usd'] - 1.0) < 0.01
        
        # Net: 10 - 1 = 9 USD
        assert abs(result['net_usd'] - 9.0) < 0.1
    
    def test_calculate_pnl_from_spread(self):
        """Тест расчёта PnL через спред"""
        result = calculate_pnl_from_spread(
            entry_spread=5.0,   # Открыли при спреде 5%
            current_spread=3.0,  # Сейчас спред 3%
            position_size_usd=100,
            leverage=5,
        )
        
        # Delta spread: 5 - 3 = 2%
        assert abs(result['gross_pct'] - 2.0) < 0.01
        
        # Gross USD: 2% * 500 = 10 USD
        assert abs(result['gross_usd'] - 10.0) < 0.1
    
    def test_fees_are_subtracted(self):
        """КРИТИЧЕСКИЙ: комиссии должны вычитаться из прибыли"""
        result = calculate_net_pnl(
            entry_price_long=100,
            entry_price_short=100,
            current_price_long=100,
            current_price_short=100,
            position_size_usd=100,
            leverage=5,
            fee_rate=0.0005,
        )
        
        # Без движения цены gross = 0, но есть комиссии
        assert result['gross_usd'] == 0
        assert result['fees_usd'] > 0
        assert result['net_usd'] < 0  # Убыток из-за комиссий


class TestRiskManager:
    """Тесты для risk_manager.py (критические сценарии)"""
    
    def test_no_duplicate_positions(self):
        """КРИТИЧЕСКИЙ: не должно быть дублирования позиций"""
        from risk_manager import RiskManager
        
        rm = RiskManager(initial_balance=1000)
        
        # Открываем две позиции с одним символом
        rm.register_position('pair1', 'BTCUSDT', 'mexc', 'gate')
        rm.register_position('pair2', 'BTCUSDT', 'bybit', 'gate')
        
        assert rm.get_open_count() == 2, "Should have 2 positions"
        
        # Закрываем первую
        rm.unregister_position('pair1')
        
        assert rm.get_open_count() == 1, "Should have 1 position left"
        assert 'pair2' in rm.open_positions, "pair2 should still exist"
        assert 'pair1' not in rm.open_positions, "pair1 should be removed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
