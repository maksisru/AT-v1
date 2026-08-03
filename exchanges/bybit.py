"""Bybit exchange connector"""
import asyncio
import json
from datetime import datetime
from typing import List
import aiohttp
from .base import BaseExchange
from .auth_utils import sign_request_hmac, get_timestamp_ms
from core.models import MarketData


class BybitExchange(BaseExchange):
    """Bybit exchange implementation"""
    
    def __init__(self, api_key: str = "", api_secret: str = ""):
        super().__init__("bybit", api_key, api_secret)  # Lowercase для совместимости с config
        self.ws_url = "wss://stream.bybit.com/v5/public/linear"
        self.rest_url = "https://api.bybit.com"
        self.orderbooks = {}
        self.funding_rates = {}
        self.ws_running = False
        self._ping_task = None
    
    async def start_websocket_listener(self, symbols: List[str]):
        """Запуск WebSocket слушателя с автоматическим реконнектом"""
        # 🔒 Жесткая блокировка повторного запуска
        if hasattr(self, '_is_listening') and self._is_listening:
            return
        self._is_listening = True
        
        self.ws_running = True
        
        # Для Bybit нужна aiohttp сессия
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        while self.ws_running:
            try:
                # 🔧 FIX: Закрываем старое соединение перед реконнектом
                if self._ping_task:
                    self._ping_task.cancel()
                    self._ping_task = None
                
                if hasattr(self, 'ws') and self.ws:
                    try:
                        await self.ws.close()
                    except Exception:
                        pass
                    self.ws = None
                
                await self.connect_ws()
                await self.subscribe_orderbook(symbols)
                await self.subscribe_funding_rate(symbols)  # 🔧 FIX: Добавлена подписка на funding
                
                # 🔧 FIX: Явный receive() вместо async for для предотвращения race condition
                while self.ws_running and self.ws:
                    try:
                        msg = await self.ws.receive()
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            await self._handle_message(data)
                        elif msg.type == aiohttp.WSMsgType.CLOSED:
                            print("⚠️ Bybit WS connection closed, reconnecting...")
                            break
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            print("⚠️ Bybit WS error, reconnecting...")
                            break
                    except Exception as e:
                        print(f"⚠️ Bybit receive error: {e}")
                        break
                        
            except Exception as e:
                print(f"❌ Bybit WebSocket error: {e}, reconnecting...")
                if self._ping_task:
                    self._ping_task.cancel()
                await asyncio.sleep(2)
    
    async def stop_websocket(self):
        """Остановка WebSocket"""
        self.ws_running = False
        if self._ping_task:
            self._ping_task.cancel()
        if self.ws:
            await self.ws.close()
    
    def _normalize_symbol(self, symbol: str) -> str:
        """Нормализация символа к canonical формату BTCUSDT"""
        return self.to_canonical(symbol)
    
    def _exchange_format_symbol(self, symbol: str) -> str:
        """Конвертация BTCUSDT в формат биржи BTCUSDT (для Bybit одинаково)"""
        return self.to_local(symbol)
    
    async def _handle_message(self, data: dict):
        """Обработка входящего сообщения"""
        # print(f"🔍 BYBIT RAW MESSAGE: {data}")  # Отладка отключена
        try:
            # Пропускаем служебные сообщения
            if data.get("op") in ["pong", "subscribe"]:
                return
            
            topic = data.get("topic", "")
            
            # Orderbook data
            if topic.startswith("orderbook"):
                result = data.get("data", {})
                sym = result.get("s")
                bids = result.get("b", [])
                asks = result.get("a", [])
                
                if sym and bids and asks:
                    symbol = self._normalize_symbol(sym)
                    self.orderbooks[symbol] = {
                        "bid": float(bids[0][0]),
                        "ask": float(asks[0][0])
                    }
                    # print(f"✅ BYBIT orderbook saved: {symbol}")
            
            # Funding rate from tickers
            elif topic.startswith("tickers"):
                result = data.get("data", {})
                sym = result.get("symbol")
                funding_rate = result.get("fundingRate")
                
                if sym and funding_rate is not None:
                    symbol = self._normalize_symbol(sym)
                    self.funding_rates[symbol] = float(funding_rate)
                    # print(f"✅ BYBIT funding rate saved: {symbol}")
        except Exception as e:
            print(f"⚠️ Bybit message parse error: {e}")
        
    async def connect_ws(self):
        """Connect to WebSocket"""
        self.ws = await self.session.ws_connect(self.ws_url)
        self._ping_task = asyncio.create_task(self._ping_loop())
        print(f"✅ Bybit WebSocket connected")
        
    async def _ping_loop(self):
        """Heartbeat to keep connection alive"""
        while True:
            await asyncio.sleep(20)
            if self.ws:
                await self.ws.send_json({"op": "ping"})
    
    async def get_instruments(self) -> List[str]:
        """Get list of tradeable perpetual contracts (возвращает canonical формат)"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.rest_url}/v5/market/instruments-info",
                    params={"category": "linear"}
                ) as resp:
                    data = await resp.json()
                    # Bybit уже возвращает BTCUSDT (canonical), но на всякий случай нормализуем
                    raw_symbols = [
                        item["symbol"]
                        for item in data.get("result", {}).get("list", [])
                        if item.get("status") == "Trading"
                    ]
                    return [self.to_canonical(s) for s in raw_symbols]
        except Exception as e:
            print(f"Bybit get_instruments error: {e}")
            return []
    
    async def subscribe_orderbook(self, symbols: List[str]):
        """Subscribe to orderbook updates"""
        for symbol in symbols:
            exchange_symbol = self._exchange_format_symbol(symbol)
            await self.ws.send_json({
                "op": "subscribe",
                "args": [f"orderbook.50.{exchange_symbol}"]
            })
    
    async def subscribe_funding_rate(self, symbols: List[str]):
        """Subscribe to funding rate updates"""
        for symbol in symbols:
            exchange_symbol = self._exchange_format_symbol(symbol)
            await self.ws.send_json({
                "op": "subscribe",
                "args": [f"tickers.{exchange_symbol}"]
            })
    
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
    
    async def place_order(self, symbol: str, side: str, size: float, order_type: str = 'market'):
        """Открытие позиции"""
        if not self.api_key or not self.api_secret:
            raise ValueError("API credentials required")
        
        from order_utils import calculate_order_qty, map_order_side
        
        # Получаем текущую цену
        current_price = self.orderbooks.get(symbol, {}).get("ask" if side == "LONG" else "bid", 0)
        if not current_price:
            raise ValueError(f"No market data for {symbol}")
        
        # Правильный расчёт количества
        qty = calculate_order_qty(symbol, size, current_price, leverage=5)
        
        # Маппинг стороны ордера (Bybit: Buy/Sell)
        side_api = map_order_side('bybit', side, is_close=False)
        
        # Конвертируем symbol в формат биржи (для Bybit = canonical)
        exchange_symbol = self._exchange_format_symbol(symbol)
        
        async def _make_request():
            try:
                timestamp = get_timestamp_ms()
                
                # Body для POST запроса
                body = {
                    "category": "linear",
                    "symbol": exchange_symbol,
                    "side": side_api,  # Используем правильный маппинг
                    "orderType": order_type.capitalize(),
                    "qty": str(qty)  # Используем правильно рассчитанное количество
                }
                
                body_json = json.dumps(body)
                recv_window = "5000"
                
                # Подпись для v5 API
                sign_string = f"{timestamp}{self.api_key}{recv_window}{body_json}"
                signature = sign_request_hmac(self.api_secret, sign_string)
                
                headers = {
                    "X-BAPI-API-KEY": self.api_key,
                    "X-BAPI-SIGN": signature,
                    "X-BAPI-TIMESTAMP": str(timestamp),
                    "X-BAPI-RECV-WINDOW": recv_window,
                    "Content-Type": "application/json"
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.rest_url}/v5/order/create",
                        data=body_json,
                        headers=headers
                    ) as resp:
                        if resp.status == 429:
                            raise Exception("429 Rate limit exceeded")
                        data = await resp.json()
                        if data.get("retCode") == 0:
                            return data["result"]
                        else:
                            raise Exception(f"Bybit order error: {data.get('retMsg')}")
            except Exception as e:
                print(f"Bybit place_order error: {e}")
                raise
        
        return await self._rate_limited_request(_make_request)
    
    async def close_position(self, symbol: str, side: str):
        """Закрытие позиции"""
        if not self.api_key or not self.api_secret:
            raise ValueError("API credentials required")
        
        # Конвертируем symbol в формат биржи
        exchange_symbol = self._exchange_format_symbol(symbol)
        
        async def _make_request():
            timestamp = get_timestamp_ms()
            params = {
                "category": "linear",
                "symbol": exchange_symbol,
                "timestamp": timestamp,
                "recv_window": 5000
            }
            
            query_string = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
            signature = sign_request_hmac(self.api_secret, f"{timestamp}{self.api_key}{5000}{query_string}")
            
            headers = {
                "X-BAPI-API-KEY": self.api_key,
                "X-BAPI-SIGN": signature,
                "X-BAPI-TIMESTAMP": str(timestamp),
                "X-BAPI-RECV-WINDOW": "5000"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.rest_url}/v5/position/close", json=params, headers=headers) as resp:
                    if resp.status == 429:
                        raise Exception("429 Rate limit exceeded")
                    return await resp.json()
        
        return await self._rate_limited_request(_make_request)
    
    async def get_balance(self) -> float:
        """Получение баланса"""
        if not self.api_key or not self.api_secret:
            return 10000.0  # Demo режим
        
        async def _make_request():
            try:
                timestamp = get_timestamp_ms()
                params = {
                    "accountType": "UNIFIED",
                    "timestamp": timestamp,
                    "recv_window": 5000
                }
                
                query_string = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
                signature = sign_request_hmac(self.api_secret, f"{timestamp}{self.api_key}{5000}{query_string}")
                
                headers = {
                    "X-BAPI-API-KEY": self.api_key,
                    "X-BAPI-SIGN": signature,
                    "X-BAPI-TIMESTAMP": str(timestamp),
                    "X-BAPI-RECV-WINDOW": "5000"
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{self.rest_url}/v5/account/wallet-balance",
                        params=params,
                        headers=headers
                    ) as resp:
                        if resp.status == 429:
                            raise Exception("429 Rate limit exceeded")
                        data = await resp.json()
                        if data.get("result") and data["result"].get("list"):
                            return float(data["result"]["list"][0].get("totalAvailableBalance", 0))
                        return 0.0
            except Exception as e:
                print(f"Bybit get_balance error: {e}")
                return 10000.0
        
        return await self._rate_limited_request(_make_request)
