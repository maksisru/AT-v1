"""Order Utils — расчёт размера ордера и маппинг направлений"""


def calculate_order_qty(symbol: str, position_size_usd: float, price: float, leverage: int = 1) -> float:
    """
    Конвертирует USD в количество контрактов.
    
    Args:
        symbol: Торговая пара (например, 'BTCUSDT')
        position_size_usd: Размер позиции в USD (например, 100)
        price: Текущая цена (например, 63000)
        leverage: Плечо (например, 5)
    
    Returns:
        Количество контрактов для ордера
    
    Example:
        >>> calculate_order_qty('BTCUSDT', 100, 63000, 5)
        0.00793  # а НЕ 100
    """
    notional = position_size_usd * leverage
    qty = notional / price
    
    # Округление до точности инструмента
    if price > 10000:
        return round(qty, 3)
    elif price > 100:
        return round(qty, 2)
    else:
        return round(qty, 1)


# Маппинг направлений ордера для каждой биржи
SIDE_MAP = {
    'bybit': {
        'LONG':  {'open': 'Buy',  'close': 'Sell'},
        'SHORT': {'open': 'Sell', 'close': 'Buy'},
    },
    'mexc': {
        'LONG':  {'open': 1, 'close': 4},   # 1=open long, 4=close long
        'SHORT': {'open': 3, 'close': 2},   # 3=open short, 2=close short
    },
    'gate': {
        'LONG':  {'open': 1, 'close': -1},  # positive=buy, negative=sell
        'SHORT': {'open': -1, 'close': 1},
    },
}


def map_order_side(exchange: str, side: str, is_close: bool = False):
    """
    Маппинг направления торговли в формат конкретной биржи.
    
    Args:
        exchange: Название биржи ('bybit', 'mexc', 'gate')
        side: Направление ('LONG' или 'SHORT')
        is_close: True если закрытие позиции, False если открытие
        
    Returns:
        Значение side для API биржи
        
    Examples:
        >>> map_order_side('bybit', 'LONG', False)
        'Buy'
        >>> map_order_side('bybit', 'LONG', True)
        'Sell'
        >>> map_order_side('mexc', 'SHORT', False)
        3
    """
    exchange = exchange.lower()
    
    if exchange not in SIDE_MAP:
        raise ValueError(f"Unknown exchange: {exchange}")
    
    if side not in SIDE_MAP[exchange]:
        raise ValueError(f"Invalid side: {side}. Must be 'LONG' or 'SHORT'")
    
    action = 'close' if is_close else 'open'
    return SIDE_MAP[exchange][side][action]

    """
    Конвертирует внутреннее направление ('LONG'/'SHORT') в формат биржи.
    
    Args:
        exchange: Имя биржи ('bybit', 'mexc', 'gate')
        side: Направление ('LONG' или 'SHORT')
        is_close: True если закрытие позиции, False если открытие
    
    Returns:
        Направление в формате API биржи
    
    Examples:
        >>> map_order_side('bybit', 'LONG', False)
        'Buy'
        >>> map_order_side('bybit', 'SHORT', True)
        'Buy'
        >>> map_order_side('mexc', 'LONG', False)
        1
    """
    exchange = exchange.lower()
    action = 'close' if is_close else 'open'
    return SIDE_MAP[exchange][side][action]
