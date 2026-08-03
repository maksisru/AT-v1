"""Symbol Normalization — единый формат символов во всей системе

Canonical Format: BTCUSDT (без разделителей, uppercase)

Exchange Formats:
- MEXC: BTC_USDT
- Gate.io: BTC_USDT
- Bybit: BTCUSDT
"""


def to_canonical(exchange_symbol: str) -> str:
    """
    Нормализация биржевого символа в canonical формат
    
    Args:
        exchange_symbol: Символ в формате биржи (BTC_USDT, BTC/USDT, BTCUSDT)
        
    Returns:
        Canonical symbol: BTCUSDT
    
    Examples:
        >>> to_canonical("BTC_USDT")
        'BTCUSDT'
        >>> to_canonical("BTC/USDT")
        'BTCUSDT'
        >>> to_canonical("BTCUSDT")
        'BTCUSDT'
    """
    return exchange_symbol.replace("-", "").replace("_", "").replace("/", "").upper()


# Алиас для обратной совместимости
normalize_symbol = to_canonical


def to_mexc_symbol(canonical_symbol: str) -> str:
    """
    Конвертация canonical в MEXC формат
    
    Args:
        canonical_symbol: BTCUSDT
        
    Returns:
        MEXC format: BTC_USDT
    """
    # MEXC использует BTC_USDT
    if "USDT" in canonical_symbol:
        base = canonical_symbol.replace("USDT", "")
        return f"{base}_USDT"
    return canonical_symbol


def to_gate_symbol(canonical_symbol: str) -> str:
    """
    Конвертация canonical в Gate.io формат
    
    Args:
        canonical_symbol: BTCUSDT
        
    Returns:
        Gate format: BTC_USDT
    """
    # Gate использует BTC_USDT для futures
    if "USDT" in canonical_symbol:
        base = canonical_symbol.replace("USDT", "")
        return f"{base}_USDT"
    return canonical_symbol


def to_bybit_symbol(canonical_symbol: str) -> str:
    """
    Конвертация canonical в Bybit формат
    
    Args:
        canonical_symbol: BTCUSDT
        
    Returns:
        Bybit format: BTCUSDT
    """
    # Bybit использует BTCUSDT (как canonical)
    return canonical_symbol


def to_exchange_symbol(canonical_symbol: str, exchange: str) -> str:
    """
    Универсальная конвертация canonical в формат биржи
    
    Args:
        canonical_symbol: BTCUSDT
        exchange: 'mexc', 'gate', 'bybit'
        
    Returns:
        Exchange-specific format
    """
    exchange = exchange.lower()
    
    converters = {
        'mexc': to_mexc_symbol,
        'gate': to_gate_symbol,
        'bybit': to_bybit_symbol,
    }
    
    converter = converters.get(exchange)
    if converter:
        return converter(canonical_symbol)
    
    # Fallback: return canonical
    return canonical_symbol
