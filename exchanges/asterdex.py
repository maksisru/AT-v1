"""AsterDEX exchange connector (Binance Futures-compatible API)"""
import asyncio
import json
from datetime import datetime
from typing import List
import aiohttp
from .base import BaseExchange
from .auth_utils import sign_request_hmac, get_timestamp_ms, build_query_string
from core.models import MarketData


class AsterDEXExchange(BaseExchange):
    """AsterDEX exchange implementation"""
    
    def __init__(self):
        super().__init__("AsterDEX")
        self.ws_url = "wss://fstream.asterdex.com/ws"
        self.rest_url = "https://fapi.asterdex.com"
        self.orderbooks = {}
        self.funding_rates = {}
        
    async def connect_ws(self):
        """Connect to WebSocket stream"""
        self.ws = await self.session.ws_connect(self.ws_url)
        
    async def get_instruments(self) -> List[str]:
        """Get list of trading perpetual futures"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.rest_url}/fapi/v1/exchangeInfo") as resp:
                    data = await resp.json()
                    return [
                        item["symbol"]
                        for item in data.get("symbols", [])
                        if item.get("status") == "TRADING"
                    ]
        except Exception as e:
            print(f"AsterDEX get_instruments error: {e}")
            return []
    
    async def subscribe_orderbook(self, symbols: List[str]):
        """Subscribe to orderbook depth streams"""
        streams = [f"{symbol.lower()}@depth20@100ms" for symbol in symbols]
        await self.ws.send_json({
            "method": "SUBSCRIBE",
            "params": streams,
            "id": 1
        })
    
    async def subscribe_funding_rate(self, symbols: List[str]):
        """Subscribe to mark price streams (contains funding rate)"""
        streams = [f"{symbol.lower()}@markPrice@1s" for symbol in symbols]
        await self.ws.send_json({
            "method": "SUBSCRIBE",
            "params": streams,
            "id": 2
        })
    
    async def get_market_data(self, symbol: str) -> MarketData:
        """Get market data from WebSocket stream"""
        while True:
            try:
                msg = await self.ws.receive()
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    
                    # Skip subscription responses
                    if "result" in data:
                        continue
                    
                    # Depth stream
                    if data.get("e") == "depthUpdate":
                        sym = data.get("s", "").upper()
                        bids = data.get("b", [])
                        asks = data.get("a", [])
                        
                        if sym and bids and asks:
                            self.orderbooks[sym] = {
                                "bid": float(bids[0][0]),
                                "ask": float(asks[0][0])
                            }
                    
                    # Mark price stream (contains funding rate)
                    elif data.get("e") == "markPriceUpdate":
                        sym = data.get("s", "").upper()
                        funding_rate = data.get("r")
                        
                        if sym and funding_rate is not None:
                            self.funding_rates[sym] = float(funding_rate)
                    
                    # Return data if we have both
                    for sym in list(self.orderbooks.keys()):
                        if sym in self.funding_rates:
                            return MarketData(
                                exchange=self.name,
                                symbol=sym,
                                bid=self.orderbooks[sym]["bid"],
                                ask=self.orderbooks[sym]["ask"],
                                funding_rate=self.funding_rates[sym],
                                timestamp=datetime.now()
                            )
                            
            except Exception as e:
                print(f"AsterDEX WS error: {e}")
                await asyncio.sleep(1)
    
    async def place_order(self, symbol: str, side: str, size: float, order_type: str = 'market'):
        """Открытие позиции (Binance-совместимый)"""
        if not self.api_key or not self.api_secret:
            raise ValueError("API credentials required")
        
        async def _make_request():
            timestamp = get_timestamp_ms()
            params = {
                "symbol": symbol,
                "side": side.upper(),
                "type": order_type.upper(),
                "quantity": str(size),
                "timestamp": timestamp
            }
            
            query_string = build_query_string(params)
            signature = sign_request_hmac(self.api_secret, query_string)
            params["signature"] = signature
            
            headers = {"X-MBX-APIKEY": self.api_key}
            
            async with self.session.post(f"{self.rest_url}/fapi/v1/order", params=params, headers=headers) as resp:
                if resp.status == 429:
                    raise Exception("429 Rate limit exceeded")
                return await resp.json()
        
        return await self._rate_limited_request(_make_request)
    
    async def close_position(self, symbol: str, side: str):
        """Закрытие позиции"""
        if not self.api_key or not self.api_secret:
            raise ValueError("API credentials required")
        
        async def _make_request():
            timestamp = get_timestamp_ms()
            params = {
                "symbol": symbol,
                "timestamp": timestamp
            }
            
            query_string = build_query_string(params)
            signature = sign_request_hmac(self.api_secret, query_string)
            params["signature"] = signature
            
            headers = {"X-MBX-APIKEY": self.api_key}
            
            async with self.session.delete(f"{self.rest_url}/fapi/v1/allOpenOrders", params=params, headers=headers) as resp:
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
                    "timestamp": timestamp
                }
                
                query_string = build_query_string(params)
                signature = sign_request_hmac(self.api_secret, query_string)
                params["signature"] = signature
                
                headers = {"X-MBX-APIKEY": self.api_key}
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{self.rest_url}/fapi/v2/account",
                        params=params,
                        headers=headers
                    ) as resp:
                        if resp.status == 429:
                            raise Exception("429 Rate limit exceeded")
                        data = await resp.json()
                        if data.get("assets"):
                            return float(data["assets"][0].get("availableBalance", 0))
                        return 0.0
            except Exception as e:
                print(f"AsterDEX get_balance error: {e}")
                return 10000.0
        
        return await self._rate_limited_request(_make_request)
