"""Telegram Logger — отправка уведомлений в Telegram"""
import asyncio
import aiohttp
from datetime import datetime
from typing import Optional


class TelegramLogger:
    """Логирование событий в Telegram"""
    
    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = bool(bot_token and chat_id)
        self.api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage" if bot_token else None
        
        if not self.enabled:
            print("[WARNING] Telegram logger disabled (no credentials)")
    
    async def send(self, message: str, parse_mode: str = "HTML"):
        """Отправка сообщения в Telegram"""
        if not self.enabled:
            return
        
        try:
            async with aiohttp.ClientSession() as session:
                data = {
                    "chat_id": str(self.chat_id),
                    "text": message,
                    "parse_mode": parse_mode
                }
                async with session.post(self.api_url, json=data, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        print(f"[TELEGRAM ERROR] Status {resp.status}: {text}")
                    else:
                        print(f"[TELEGRAM OK] Message sent")
        except asyncio.TimeoutError:
            print(f"[TELEGRAM ERROR] Timeout")
        except Exception as e:
            print(f"[TELEGRAM ERROR] {type(e).__name__}: {e}")
    
    async def log_system_start(self, balance: float, strategy: str, exchanges: list):
        """Логирование старта системы"""
        message = f"""
🚀 <b>Система запущена</b>

💰 Баланс: {balance} USD
📊 Стратегия: {strategy}
🏦 Биржи: {', '.join(exchanges)}
🕐 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        await self.send(message)
    
    async def log_opportunity(self, symbol: str, exchange_long: str, exchange_short: str, spread: float):
        """Логирование найденной возможности"""
        message = f"""
🔍 <b>Возможность найдена</b>

📈 {symbol}
🏦 LONG: {exchange_long}
🏦 SHORT: {exchange_short}
💹 Спред: {spread:.3f}%
"""
        await self.send(message)
    
    async def log_position_opened(self, symbol: str, exchange_long: str, exchange_short: str, 
                                   spread: float, position_size: float):
        """Логирование открытия позиции"""
        message = f"""
✅ <b>Позиция открыта</b>

📈 {symbol}
🏦 LONG: {exchange_long}
🏦 SHORT: {exchange_short}
💹 Спред: {spread:.3f}%
💰 Размер: {position_size:.2f} USD
🕐 {datetime.now().strftime('%H:%M:%S')}
"""
        await self.send(message)
    
    async def log_position_closed(self, symbol: str, spread_open: float, spread_close: float, 
                                   pnl: float, hold_time: float, reason: str):
        """Логирование закрытия позиции"""
        emoji = "✅" if pnl > 0 else "❌"
        message = f"""
{emoji} <b>Позиция закрыта</b>

📈 {symbol}
💹 Спред вход: {spread_open:.3f}%
💹 Спред выход: {spread_close:.3f}%
💰 PnL: {pnl:+.2f} USD
⏱️ Время: {hold_time:.1f}s
📝 Причина: {reason}
🕐 {datetime.now().strftime('%H:%M:%S')}
"""
        await self.send(message)
    
    async def log_error(self, error_type: str, details: str):
        """Логирование ошибки"""
        message = f"""
❌ <b>Ошибка</b>

🔴 Тип: {error_type}
📝 Детали: {details}
🕐 {datetime.now().strftime('%H:%M:%S')}
"""
        await self.send(message)
    
    async def log_daily_stats(self, total_trades: int, profitable: int, total_pnl: float, 
                              win_rate: float, avg_hold_time: float):
        """Ежедневная статистика"""
        message = f"""
📊 <b>Дневная статистика</b>

📈 Всего сделок: {total_trades}
✅ Прибыльных: {profitable}
💰 Общий PnL: {total_pnl:+.2f} USD
📊 Win Rate: {win_rate:.1f}%
⏱️ Среднее время: {avg_hold_time:.1f}s
🕐 {datetime.now().strftime('%Y-%m-%d')}
"""
        await self.send(message)
    
    async def log_risk_warning(self, warning_type: str, details: str):
        """Предупреждение о рисках"""
        message = f"""
⚠️ <b>Предупреждение</b>

🔶 {warning_type}
📝 {details}
🕐 {datetime.now().strftime('%H:%M:%S')}
"""
        await self.send(message)
