"""Rate Limiter — защита от превышения лимитов API"""
import asyncio
import time
from typing import Dict, Optional


class RateLimiter:
    """Управление rate limits для REST API"""
    
    def __init__(self, max_requests: int = 10, time_window: float = 1.0):
        """
        Args:
            max_requests: Максимум запросов
            time_window: Временное окно в секундах
        """
        self.semaphore = asyncio.Semaphore(max_requests)
        self.time_window = time_window
        self.last_request_time: Optional[float] = None
        self.request_count = 0
        self.max_requests = max_requests
    
    async def acquire(self):
        """Получить разрешение на запрос"""
        async with self.semaphore:
            current_time = time.time()
            
            # Сброс счётчика если прошло time_window
            if self.last_request_time and (current_time - self.last_request_time) > self.time_window:
                self.request_count = 0
            
            # Если достигнут лимит, ждём
            if self.request_count >= self.max_requests:
                wait_time = self.time_window - (current_time - self.last_request_time)
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
                self.request_count = 0
            
            self.request_count += 1
            self.last_request_time = current_time
    
    async def execute_with_retry(self, coro, max_retries: int = 3):
        """
        Выполнить запрос с retry при 429 ошибке
        
        Args:
            coro: Async функция для выполнения
            max_retries: Максимум попыток
        """
        for attempt in range(max_retries):
            try:
                await self.acquire()
                result = await coro()
                return result
            except Exception as e:
                # Проверяем на 429 Too Many Requests
                if '429' in str(e) or 'rate limit' in str(e).lower():
                    if attempt < max_retries - 1:
                        # Exponential backoff
                        wait_time = 2 ** attempt
                        print(f"⚠️ Rate limit hit, waiting {wait_time}s before retry...")
                        await asyncio.sleep(wait_time)
                        continue
                raise


# Глобальные rate limiters для каждой биржи
EXCHANGE_RATE_LIMITERS: Dict[str, RateLimiter] = {
    'mexc': RateLimiter(max_requests=20, time_window=1.0),      # 20 req/s
    'gate': RateLimiter(max_requests=10, time_window=1.0),      # 10 req/s
    'bybit': RateLimiter(max_requests=10, time_window=1.0),     # 10 req/s
    'asterdex': RateLimiter(max_requests=5, time_window=1.0),   # 5 req/s (консервативно)
}


def get_rate_limiter(exchange_name: str) -> RateLimiter:
    """Получить rate limiter для биржи"""
    return EXCHANGE_RATE_LIMITERS.get(exchange_name.lower(), RateLimiter())
