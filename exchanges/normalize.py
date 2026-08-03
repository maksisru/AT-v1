"""Нормализация цен и circuit breaker для аномалий"""
import logging
from typing import Dict
from pathlib import Path
import threading

# Максимальный адекватный спред для реального арбитража (в процентах)
MAX_SPREAD_THRESHOLD = 20.0

# Contract multipliers для нормализации цен контрактов
# Ключ: (exchange, symbol), Значение: множитель контракта
CONTRACT_MULTIPLIERS: Dict[str, Dict[str, float]] = {}

# Настройка изолированного логгера для аномалий (потокобезопасный)
Path("data_collection").mkdir(exist_ok=True)
_logger_lock = threading.Lock()
anomaly_logger = logging.getLogger("anomaly_detector")
anomaly_logger.setLevel(logging.CRITICAL)
anomaly_logger.propagate = False  # Изоляция от root logger

if not anomaly_logger.handlers:
    anomaly_handler = logging.FileHandler(
        "data_collection/anomalies.log", 
        encoding="utf-8", 
        mode="a"
    )
    anomaly_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    )
    anomaly_logger.addHandler(anomaly_handler)


def validate_spread(
    exchange_long: str,
    exchange_short: str,
    symbol: str,
    price_long: float,
    price_short: float,
) -> bool:
    """
    Circuit Breaker: валидирует спред на адекватность.
    
    Returns:
        True: данные валидны, можно использовать для торговли
        False: аномалия обнаружена, логируется в anomalies.log
    """
    # Проверка на положительные цены
    if price_long <= 0 or price_short <= 0:
        with _logger_lock:
            anomaly_logger.critical(
                f"INVALID_PRICE | {symbol} | {exchange_long}={price_long:.6f} | "
                f"{exchange_short}={price_short:.6f} | reason=non_positive_price"
            )
        return False

    # Расчёт спреда
    spread_pct = ((price_short - price_long) / price_long) * 100
    
    # Проверка порога (используем модуль для учёта обратного направления)
    if abs(spread_pct) > MAX_SPREAD_THRESHOLD:
        ratio = price_short / price_long if price_long > 0 else 0
        with _logger_lock:
            anomaly_logger.critical(
                f"ANOMALY_DETECTED | {symbol} | {exchange_long}={price_long:.6f} | "
                f"{exchange_short}={price_short:.6f} | spread={spread_pct:.2f}% | "
                f"threshold={MAX_SPREAD_THRESHOLD}% | ratio={ratio:.2f}x"
            )
        return False

    return True


def normalize_price(exchange: str, symbol: str, price: float) -> float:
    """
    Нормализует цену контракта к базису per-token.
    Применяется если биржа котирует цену за лот контракта (10/100 токенов).
    """
    if exchange == "gate":
        return price  # Gate.io котирует per-token
    
    # Получаем множитель для данной биржи и символа
    multiplier = CONTRACT_MULTIPLIERS.get(exchange, {}).get(symbol, 1.0)
    
    if multiplier > 1.0:
        return price / multiplier
    
    return price
