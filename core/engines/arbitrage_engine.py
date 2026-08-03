"""Arbitrage Engine — расчёт спредов и поиск возможностей"""
from typing import List, Dict
from core.models import MarketData, ArbitragePair
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from collections import deque
import threading
from exchanges.normalize import validate_spread


class ArbitrageEngine:
    """Анализ арбитражных возможностей"""
    
    def __init__(self, max_workers: int = 4):
        self.spread_history = []
        self.stats = {
            "total_opportunities": 0,
            "spreads": deque(maxlen=10000)  # Ограничение 10k последних спредов
        }
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.stats_lock = threading.Lock()  # Защита от race condition
        
        # ИСПРАВЛЕНИЕ #2: История спредов для детекции тренда
        self.spread_trend_history: Dict[str, deque] = {}
        self.TREND_WINDOW = 5  # Последние 5 измерений (500ms при 100ms интервале)
    
    def calculate_gross_spread(self, long_data: MarketData, short_data: MarketData) -> float:
        """Расчёт gross спреда БЕЗ учёта funding rate"""
        raw_spread = (short_data.bid - long_data.ask) / long_data.ask * 100
        return raw_spread
    
    def calculate_effective_spread(self, long_data: MarketData, short_data: MarketData) -> float:
        """Расчёт эффективного спреда с учётом funding rate"""
        # Спред: цена где покупаем - цена где продаём
        raw_spread = self.calculate_gross_spread(long_data, short_data)
        
        # Разница funding rates (платим на шорт, получаем на лонг)
        # Funding rate уже в процентах! (0.0001 = 0.01%)
        funding_diff = short_data.funding_rate - long_data.funding_rate
        
        # Эффективный спред
        effective = raw_spread - funding_diff
        
        return effective
    
    def _get_pair_key(self, ex_long: str, ex_short: str, symbol: str) -> str:
        """Генерация ключа пары для истории спредов"""
        return f"{ex_long}|{ex_short}|{symbol}"
    
    def _get_spread_trend(self, pair_key: str, current_spread: float) -> str:
        """
        Определяет тренд спреда: 'expanding', 'stable', 'collapsing'
        
        Expanding: спред растёт → хороший момент для входа
        Stable: спред не меняется → нейтральный вход
        Collapsing: спред падает → НЕ ВХОДИТЬ, возможность исчезает
        """
        if pair_key not in self.spread_trend_history:
            self.spread_trend_history[pair_key] = deque(maxlen=self.TREND_WINDOW)
        
        history = self.spread_trend_history[pair_key]
        history.append(current_spread)
        
        if len(history) < 3:
            return 'unknown'
        
        # Линейная регрессия: знак наклона определяет тренд
        values = list(history)
        n = len(values)
        mean_x = (n - 1) / 2
        mean_y = sum(values) / n
        
        numerator = sum((i - mean_x) * (v - mean_y) for i, v in enumerate(values))
        denominator = sum((i - mean_x) ** 2 for i in range(n))
        
        if denominator == 0:
            return 'stable'
        
        slope = numerator / denominator  # % per iteration
        
        if slope > 0.05:   # Растёт более 0.05% за итерацию
            return 'expanding'
        elif slope < -0.05:  # Падает более 0.05% за итерацию
            return 'collapsing'
        else:
            return 'stable'
    
    def _check_pair_batch(self, pairs_batch, threshold):
        """Проверка батча пар (для параллелизма)"""
        opportunities = []
        
        for ex_long, ex_short, symbol, data_long, data_short in pairs_batch:
            # 🛡️ Circuit Breaker: фильтруем аномалии
            if not validate_spread(ex_long, ex_short, symbol, data_long.ask, data_short.bid):
                continue
            
            # Стратегия 1
            spread1 = self.calculate_effective_spread(data_long, data_short)
            if spread1 > threshold:
                pair_key = self._get_pair_key(ex_long, ex_short, symbol)
                trend = self._get_spread_trend(pair_key, spread1)
                
                # ИСПРАВЛЕНИЕ #2: НЕ входим если спред уже схлопывается
                if trend == 'collapsing':
                    continue
                
                funding_diff_1 = data_short.funding_rate - data_long.funding_rate
                opp = ArbitragePair(
                    exchange_long=ex_long, exchange_short=ex_short,
                    symbol=symbol, spread=spread1,
                    funding_diff=funding_diff_1,
                    price_long=data_long.ask, price_short=data_short.bid,
                    timestamp=datetime.now(),
                    data_long=data_long, data_short=data_short,
                    effective_spread=spread1 - abs(funding_diff_1) * 100,
                    spread_trend=trend
                )
                opportunities.append(opp)
                with self.stats_lock:
                    self.stats["spreads"].append(spread1)
            
            # 🛡️ Circuit Breaker: обратное направление
            if not validate_spread(ex_short, ex_long, symbol, data_short.ask, data_long.bid):
                continue
            
            # Стратегия 2
            spread2 = self.calculate_effective_spread(data_short, data_long)
            if spread2 > threshold:
                pair_key = self._get_pair_key(ex_short, ex_long, symbol)
                trend = self._get_spread_trend(pair_key, spread2)
                
                # ИСПРАВЛЕНИЕ #2: НЕ входим если спред уже схлопывается
                if trend == 'collapsing':
                    continue
                
                funding_diff_2 = data_long.funding_rate - data_short.funding_rate
                opp = ArbitragePair(
                    exchange_long=ex_short, exchange_short=ex_long,
                    symbol=symbol, spread=spread2,
                    funding_diff=funding_diff_2,
                    price_long=data_short.ask, price_short=data_long.bid,
                    timestamp=datetime.now(),
                    data_long=data_short, data_short=data_long,
                    effective_spread=spread2 - abs(funding_diff_2) * 100,
                    spread_trend=trend
                )
                opportunities.append(opp)
                with self.stats_lock:
                    self.stats["spreads"].append(spread2)
        
        return opportunities
    
    def find_opportunities_parallel(self, market_data: Dict[str, Dict[str, MarketData]], threshold: float, batch_size: int = 50) -> List[ArbitragePair]:
        """Параллельный поиск возможностей (батчинг)"""
        exchanges = list(market_data.keys())
        
        # Собираем все пары
        all_pairs = []
        for i, ex_long in enumerate(exchanges):
            for ex_short in exchanges[i+1:]:
                symbols_long = set(market_data[ex_long].keys())
                symbols_short = set(market_data[ex_short].keys())
                common_symbols = symbols_long & symbols_short
                
                for symbol in common_symbols:
                    data_long = market_data[ex_long][symbol]
                    data_short = market_data[ex_short][symbol]
                    all_pairs.append((ex_long, ex_short, symbol, data_long, data_short))
        
        # Разбиваем на батчи
        batches = [all_pairs[i:i+batch_size] for i in range(0, len(all_pairs), batch_size)]
        
        # Параллельная обработка батчей
        futures = [self.executor.submit(self._check_pair_batch, batch, threshold) for batch in batches]
        
        # Собираем результаты
        opportunities = []
        for future in futures:
            opportunities.extend(future.result())
        
        # Защита от race condition
        with self.stats_lock:
            self.stats["total_opportunities"] += len(opportunities)
        
        opportunities.sort(key=lambda x: x.spread, reverse=True)
        
        return opportunities
    
    def find_opportunities(self, market_data: Dict[str, Dict[str, MarketData]], threshold: float) -> List[ArbitragePair]:
        """Поиск арбитражных возможностей (последовательная версия для совместимости)"""
        opportunities = []
        exchanges = list(market_data.keys())
        
        # Собираем все комбинации для параллельной обработки
        pairs_to_check = []
        
        for i, ex_long in enumerate(exchanges):
            for ex_short in exchanges[i+1:]:
                symbols_long = set(market_data[ex_long].keys())
                symbols_short = set(market_data[ex_short].keys())
                common_symbols = symbols_long & symbols_short
                
                for symbol in common_symbols:
                    data_long = market_data[ex_long][symbol]
                    data_short = market_data[ex_short][symbol]
                    pairs_to_check.append((ex_long, ex_short, symbol, data_long, data_short))
        
        # Параллельно проверяем все пары
        for ex_long, ex_short, symbol, data_long, data_short in pairs_to_check:
            # Стратегия 1: LONG на ex_long, SHORT на ex_short
            effective_spread = self.calculate_effective_spread(data_long, data_short)
            
            if effective_spread > threshold:
                # Сохраняем GROSS spread (без funding) для корректной записи
                gross_spread = self.calculate_gross_spread(data_long, data_short)
                
                opp = ArbitragePair(
                    exchange_long=ex_long,
                    exchange_short=ex_short,
                    symbol=symbol,
                    spread=gross_spread,  # GROSS, не effective!
                    funding_diff=data_short.funding_rate - data_long.funding_rate,
                    price_long=data_long.ask,
                    price_short=data_short.bid,
                    timestamp=datetime.now(),
                    data_long=data_long,
                    data_short=data_short
                )
                opportunities.append(opp)
                with self.stats_lock:
                    self.stats["total_opportunities"] += 1
                    self.stats["spreads"].append(gross_spread)  # Используем gross для статистики
            
            # Стратегия 2: LONG на ex_short, SHORT на ex_long
            effective_spread2 = self.calculate_effective_spread(data_short, data_long)
            
            if effective_spread2 > threshold:
                gross_spread2 = self.calculate_gross_spread(data_short, data_long)
                
                opp = ArbitragePair(
                    exchange_long=ex_short,
                    exchange_short=ex_long,
                    symbol=symbol,
                    spread=gross_spread2,  # GROSS, не effective!
                    funding_diff=data_long.funding_rate - data_short.funding_rate,
                    price_long=data_short.ask,
                    price_short=data_long.bid,
                    timestamp=datetime.now(),
                    data_long=data_short,
                    data_short=data_long
                )
                opportunities.append(opp)
                with self.stats_lock:
                    self.stats["total_opportunities"] += 1
                    self.stats["spreads"].append(gross_spread2)
        
        # Сортировка по спреду (топ возможности первыми)
        opportunities.sort(key=lambda x: x.spread, reverse=True)
        
        return opportunities
    
    def get_statistics(self) -> Dict:
        """Получить статистику"""
        if not self.stats["spreads"]:
            return {
                "total_opportunities": 0,
                "avg_spread": 0,
                "max_spread": 0
            }
        
        return {
            "total_opportunities": self.stats["total_opportunities"],
            "avg_spread": sum(self.stats["spreads"]) / len(self.stats["spreads"]),
            "max_spread": max(self.stats["spreads"])
        }
    
    def shutdown(self):
        """Безопасное закрытие ThreadPoolExecutor"""
        if hasattr(self, 'executor') and self.executor:
            print("[ArbitrageEngine] Завершение работы пула потоков...")
            self.executor.shutdown(wait=True, cancel_futures=False)
            print("[ArbitrageEngine] Пул потоков закрыт")
            self.executor = None
    
    def __del__(self):
        """Автоматическое закрытие при удалении объекта"""
        self.shutdown()

