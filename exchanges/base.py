"""Базовый класс для интеграции с биржами"""
from abc import ABC, abstractmethod
from typing import List, Dict
import aiohttp
from core.models import MarketData
from core.utils.rate_limiter import get_rate_limiter
from core.utils.symbol_utils import normalize_symbol, to_exchange_symbol


class BaseExchange(ABC):
    """Базовый интерфейс биржи"""
    
    def __init__(self, name: str, api_key: str = "", api_secret: str = ""):
        self.name = name
        self.api_key = api_key if api_key else ""
        self.api_secret = api_secret if api_secret else ""
        self.ws = None
        self.session = None
        self.rate_limiter = get_rate_limiter(name)  # Rate limiter для REST API
    
    def to_canonical(self, exchange_symbol: str) -> str:
        """Конвертация биржевого символа в canonical формат (BTCUSDT)"""
        return normalize_symbol(exchange_symbol)
    
    def to_local(self, canonical: str) -> str:
        """Конвертация canonical в формат этой биржи"""
        return to_exchange_symbol(canonical, self.name)
    
    async def initialize(self):
        """Инициализация HTTP сессии и WebSocket"""
        self.session = aiohttp.ClientSession()
        await self.connect_ws()
    
    async def close(self):
        """Закрытие соединений"""
        if self.ws:
            await self.ws.close()
        if self.session:
            await self.session.close()
    
    async def _rate_limited_request(self, coro):
        """Выполнить HTTP запрос с rate limiting"""
        return await self.rate_limiter.execute_with_retry(coro)
    
    async def start_websocket_listener(self, symbols: List[str]):
        """
        Запуск WebSocket слушателя (универсальный метод)
        
        Args:
            symbols: Список символов для подписки
        """
        # Подключаемся к WebSocket
        await self.connect_ws()
        
        # Подписываемся на символы
        await self.subscribe_orderbook(symbols)
        
        # Запускаем фоновый listener (бесконечный цикл)
        # Реализация зависит от конкретной биржи
        pass
        
    @abstractmethod
    async def connect_ws(self):
        """Подключение к WebSocket"""
        pass
    
    @abstractmethod
    async def subscribe_orderbook(self, symbols: List[str]):
        """Подписка на orderbook"""
        pass
    
    @abstractmethod
    async def get_market_data(self, symbol: str) -> MarketData:
        """Получение рыночных данных"""
        pass
    
    @abstractmethod
    async def get_instruments(self) -> List[str]:
        """Получение списка инструментов"""
        pass
    
    @abstractmethod
    async def place_order(self, symbol: str, side: str, size: float, order_type: str = 'market') -> Dict:
        """Размещение ордера"""
        pass
    
    @abstractmethod
    async def close_position(self, symbol: str, side: str) -> Dict:
        """Закрытие позиции"""
        pass
    
    @abstractmethod
    async def get_balance(self) -> float:
        """Получение баланса"""
        pass
