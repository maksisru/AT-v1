"""Gate.io Exchange Connector"""
import json
import asyncio
import websockets
import time
import aiohttp
import hmac
import hashlib
from typing import List, Dict
from datetime import datetime
from exchanges.base import BaseExchange
from exchanges.auth_utils import get_timestamp_ms
from core.models import MarketData


class GateExchange(BaseExchange):
    """Коннектор для биржи Gate.io Futures"""
    
    WS_URL = "wss://fx-ws.gateio.ws/v4/ws/usdt"
    REST_URL = "https://fx-api.gateio.ws/api/v4"
    
    def __init__(self, api_key: str = "", api_secret: str = ""):
        super().__init__("gate", api_key, api_secret)
        self.orderbooks = {}
        self.funding_rates = {}
        self.instruments = []
        self.ws_running = False
    
    async def start_websocket_listener(self, symbols: List[str]):
        """Запуск WebSocket слушателя с автоматическим реконнектом"""
        # 🔒 Жесткая блокировка повторного запуска
        if hasattr(self, '_is_listening') and self._is_listening:
            return
        self._is_listening = True
        
        self.ws_running = True
        
        while self.ws_running:
            try:
                # 🔧 FIX: Закрываем старое соединение перед реконнектом
                if hasattr(self, 'ws') and self.ws:
                    try:
                        await self.ws.close()
                    except Exception:
                        pass
                    self.ws = None
                
                await self.connect_ws()
                await self.subscribe_orderbook(symbols)
                
                # 🔧 FIX: Явный recv() вместо async for для предотвращения race condition
                while self.ws_running and self.ws:
                    try:
                        message = await self.ws.recv()
                        data = json.loads(message)
                        await self._handle_message(data)
                    except websockets.exceptions.ConnectionClosed:
                        print("⚠️ Gate.io WS connection closed, reconnecting...")
                        break
                    
            except Exception as e:
                print(f"❌ Gate.io WebSocket error: {e}, reconnecting...")
                await asyncio.sleep(2)
    
    async def stop_websocket(self):
        """Остановка WebSocket"""
        self.ws_running = False
        if self.ws:
            await self.ws.close()
    
    def _normalize_symbol(self, symbol: str) -> str:
        """Нормализация символа к canonical формату BTCUSDT"""
        return self.to_canonical(symbol)
    
    def _exchange_format_symbol(self, symbol: str) -> str:
        """Конвертация BTCUSDT в формат биржи BTC_USDT"""
        return self.to_local(symbol)
    
    async def _handle_message(self, data: dict):
        """Обработка входящего сообщения"""
        # print(f"🔍 GATE RAW MESSAGE: {data}")  # Отладка отключена
        try:
            channel = data.get("channel")
            event = data.get("event")
            
            # Пропускаем служебные сообщения
            if event in ["subscribe", "pong"]:
                return
            
            # Обработка order_book (событие "all" или "update")
            if channel == "futures.order_book" and event in ["all", "update"]:
                result = data.get("result", {})
                contract = result.get("contract")
                asks = result.get("asks", [])
                bids = result.get("bids", [])
                
                if contract and asks and bids:
                    symbol = self._normalize_symbol(contract)
                    self.orderbooks[symbol] = {
                        "bid": float(bids[0]["p"]),
                        "ask": float(asks[0]["p"])
                    }
                    # print(f"✅ GATE orderbook saved: {symbol}")
            
            # Обработка tickers
            elif channel == "futures.tickers" and event == "update":
                for ticker in data.get("result", []):
                    contract = ticker.get("contract")
                    funding_rate = ticker.get("funding_rate")
                    
                    if contract and funding_rate is not None:
                        symbol = self._normalize_symbol(contract)
                        self.funding_rates[symbol] = float(funding_rate)
                        # print(f"✅ GATE funding rate saved: {symbol}")
        except Exception as e:
            print(f"⚠️ Gate.io message parse error: {e}")
    
    async def connect_ws(self):
        """Подключение к WebSocket"""
        self.ws = await websockets.connect(
            self.WS_URL,
            ping_interval=15,  # Отправлять ping каждые 15 секунд
            ping_timeout=30    # Ждать pong 30 секунд
        )
        print(f"✅ Gate.io WebSocket connected")
    
    async def subscribe_orderbook(self, symbols: List[str]):
        """Подписка на orderbook для списка символов"""
        for symbol in symbols:
            exchange_symbol = self._exchange_format_symbol(symbol)
            # Подписка на order_book
            await self.ws.send(json.dumps({
                "time": int(time.time()),
                "channel": "futures.order_book",
                "event": "subscribe",
                "payload": [exchange_symbol, "20", "0"]
            }))
            
            # Подписка на tickers (funding rate)
            await self.ws.send(json.dumps({
                "time": int(time.time()),
                "channel": "futures.tickers",
                "event": "subscribe",
                "payload": [exchange_symbol]
            }))
        
        print(f"✅ Gate.io subscribed to {len(symbols)} symbols")
    
    async def subscribe_funding_rate(self, symbols: List[str]):
        """Подписка на funding rate (уже включена в subscribe_orderbook)"""
        pass  # Funding rate подписка происходит через futures.tickers в subscribe_orderbook
    
    async def get_market_data(self, symbol: str = None) -> MarketData:
        """Получение рыночных данных из локального хранилища"""
        # Если symbol не указан, возвращаем любые доступные данные
        if symbol is None:
            for sym in self.orderbooks.keys():
                return MarketData(
                    exchange=self.name,
                    symbol=sym,
                    bid=self.orderbooks[sym]["bid"],
                    ask=self.orderbooks[sym]["ask"],
                    funding_rate=self.funding_rates.get(sym, 0.0),
                    timestamp=datetime.now()
                )
            return None
        
        # Просто читаем готовые данные для конкретного символа
        if symbol in self.orderbooks:
            return MarketData(
                exchange=self.name,
                symbol=symbol,
                bid=self.orderbooks[symbol]["bid"],
                ask=self.orderbooks[symbol]["ask"],
                funding_rate=self.funding_rates.get(symbol, 0.0),
                timestamp=datetime.now()
            )
        return None
    
    async def get_instruments(self) -> List[str]:
        """Получение списка торговых инструментов (возвращает canonical формат)"""
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.REST_URL}/futures/usdt/contracts") as resp:
                data = await resp.json()
                
                if isinstance(data, list):
                    # Gate возвращает BTC_USDT → нормализуем в BTCUSDT
                    raw_symbols = [item["name"] for item in data if not item.get("in_delisting")]
                    self.instruments = [self.to_canonical(s) for s in raw_symbols]
                    return self.instruments
                
                return []
    
    def _sign_gate(self, method: str, url: str, query: str = "", body: str = "") -> Dict[str, str]:
        """Gate.io подпись"""
        timestamp = str(int(time.time()))
        hashed_payload = hashlib.sha512(body.encode()).hexdigest()
        sign_string = f"{method}\n{url}\n{query}\n{hashed_payload}\n{timestamp}"
        signature = hmac.new(self.api_secret.encode(), sign_string.encode(), hashlib.sha512).hexdigest()
        
        return {
            "KEY": self.api_key,
            "Timestamp": timestamp,
            "SIGN": signature
        }
    
    async def place_order(self, symbol: str, side: str, size: float, order_type: str = 'market') -> Dict:
        """Размещение ордера"""
        if not self.api_key or not self.api_secret:
            raise ValueError("API credentials required")
        
        from order_utils import calculate_order_qty, map_order_side
        
        # Получаем текущую цену
        current_price = self.orderbooks.get(symbol, {}).get("ask" if side == "LONG" else "bid", 0)
        if not current_price:
            raise ValueError(f"No market data for {symbol}")
        
        # Правильный расчёт количества
        qty = calculate_order_qty(symbol, size, current_price, leverage=5)
        
        # Маппинг стороны ордера (Gate: 1=buy, -1=sell)
        side_multiplier = map_order_side('gate', side, is_close=False)
        
        # Конвертируем symbol в формат биржи
        exchange_symbol = self._exchange_format_symbol(symbol)
        
        settle = "usdt"
        url = f"/api/v4/futures/{settle}/orders"
        body = json.dumps({
            "contract": exchange_symbol,
            "size": int(qty * side_multiplier),  # Положительное для buy, отрицательное для sell
            "price": "0",
            "tif": "ioc"
        })
        
        headers = self._sign_gate("POST", url, "", body)
        headers["Content-Type"] = "application/json"
        
        async def _make_request():
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.REST_URL}{url}", data=body, headers=headers) as resp:
                    if resp.status == 429:
                        raise Exception("429 Rate limit exceeded")
                    return await resp.json()
        
        return await self._rate_limited_request(_make_request)
    
    async def close_position(self, symbol: str, side: str) -> Dict:
        """Закрытие позиции"""
        if not self.api_key or not self.api_secret:
            raise ValueError("API credentials required")
        
        # Конвертируем symbol в формат биржи
        exchange_symbol = self._exchange_format_symbol(symbol)
        
        settle = "usdt"
        url = f"/api/v4/futures/{settle}/positions/{exchange_symbol}/close"
        body = json.dumps({})
        
        headers = self._sign_gate("POST", url, "", body)
        headers["Content-Type"] = "application/json"
        
        async def _make_request():
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.REST_URL}{url}", data=body, headers=headers) as resp:
                    if resp.status == 429:
                        raise Exception("429 Rate limit exceeded")
                    return await resp.json()
        
        return await self._rate_limited_request(_make_request)
    
    async def get_balance(self) -> float:
        """Получение баланса"""
        if not self.api_key or not self.api_secret:
            raise ValueError("API credentials required")
        
        settle = "usdt"
        url = f"/api/v4/futures/{settle}/accounts"
        
        headers = self._sign_gate("GET", url)
        
        async def _make_request():
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.REST_URL}{url}", headers=headers) as resp:
                    if resp.status == 429:
                        raise Exception("429 Rate limit exceeded")
                    data = await resp.json()
                    return float(data.get("available", 0))
        
        return await self._rate_limited_request(_make_request)
