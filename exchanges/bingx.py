"""BingX exchange connector"""
import asyncio
import json
import time
from datetime import datetime
from typing import List
import aiohttp
from .base import BaseExchange
from core.models import MarketData


class BingXExchange(BaseExchange):
    """BingX exchange implementation"""
    
    def __init__(self):
        super().__init__("BingX")
        self.ws_url = "wss://open-api-swap.bingx.com/swap-market"
        self.rest_url = "https://open-api.bingx.com"
        self.orderbooks = {}
        self.funding_rates = {}
        
    async def connect_ws(self):
        """Connect to WebSocket"""
        self.ws = await self.session.ws_connect(self.ws_url)
    
    async def _ping_loop(self):
        """Heartbeat (not needed - server sends pings)"""
        pass
    
    async def get_instruments(self) -> List[str]:
        """Get list of perpetual swap contracts"""
        async with self.session.get(
            f"{self.rest_url}/openApi/swap/v2/quote/contracts"
        ) as resp:
            data = await resp.json()
            return [
                item["symbol"]
                for item in data.get("data", [])
                if item.get("status") == 1
            ]
    
    async def subscribe_orderbook(self, symbols: List[str]):
        """Subscribe to depth updates"""
        for symbol in symbols:
            await self.ws.send_json({
                "id": f"depth_{symbol}",
                "reqType": "sub",
                "dataType": f"{symbol}@depth20"
            })
    
    async def subscribe_funding_rate(self, symbols: List[str]):
        """Subscribe to ticker updates (contains funding rate)"""
        for symbol in symbols:
            await self.ws.send_json({
                "id": f"ticker_{symbol}",
                "reqType": "sub",
                "dataType": f"{symbol}@ticker"
            })
    
    async def get_market_data(self, symbol: str) -> MarketData:
        """Get market data from WebSocket stream"""
        while True:
            try:
                msg = await self.ws.receive()
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    
                    # Skip pong messages
                    if "pong" in data:
                        continue
                    
                    data_type = data.get("dataType", "")
                    
                    # Orderbook data
                    if "@depth" in data_type:
                        result = data.get("data", {})
                        sym = result.get("s")
                        bids = result.get("bids", [])
                        asks = result.get("asks", [])
                        
                        if sym and bids and asks:
                            self.orderbooks[sym] = {
                                "bid": float(bids[0][0]),
                                "ask": float(asks[0][0])
                            }
                    
                    # Funding rate from ticker
                    elif "@ticker" in data_type:
                        result = data.get("data", {})
                        sym = result.get("s")
                        funding_rate = result.get("r")
                        
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
                print(f"BingX WS error: {e}")
                await asyncio.sleep(1)
    
    async def place_order(self, symbol: str, side: str, size: float, order_type: str = 'market'):
        raise NotImplementedError("Trading not implemented yet")
    
    async def close_position(self, symbol: str, side: str):
        raise NotImplementedError("Trading not implemented yet")
    
    async def get_balance(self) -> float:
        raise NotImplementedError("Trading not implemented yet")
