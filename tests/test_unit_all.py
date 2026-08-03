"""Unit-тесты для критических компонентов системы (pytest)"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from datetime import datetime
from core.models import MarketData, ArbitragePair, Trade
from core.utils.order_utils import calculate_order_qty, map_order_side
from core.utils.symbol_utils import normalize_symbol, to_exchange_symbol
from core.analyzers.pnl_calculator import calculate_net_pnl
from core.managers.risk_manager import RiskManager
from core.engines.arbitrage_engine import ArbitrageEngine


class TestOrderUtils:
    """Тесты для order_utils.py"""
    
    def test_calculate_order_qty_btc(self):
        """Проверка расчёта qty для BTC"""
        qty = calculate_order_qty('BTCUSDT', 100, 63000, leverage=5)
        expected = (100 * 5) / 63000  # 0.00793
        assert abs(qty - expected) < 0.0001
        assert qty != 100, "Qty не должен равняться сырому USD!"
    
    def test_map_order_side_bybit(self):
        """Проверка маппинга для Bybit"""
        # LONG open
        assert map_order_side('bybit', 'LONG', False) == 'Buy'
        # LONG close
        assert map_order_side('bybit', 'LONG', True) == 'Sell'
        # SHORT open
        assert map_order_side('bybit', 'SHORT', False) == 'Sell'
        # SHORT close
        assert map_order_side('bybit', 'SHORT', True) == 'Buy'
    
    def test_map_order_side_mexc(self):
        """Проверка маппинга для MEXC"""
        assert map_order_side('mexc', 'LONG', False) == 1  # open long
        assert map_order_side('mexc', 'LONG', True) == 4   # close long
        assert map_order_side('mexc', 'SHORT', False) == 3  # open short
        assert map_order_side('mexc', 'SHORT', True) == 2   # close short


class TestSymbolUtils:
    """Тесты для symbol_utils.py"""
    
    def test_normalize_symbol(self):
        """Проверка нормализации символов"""
        assert normalize_symbol("BTC_USDT") == "BTCUSDT"
        assert normalize_symbol("BTC/USDT") == "BTCUSDT"
        assert normalize_symbol("BTC-USDT") == "BTCUSDT"
        assert normalize_symbol("btcusdt") == "BTCUSDT"
    
    def test_to_exchange_symbol(self):
        """Проверка конвертации в формат биржи"""
        assert to_exchange_symbol("BTCUSDT", "mexc") == "BTC_USDT"
        assert to_exchange_symbol("BTCUSDT", "gate") == "BTC_USDT"
        assert to_exchange_symbol("BTCUSDT", "bybit") == "BTCUSDT"


class TestPnLCalculator:
    """Тесты для pnl_calculator.py"""
    
    def test_calculate_net_pnl_profit(self):
        """Проверка расчёта прибыльной позиции"""
        result = calculate_net_pnl(
            entry_price_long=100,
            entry_price_short=101,
            current_price_long=101,   # +1%
            current_price_short=100,  # +1%
            position_size_usd=100,
            leverage=5,
            fee_rate=0.0005
        )
        
        assert result['gross_pct'] == pytest.approx(2.0, abs=0.01)
        assert result['gross_usd'] == pytest.approx(10.0, abs=0.1)
        assert result['fees_usd'] == pytest.approx(1.0, abs=0.01)
        assert result['net_usd'] == pytest.approx(9.0, abs=0.1)
    
    def test_fees_deducted(self):
        """Комиссии должны вычитаться"""
        result = calculate_net_pnl(
            entry_price_long=100,
            entry_price_short=100,
            current_price_long=100,
            current_price_short=100,
            position_size_usd=100,
            leverage=5,
            fee_rate=0.0005
        )
        
        assert result['gross_usd'] == 0
        assert result['fees_usd'] > 0
        assert result['net_usd'] < 0  # Убыток из-за комиссий


class TestRiskManager:
    """Тесты для risk_manager.py"""
    
    def test_no_duplicate_positions(self):
        """Не должно быть дублирования позиций"""
        rm = RiskManager(initial_balance=1000)
        
        # Открываем 2 позиции с одним символом
        rm.register_position('pair1', 'BTCUSDT', 'mexc', 'gate')
        rm.register_position('pair2', 'BTCUSDT', 'bybit', 'gate')
        
        assert rm.get_open_count() == 2
        
        # Закрываем первую
        rm.unregister_position('pair1')
        
        assert rm.get_open_count() == 1
        assert 'pair2' in rm.open_positions
        assert 'pair1' not in rm.open_positions
    
    def test_position_metadata(self):
        """Метаданные должны сохраняться"""
        rm = RiskManager(initial_balance=1000)
        rm.register_position('test_pair', 'BTCUSDT', 'mexc', 'gate')
        
        pos = rm.open_positions['test_pair']
        assert pos['symbol'] == 'BTCUSDT'
        assert pos['exchange_long'] == 'mexc'
        assert pos['exchange_short'] == 'gate'
        assert 'opened_at' in pos


class TestArbitrageEngine:
    """Тесты для arbitrage_engine.py"""
    
    def test_gross_vs_effective_spread(self):
        """Gross и effective спреды должны различаться"""
        engine = ArbitrageEngine()
        
        long_data = MarketData(
            exchange="mexc",
            symbol="BTCUSDT",
            bid=63000.0,
            ask=63100.0,
            funding_rate=0.0001,
            timestamp=datetime.now()
        )
        
        short_data = MarketData(
            exchange="gate",
            symbol="BTCUSDT",
            bid=63500.0,
            ask=63600.0,
            funding_rate=0.00015,
            timestamp=datetime.now()
        )
        
        gross = engine.calculate_gross_spread(long_data, short_data)
        effective = engine.calculate_effective_spread(long_data, short_data)
        
        assert gross != effective
        assert abs(gross - effective) < 0.1  # Небольшая разница
    
    def test_spread_reasonable(self):
        """Спреды должны быть разумными (< 100%)"""
        engine = ArbitrageEngine()
        
        long_data = MarketData(
            exchange="mexc",
            symbol="BTCUSDT",
            bid=63000.0,
            ask=63100.0,
            funding_rate=0.01,  # Экстремальный
            timestamp=datetime.now()
        )
        
        short_data = MarketData(
            exchange="gate",
            symbol="BTCUSDT",
            bid=63500.0,
            ask=63600.0,
            funding_rate=-0.01,  # Экстремальный
            timestamp=datetime.now()
        )
        
        effective = engine.calculate_effective_spread(long_data, short_data)
        
        assert abs(effective) < 100, f"Спред {effective}% слишком большой (баг?)"


class TestIntegration:
    """Интеграционные тесты"""
    
    def test_full_flow_simulation(self):
        """Симуляция полного flow: найти → открыть → закрыть"""
        # TODO: Реализовать end-to-end тест
        pass
    
    def test_concurrent_positions(self):
        """Множественные позиции одновременно"""
        # TODO: Проверить что система корректно работает с 3+ позициями
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
