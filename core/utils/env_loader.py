"""Загрузка конфигурации из .env файла"""
import os
from pathlib import Path


def load_env():
    """Загрузка переменных окружения из .env файла"""
    # Ищем .env в корне проекта (2 уровня вверх от core/utils/)
    env_path = Path(__file__).parent.parent.parent / '.env'
    
    if not env_path.exists():
        print("⚠️  .env файл не найден. Используйте .env.example как шаблон.")
        return
    
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()


def get_api_keys(exchange: str):
    """Получение API ключей для биржи"""
    load_env()
    
    key = os.getenv(f'{exchange.upper()}_API_KEY')
    secret = os.getenv(f'{exchange.upper()}_API_SECRET')
    
    return key, secret


def get_telegram_config():
    """Получение Telegram конфигурации"""
    load_env()
    
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    
    # Пустые строки трактуем как None
    if bot_token == '':
        bot_token = None
    if chat_id == '':
        chat_id = None
    
    return bot_token, chat_id
