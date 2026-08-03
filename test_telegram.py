"""Тест отправки в Telegram"""
import asyncio
from utils.telegram_logger import TelegramLogger
from core.utils.env_loader import get_telegram_config

async def test_telegram():
    bot_token, chat_id = get_telegram_config()
    
    print(f"Bot token: {bot_token[:20] if bot_token else None}...")
    print(f"Chat ID: {chat_id}")
    
    telegram = TelegramLogger(bot_token, chat_id)
    
    if not telegram.enabled:
        print("Telegram disabled - missing credentials")
        return
    
    print("Telegram enabled, sending test message...")
    await telegram.send("🧪 <b>Test message</b>\n\nЕсли видишь это — Telegram работает!")
    print("Message sent")

if __name__ == "__main__":
    asyncio.run(test_telegram())
