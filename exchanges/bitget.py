"""Bitget exchange connector"""
import asyncio
import json
import time
from datetime import datetime
from typing import List
import aiohttp
from .base import BaseExchange
from core.models import MarketData


class BitgetExchange(BaseExchange):
    """Bitget exchange implementation"""
    
    def __init__(self):
        super().__init__("Bitget")
        self.ws_url = "wss://ws.bitget.com/v2/ws/public"
        self.rest_url = "https://api.bitget.com"
        self.orderbooks = {}
        self.funding_rates = {}
        
    async def connect_ws(self):
        """Connect to WebSocket"""
        self.ws = await self.session.ws_connect(self.ws_url)
    
    async def _ping_loop(self):
        """Heartbeat (not needed for Bitget v2)"""
        pass
    
    async def get_instruments(self) -> List[str]:
        """Get list of USDT-M perpetual contracts"""
        async with self.session.get(
            f"{self.rest_url}/api/v2/mix/market/contracts",
            params={"productType": "USDT-FUTURES"}
        ) as resp:
            result = await resp.json()
            data = result.get("data", [])
            if not data:
                print(f"Bitget API response: {result}")
                return []
            return [
                item["symbol"]
                for item in data
                if item.get("symbolStatus") == "normal"
            ]
    
    async def subscribe_orderbook(self, symbols: List[str]):
        """Subscribe to depth updates"""
        args = []
        for symbol in symbols:
            args.append({
                "instType": "USDT-FUTURES",
                "channel": "books15",
                "instId": symbol
            })
        await self.ws.send_json({
            "op": "subscribe",
            "args": args
        })
    
    async def subscribe_funding_rate(self, symbols: List[str]):
        """Subscribe to ticker updates (contains funding rate)"""
        args = []
        for symbol in symbols:
            args.append({
                "instType": "USDT-FUTURES",
                "channel": "ticker",
                "instId": symbol
            })
        await self.ws.send_json({
            "op": "subscribe",
            "args": args
        })
    
    async def get_market_data(self, symbol: str) -> MarketData:
        """Get market data from WebSocket stream"""
        while True:
            try:
                msg = await self.ws.receive()
                if msg.type == aiohttp.WSMsgType.TEXT:
                    if msg.data == "pong":
                        continue
                        
                    data = json.loads(msg.data)
                    
                    # Skip subscription confirmations
                    if data.get("event") == "subscribe":
                        continue
                    
                    action = data.get("action")
                    arg = data.get("arg", {})
                    channel = arg.get("channel")
                    
                    # Orderbook data
                    if channel == "books15":
                        for item in data.get("data", []):
                            sym = item.get("instId")
                            asks = item.get("asks", [])
                            bids = item.get("bids", [])
                            
                            if sym and asks and bids:
                                self.orderbooks[sym] = {
                                    "bid": float(bids[0][0]),
                                    "ask": float(asks[0][0])
                                }
                    
                    # Funding rate from ticker
                    elif channel == "ticker":
                        for item in data.get("data", []):
                            sym = item.get("instId")
                            funding_rate = item.get("fundingRate")
                            
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
                print(f"Bitget WS error: {e}")
                await asyncio.sleep(1)
    
    async def place_order(self, symbol: str, side: str, size: float, order_type: str = 'market'):
        raise NotImplementedError("Trading not implemented yet")
    
    async def close_position(self, symbol: str, side: str):
        raise NotImplementedError("Trading not implemented yet")
    
    async def get_balance(self) -> float:
        raise NotImplementedError("Trading not implemented yet")
