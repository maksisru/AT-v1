"""Диагностика множителей контрактов через REST API"""
import urllib.request
import json


def fetch_gate_contract_info(symbol: str):
    """Получает спецификацию контракта от Gate.io"""
    url = "https://fx-api.gateio.ws/api/v4/futures/usdt/contracts"
    contract = symbol.replace("USDT", "_USDT")
    
    with urllib.request.urlopen(url) as resp:
        contracts = json.loads(resp.read())
        for c in contracts:
            if c.get("name") == contract:
                return {
                    "contract": c.get("name"),
                    "quanto_multiplier": c.get("quanto_multiplier", 1.0),
                    "order_size_min": c.get("order_size_min", 0),
                    "order_size_max": c.get("order_size_max", 0),
                }
    return None


def fetch_bybit_contract_info(symbol: str):
    """Получает спецификацию контракта от Bybit"""
    url = f"https://api.bybit.com/v5/market/instruments-info?category=linear&symbol={symbol}"
    
    with urllib.request.urlopen(url) as resp:
        data = json.loads(resp.read())
        if data.get("retCode") == 0:
            result = data.get("result", {}).get("list", [])
            if result:
                info = result[0]
                return {
                    "symbol": info.get("symbol"),
                    "contract_type": info.get("contractType"),
                    "launch_time": info.get("launchTime"),
                }
    return None


def diagnose_edge_anomaly():
    """Диагностирует аномалию EDGEUSDT"""
    print("🔍 Диагностика EDGEUSDT аномалии\n")
    
    # Gate
    gate_info = fetch_gate_contract_info("EDGEUSDT")
    print(f"📊 Gate.io EDGE_USDT:")
    print(f"   {gate_info}\n")
    
    # Bybit
    bybit_info = fetch_bybit_contract_info("EDGEUSDT")
    print(f"📊 Bybit EDGEUSDT:")
    print(f"   {bybit_info}\n")
    
    # Вычисляем соотношение цен
    gate_price = 0.06532  # из CSV
    bybit_price = 0.4655  # из CSV
    ratio = bybit_price / gate_price
    print(f"💡 Соотношение цен: {bybit_price} / {gate_price} = {ratio:.2f}x")
    
    if gate_info:
        multiplier = gate_info.get("quanto_multiplier", 1.0)
        print(f"   Gate quanto_multiplier: {multiplier}")
        print(f"   Normalized Gate: {gate_price * multiplier:.6f}")


if __name__ == "__main__":
    diagnose_edge_anomaly()
