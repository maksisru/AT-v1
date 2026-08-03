"""
Валидационный тест для проверки детекции аномалии EDGEUSDT.
Моделирует реальный инцидент: Gate=0.06532, Bybit=0.4655 (спред 612%).
"""
import sys
import unittest
from pathlib import Path

# Добавляем корневую директорию в sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from exchanges.normalize import validate_spread, MAX_SPREAD_THRESHOLD


class TestAnomalyDetection(unittest.TestCase):
    """Тестирование Circuit Breaker на реальных данных аномалий"""
    
    def test_edge_anomaly_gate_to_bybit(self):
        """Тест 1: Детекция аномалии EDGEUSDT (Long Gate, Short Bybit)"""
        gate_price = 0.06532
        bybit_price = 0.4655
        symbol = "EDGEUSDT"
        
        # Circuit Breaker должен заблокировать этот спред
        result = validate_spread("gate", "bybit", symbol, gate_price, bybit_price)
        
        self.assertFalse(result, "Аномальный спред 612% должен быть заблокирован")
    
    def test_edge_anomaly_reverse(self):
        """Тест 2: Детекция аномалии в обратном направлении"""
        gate_price = 0.06532
        bybit_price = 0.4655
        symbol = "EDGEUSDT"
        
        # Обратное направление также должно блокироваться
        result = validate_spread("bybit", "gate", symbol, bybit_price, gate_price)
        
        self.assertFalse(result, "Обратный аномальный спред должен быть заблокирован")
    
    def test_valid_small_spread(self):
        """Тест 3: Валидный малый спред пропускается"""
        price1 = 30000.0
        price2 = 30600.0  # +2% спред
        symbol = "BTCUSDT"
        
        # Валидный спред должен пройти проверку
        result = validate_spread("gate", "bybit", symbol, price1, price2)
        
        self.assertTrue(result, "Валидный спред 2% должен пройти проверку")
    
    def test_edge_case_exactly_threshold(self):
        """Тест 4: Спред точно на пороге (граничный случай)"""
        price1 = 100.0
        price2 = 110.0  # Ровно 10% спред
        symbol = "TESTUSDT"
        
        # Точно на пороге — должен пройти (<=)
        result = validate_spread("gate", "bybit", symbol, price1, price2)
        
        self.assertTrue(result, f"Спред на пороге {MAX_SPREAD_THRESHOLD}% должен пройти")
    
    def test_edge_case_just_over_threshold(self):
        """Тест 5: Спред чуть выше порога"""
        price1 = 100.0
        price2 = 110.01  # 10.01% спред
        symbol = "TESTUSDT"
        
        # Чуть выше порога — должен блокироваться
        result = validate_spread("gate", "bybit", symbol, price1, price2)
        
        self.assertFalse(result, "Спред выше порога должен быть заблокирован")
    
    def test_negative_prices(self):
        """Тест 6: Отрицательные или нулевые цены блокируются"""
        # Нулевая цена
        result1 = validate_spread("gate", "bybit", "TESTUSDT", 0.0, 100.0)
        self.assertFalse(result1, "Нулевая цена должна быть заблокирована")
        
        # Отрицательная цена
        result2 = validate_spread("gate", "bybit", "TESTUSDT", -10.0, 100.0)
        self.assertFalse(result2, "Отрицательная цена должна быть заблокирована")
    
    def test_anomaly_log_file_created(self):
        """Тест 7: Проверка создания лог-файла аномалий"""
        log_path = Path("data_collection/anomalies.log")
        
        # Триггерим аномалию
        validate_spread("gate", "bybit", "EDGEUSDT", 0.06532, 0.4655)
        
        # Проверяем существование лога
        self.assertTrue(log_path.exists(), "Лог-файл anomalies.log должен быть создан")


def run_tests_with_summary():
    """Запуск тестов с красивым выводом результатов"""
    print("=" * 70)
    print("🧪 ВАЛИДАЦИОННЫЙ ТЕСТ: Circuit Breaker для аномалий")
    print("=" * 70)
    print()
    
    # Создаем test suite
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestAnomalyDetection)
    
    # Запускаем тесты
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Итоговая статистика
    print()
    print("=" * 70)
    print("📋 РЕЗУЛЬТАТЫ:")
    print("=" * 70)
    print(f"   Всего тестов:   {result.testsRun}")
    print(f"   Успешных:       {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"   Провалено:      {len(result.failures)}")
    print(f"   Ошибок:         {len(result.errors)}")
    print()
    
    if result.wasSuccessful():
        print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ")
        print(f"   Circuit breaker работает корректно (порог {MAX_SPREAD_THRESHOLD}%)")
        print("   Аномалия EDGEUSDT успешно детектирована")
        print("   Логи записаны в data_collection/anomalies.log")
        return True
    else:
        print("❌ НЕКОТОРЫЕ ТЕСТЫ ПРОВАЛЕНЫ")
        print("   Требуется доработка логики валидации")
        return False


if __name__ == "__main__":
    success = run_tests_with_summary()
    sys.exit(0 if success else 1)
