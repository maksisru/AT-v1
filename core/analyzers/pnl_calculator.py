"""PnL Calculator — унифицированный расчёт прибыли/убытка"""


def calculate_net_pnl(
    entry_price_long: float,
    entry_price_short: float,
    current_price_long: float,
    current_price_short: float,
    position_size_usd: float,
    leverage: int = 5,
    fee_rate: float = 0.0005,
) -> dict:
    """
    Расчёт чистого PnL с учётом leverage и комиссий.
    
    Args:
        entry_price_long: Цена входа в LONG
        entry_price_short: Цена входа в SHORT
        current_price_long: Текущая цена на бирже LONG
        current_price_short: Текущая цена на бирже SHORT
        position_size_usd: Размер позиции в USD
        leverage: Кредитное плечо
        fee_rate: Комиссия биржи (0.05% = 0.0005)
    
    Returns:
        dict: {
            'gross_pct': процент прибыли без комиссий,
            'gross_usd': прибыль в USD без комиссий,
            'fees_usd': комиссии в USD (4 операции),
            'net_usd': чистая прибыль в USD,
            'net_pct': чистая прибыль в %
        }
    """
    # Процент прибыли по каждой позиции
    pnl_long_pct = (current_price_long - entry_price_long) / entry_price_long * 100
    pnl_short_pct = (entry_price_short - current_price_short) / entry_price_short * 100
    gross_pct = pnl_long_pct + pnl_short_pct
    
    # Notional value с учётом leverage
    notional = position_size_usd * leverage
    
    # Прибыль в USD без комиссий
    gross_usd = gross_pct * notional / 100
    
    # Комиссии: 4 операции (open long, open short, close long, close short)
    fees_usd = notional * fee_rate * 4
    
    # Чистая прибыль
    net_usd = gross_usd - fees_usd
    net_pct = (net_usd / position_size_usd) * 100
    
    return {
        "gross_pct": gross_pct,
        "gross_usd": gross_usd,
        "fees_usd": fees_usd,
        "net_usd": net_usd,
        "net_pct": net_pct,
    }


def calculate_pnl_from_spread(
    entry_spread: float,
    current_spread: float,
    position_size_usd: float,
    leverage: int = 5,
    fee_rate: float = 0.0005,
) -> dict:
    """
    Упрощённый расчёт PnL через изменение спреда.
    
    Args:
        entry_spread: Спред при открытии (%)
        current_spread: Текущий спред (%)
        position_size_usd: Размер позиции в USD
        leverage: Кредитное плечо
        fee_rate: Комиссия биржи
    
    Returns:
        dict: см. calculate_net_pnl()
    """
    # Delta spread — сколько спред сузился
    delta_spread = entry_spread - current_spread
    
    notional = position_size_usd * leverage
    gross_usd = delta_spread * notional / 100
    fees_usd = notional * fee_rate * 4
    net_usd = gross_usd - fees_usd
    net_pct = (net_usd / position_size_usd) * 100
    
    return {
        "gross_pct": delta_spread,
        "gross_usd": gross_usd,
        "fees_usd": fees_usd,
        "net_usd": net_usd,
        "net_pct": net_pct,
    }
