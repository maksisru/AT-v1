"""Главный модуль арбитражной системы"""
import asyncio
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Создание директории для логов и данных
Path("data_collection").mkdir(exist_ok=True)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        RotatingFileHandler('data_collection/arbitrage.log', maxBytes=10*1024*1024, backupCount=5),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

from core.utils.env_loader import get_api_keys, get_telegram_config
from exchanges.mexc import MEXCExchange
from exchanges.gate import GateExchange
from exchanges.bybit import BybitExchange

from core.engines.market_data_engine import MarketDataEngine
from core.engines.arbitrage_engine import ArbitrageEngine
from core.engines.trading_engine import TradingEngine
from core.managers.risk_manager import RiskManager
from core.managers.position_manager import PositionManager
from strategies.strategy_selector import StrategySelector
from utils.telegram_logger import TelegramLogger
from core.analyzers.opportunity_analyzer import OpportunityAnalyzer
from config.opportunity_config import OPPORTUNITY_CONFIG

from config import main_config as config

# Стратегия выбирается динамически
STRATEGY = 'dynamic'  # используется только для отображения

# Импорт производительной конфигурации (если есть)
try:
    from config.performance_config import (
        MAX_WORKERS, SYMBOLS_PER_EXCHANGE, ANALYSIS_INTERVAL,
        STATS_INTERVAL, OPPORTUNITY_DISPLAY_INTERVAL, TOP_OPPORTUNITIES
    )
except ImportError:
    # Дефолтные значения
    MAX_WORKERS = 4
    SYMBOLS_PER_EXCHANGE = 10
    ANALYSIS_INTERVAL = 0.3
    STATS_INTERVAL = 30
    OPPORTUNITY_DISPLAY_INTERVAL = 3
    TOP_OPPORTUNITIES = 5


class ArbitrageSystem:
    """Основная система арбитража"""
    
    def __init__(self, use_api_keys=False, initial_balance=1000, strategy='amplitude', demo_mode=True):
        self.use_api_keys = use_api_keys
        self.initial_balance = initial_balance
        self.strategy_name = strategy
        self.demo_mode = demo_mode
        self.exchanges = {}
        self.market_data_engine = None
        self.arbitrage_engine = None
        self.trading_engine = None
        self.risk_manager = None
        self.strategy_selector = None
        self.position_manager = None
        self.telegram = None
        self.running = False
        self.pairwise_symbols = {}  # Попарные пересечения символов
        self.executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)  # Пул потоков для анализа
        
        # High-spread компоненты
        self.hs_classifier = None
        self.hs_analyzer = None
        self.hs_exit_strategy = None
    
    async def initialize(self):
        """Инициализация всех компонентов"""
        print("\n=== Инициализация ArbitrageSystem ===")
        
        # Создаём коннекторы бирж
        print("\n1. Создание коннекторов бирж...")
        
        if self.use_api_keys:
            print("   📝 Загрузка API ключей из .env...")
            mexc_key, mexc_secret = get_api_keys('mexc')
            gate_key, gate_secret = get_api_keys('gate')
            bybit_key, bybit_secret = get_api_keys('bybit')
            
            self.exchanges = {
                "mexc": MEXCExchange(),
                "gate": GateExchange(),
                "bybit": BybitExchange()
            }
            
            # Устанавливаем API ключи
            self.exchanges["mexc"].api_key = mexc_key
            self.exchanges["mexc"].api_secret = mexc_secret
            self.exchanges["gate"].api_key = gate_key
            self.exchanges["gate"].api_secret = gate_secret
            self.exchanges["bybit"].api_key = bybit_key
            self.exchanges["bybit"].api_secret = bybit_secret
        else:
            self.exchanges = {
                "mexc": MEXCExchange(),
                "gate": GateExchange(),
                "bybit": BybitExchange()
            }
        
        # Инициализируем каждую биржу
        for name, exchange in self.exchanges.items():
            print(f"   - Инициализация {name}...")
            await exchange.initialize()
        
        print("   ✓ Все биржи инициализированы")
        
        # Создаём движки
        print("\n2. Создание движков...")
        self.market_data_engine = MarketDataEngine(self.exchanges)
        self.arbitrage_engine = ArbitrageEngine(max_workers=MAX_WORKERS)  # Параллельный движок
        self.trading_engine = TradingEngine(self.exchanges, demo_mode=self.demo_mode)
        self.risk_manager = RiskManager(initial_balance=self.initial_balance)
        self.opportunity_analyzer = OpportunityAnalyzer(config=OPPORTUNITY_CONFIG)  # Net Edge Strategy
        
        # Динамический селектор стратегий
        self.strategy_selector = StrategySelector()
        
        # Telegram logger (загрузка из .env)
        telegram_bot_token, telegram_chat_id = get_telegram_config()
        self.telegram = TelegramLogger(telegram_bot_token, telegram_chat_id)
        
        # Position Manager
        self.position_manager = PositionManager(
            self.trading_engine,
            self.strategy_selector,
            self.telegram,
            self.risk_manager  # Передаём risk_manager для обновления баланса
        )
        
        # High-spread компоненты
        from core.analyzers.high_spread_classifier import HighSpreadClassifier
        from core.analyzers.high_spread_analyzer import HighSpreadAnalyzer, HIGH_SPREAD_CONFIG
        from core.analyzers.high_spread_exit_strategy import HighSpreadExitStrategy
        
        self.hs_classifier = HighSpreadClassifier()
        self.hs_analyzer = HighSpreadAnalyzer(
            config=HIGH_SPREAD_CONFIG,
            position_size_usd=self.risk_manager.calculate_position_size(),
        )
        self.hs_exit_strategy = HighSpreadExitStrategy()
        
        mode_text = "LIVE" if not self.demo_mode else "DEMO"
        print(f"   ✓ Все движки созданы ({mode_text} режим)")
        print(f"   📊 Стратегия: DYNAMIC (Net Edge) + HIGH-SPREAD")
        print(f"   📊 Баланс: {self.initial_balance} USD")
        print(f"   📊 Размер позиции: {self.risk_manager.calculate_position_size()} USD (1/10 баланса)")
        print(f"   📊 Макс позиций: {config.MAX_OPEN_POSITIONS}")
        print(f"   📊 Min Net Edge: {OPPORTUNITY_CONFIG['MIN_NET_EDGE']}%")
        
        # Уведомление в Telegram
        await self.telegram.log_system_start(
            balance=self.initial_balance,
            strategy=self.strategy_name.upper(),
            exchanges=list(self.exchanges.keys())
        )
        
        print("\n=== Система готова ===\n")
    
    async def run_market_data_collection(self):
        """Запуск сбора рыночных данных"""
        print("📊 Запуск сбора рыночных данных...")
        
        # Получаем попарные пересечения
        pairwise_symbols = await self.market_data_engine.get_common_symbols(limit=None)
        
        # Используем объединение всех пар (уникальные символы)
        all_symbols = set()
        for pair_key, symbols in pairwise_symbols.items():
            if pair_key != 'all':
                all_symbols.update(symbols)
        
        common_symbols = list(all_symbols)
        print(f"   📈 Торговых пар для мониторинга: {len(common_symbols)}")
        
        if len(common_symbols) > 0:
            print(f"   📋 Примеры: {', '.join(list(common_symbols)[:5])}")
        
        # Сохраняем информацию о парах для арбитража
        self.pairwise_symbols = pairwise_symbols
        
        # Подписываемся на данные (запускает фоновые задачи)
        await self.market_data_engine.subscribe_all(common_symbols)
        print("   ✓ Данные поступают в реальном времени")
    
    async def watchdog_positions(self):
        """
        Watchdog: проверяет что все позиции синхронизированы между компонентами.
        Запускается каждые 60 секунд.
        """
        while self.running:
            await asyncio.sleep(60)
            
            try:
                pm_positions = set(self.position_manager.positions.keys())
                te_positions = set(self.trading_engine.open_positions.keys())
                rm_positions = set(self.risk_manager.open_positions.keys())
                
                # Позиции в trading_engine но нет в position_manager (orphaned)
                orphaned = te_positions - pm_positions
                if orphaned:
                    for pair_id in orphaned:
                        trade = self.trading_engine.open_positions[pair_id]
                        logger.error(f"WATCHDOG: orphaned position {pair_id[:8]} ({trade.symbol})")
                        await self.telegram.log_error(
                            "Watchdog: Orphaned Position",
                            f"{trade.symbol} {pair_id[:8]}: in trading_engine but not in position_manager. Closing."
                        )
                        # Аварийное закрытие
                        await self.trading_engine.close_position(pair_id)
                
                # Позиции в position_manager но не в trading_engine (ghost)
                ghost = pm_positions - te_positions
                if ghost:
                    for pair_id in ghost:
                        trade = self.position_manager.positions[pair_id]
                        logger.error(f"WATCHDOG: ghost position {pair_id[:8]} ({trade.symbol})")
                        await self.telegram.log_error(
                            "Watchdog: Ghost Position",
                            f"{trade.symbol}: in position_manager but not in trading_engine. Removing."
                        )
                        del self.position_manager.positions[pair_id]
                        self.risk_manager.unregister_position(pair_id)
                
                # Расхождение в risk_manager
                rm_ghost = rm_positions - pm_positions
                for pair_id in rm_ghost:
                    self.risk_manager.unregister_position(pair_id)
                    
            except Exception as e:
                logger.error(f"Watchdog error: {e}")
    
    async def run_arbitrage_monitoring(self):
        """Непрерывный мониторинг арбитража с автоматическим открытием/закрытием"""
        print(f"\n🔍 Запуск высокопроизводительного мониторинга...")
        print(f"   Потоков: {MAX_WORKERS} | Интервал: {ANALYSIS_INTERVAL*1000:.0f}ms\n")
        
        iteration = 0
        last_stats_time = asyncio.get_event_loop().time()
        last_opportunity_time = 0
        
        while self.running:
            iteration += 1
            current_time = asyncio.get_event_loop().time()
            
            # Получаем данные без блокировки (из кэша)
            market_data = self.market_data_engine.get_latest_data()
            
            if not market_data or not any(market_data.values()):
                await asyncio.sleep(0.05)
                continue
            
            # БАГ #1 FIX: Сначала мониторинг, ПОТОМ открытие новых
            # Это предотвращает гонку между monitor и register_position
            await self.position_manager.monitor_positions(market_data)
            
            # Параллельный анализ возможностей (батчинг в отдельных потоках)
            opportunities = await asyncio.get_event_loop().run_in_executor(
                None,  # Используем дефолтный executor
                self.arbitrage_engine.find_opportunities_parallel,  # Параллельная версия
                market_data,
                config.OPEN_THRESHOLD,
                50  # batch_size
            )
            
            # Показываем возможности
            if opportunities and (current_time - last_opportunity_time) >= OPPORTUNITY_DISPLAY_INTERVAL:
                last_opportunity_time = current_time
                
                # Разделяем на regular и high-spread
                
                regular_opps = []
                high_spread_opps = []
                
                for opp in opportunities:
                    # Проверяем EFFECTIVE spread для high-spread режима
                    if config.HIGH_SPREAD_MODE and opp.effective_spread >= config.HIGH_SPREAD_MIN_PCT:
                        high_spread_opps.append(opp)
                    else:
                        regular_opps.append(opp)
                
                # Обработка HIGH-SPREAD возможностей
                if high_spread_opps:
                    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🔥 HIGH-SPREAD: {len(high_spread_opps)} candidates")
                    
                    for opp in high_spread_opps[:TOP_OPPORTUNITIES]:
                        # 1. Классифицировать
                        classification = self.hs_classifier.classify(opp, market_data)
                        
                        # 2. Получить orderbook для ликвидности
                        ob_long = getattr(self.exchanges.get(opp.exchange_long), "orderbooks", {}).get(opp.symbol, {})
                        ob_short = getattr(self.exchanges.get(opp.exchange_short), "orderbooks", {}).get(opp.symbol, {})
                        
                        # 3. Анализировать
                        analysis = self.hs_analyzer.analyze(opp, classification, ob_long, ob_short)
                        
                        if not analysis.approved:
                            print(f"   ❌ {opp.symbol} {opp.spread:.2f}% {opp.exchange_long}↔{opp.exchange_short}")
                            print(f"      Type: {classification.spread_type.value}, Reason: {analysis.reject_reason}")
                            continue
                        
                        # 4. Risk check
                        risk = self.risk_manager.check_opportunity(opp, market_data)
                        if not risk["approved"]:
                            print(f"   ❌ {opp.symbol} {opp.spread:.2f}% — Risk: {risk['reason']}")
                            continue
                        
                        # 5. Финальная проверка актуальности спреда (ОШИБКА #2 FIX)
                        fresh_data = self.market_data_engine.get_latest_data()
                        long_fresh = fresh_data.get(opp.exchange_long, {}).get(opp.symbol)
                        short_fresh = fresh_data.get(opp.exchange_short, {}).get(opp.symbol)
                        
                        if long_fresh and short_fresh:
                            fresh_spread = (short_fresh.bid - long_fresh.ask) / long_fresh.ask * 100
                            if fresh_spread < config.HIGH_SPREAD_MIN_PCT:
                                print(f"   ⚠️ {opp.symbol} — spread collapsed: {opp.spread:.2f}% → {fresh_spread:.2f}%")
                                continue
                        
                        # 6. Открыть позицию
                        success, pair_id = await self.trading_engine.execute_arbitrage(
                            opp,
                            analysis.effective_position_size,
                            "high_spread",
                        )
                        
                        if success:
                            try:
                                trade = self.trading_engine.get_position(pair_id)
                                if trade is None:
                                    logger.error(f"CRITICAL: trade {pair_id[:8]} not found after execute_arbitrage")
                                    await self.telegram.log_error("Lost Trade", f"{opp.symbol} {pair_id[:8]}: position opened but not tracked")
                                else:
                                    # Сохранить метаданные
                                    trade.hs_spread_type = classification.spread_type.value
                                    trade.hs_max_hold_min = classification.max_hold_minutes
                                    
                                    self.position_manager.register_position(trade)
                                    self.risk_manager.register_position(pair_id, opp.symbol, opp.exchange_long, opp.exchange_short)
                                    
                                    print(f"   ✅ {opp.symbol} {opp.spread:.2f}% OPENED")
                                    print(f"      Type: {classification.spread_type.value}, Net: {analysis.net_edge_pct:.2f}%, Hold: ≤{classification.max_hold_minutes}min")
                            except Exception as e:
                                logger.error(f"CRITICAL: failed to register position {pair_id[:8]}: {e}")
                                await self.telegram.log_error(
                                    "Registration Failed",
                                    f"{opp.symbol}: position OPEN on exchange but NOT tracked! Manual close required. pair_id={pair_id[:8]}"
                                )
                                # Аварийная попытка закрыть
                                try:
                                    await self.trading_engine.close_position(pair_id)
                                except Exception as close_e:
                                    logger.error(f"Emergency close also failed: {close_e}")
                            
                            await self.telegram.log_position_opened(
                                symbol=opp.symbol,
                                exchange_long=opp.exchange_long,
                                exchange_short=opp.exchange_short,
                                spread=opp.spread,
                                position_size=analysis.effective_position_size
                            )
                
                # Анализируем regular opportunities с net edge strategy
                analyzed_opportunities = []
                for opp in regular_opps[:TOP_OPPORTUNITIES * 2]:
                    try:
                        analysis = self.opportunity_analyzer.analyze(opp)
                        analyzed_opportunities.append(analysis)
                    except Exception as e:
                        print(f"⚠️ Ошибка анализа {opp.symbol}: {e}")
                        continue
                
                # Фильтруем одобренные
                approved = [a for a in analyzed_opportunities if a.approved]
                rejected = [a for a in analyzed_opportunities if not a.approved]
                
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 🎯 Найдено {len(opportunities)} возможностей, "
                      f"✅ одобрено {len(approved)}, ❌ отклонено {len(rejected)}")
                
                # Показываем топ одобренных
                for analysis in approved[:TOP_OPPORTUNITIES]:
                    opp = analysis.pair
                    risk_check = self.risk_manager.check_opportunity(opp, market_data, analysis)
                    
                    status = "✅" if risk_check["approved"] else "❌"
                    print(f"   {status} {opp.symbol}: {opp.exchange_long} ↔ {opp.exchange_short}")
                    print(f"      Gross: {analysis.gross_spread_pct:.3f}% → Net Edge: {analysis.net_edge_pct:.3f}%")
                    
                    if risk_check["approved"]:
                        # Финальная проверка актуальности спреда (ОШИБКА #2 FIX)
                        fresh_data = self.market_data_engine.get_latest_data()
                        long_fresh = fresh_data.get(opp.exchange_long, {}).get(opp.symbol)
                        short_fresh = fresh_data.get(opp.exchange_short, {}).get(opp.symbol)
                        
                        if long_fresh and short_fresh:
                            fresh_spread = (short_fresh.bid - long_fresh.ask) / long_fresh.ask * 100
                            
                            # Проверяем что спред не схлопнулся
                            if fresh_spread < opp.spread * 0.9:
                                print(f"      ⚠️ Spread collapsed: {opp.spread:.2f}% → {fresh_spread:.2f}%")
                                continue
                            
                            # Пересчитываем net edge со свежими данными
                            fresh_funding_diff = abs(long_fresh.funding_rate - short_fresh.funding_rate)
                            if fresh_funding_diff > 0.01:
                                print(f"      ⚠️ Funding diff too high: {fresh_funding_diff:.4f}")
                                continue
                        else:
                            print(f"      ⚠️ Fresh data unavailable")
                            continue
                        
                        # Динамический выбор стратегии по спреду
                        strategy, strategy_name = self.strategy_selector.select_strategy(opp.spread)
                        
                        # Автоматическое открытие позиции
                        position_size = risk_check["position_size"]
                        success, pair_id = await self.trading_engine.execute_arbitrage(
                            opp, position_size, strategy_name
                        )
                        
                        if success:
                            try:
                                trade = self.trading_engine.get_position(pair_id)
                                if trade is None:
                                    logger.error(f"CRITICAL: trade {pair_id[:8]} not found after execute_arbitrage")
                                    await self.telegram.log_error("Lost Trade", f"{opp.symbol} {pair_id[:8]}: position opened but not tracked")
                                else:
                                    self.position_manager.register_position(trade)
                                    self.risk_manager.register_position(pair_id, opp.symbol, opp.exchange_long, opp.exchange_short)
                                    
                                    print(f"      ✅ Позиция открыта: {pair_id[:8]}... (стратегия: {strategy_name})")
                                    
                                    await self.telegram.log_position_opened(
                                        symbol=opp.symbol,
                                        exchange_long=opp.exchange_long,
                                        exchange_short=opp.exchange_short,
                                        spread=opp.spread,
                                        position_size=position_size
                                    )
                            except Exception as e:
                                logger.error(f"CRITICAL: failed to register position {pair_id[:8]}: {e}")
                                await self.telegram.log_error(
                                    "Registration Failed",
                                    f"{opp.symbol}: position OPEN on exchange but NOT tracked! Manual close required. pair_id={pair_id[:8]}"
                                )
                                # Аварийная попытка закрыть
                                try:
                                    await self.trading_engine.close_position(pair_id)
                                except Exception as close_e:
                                    logger.error(f"Emergency close also failed: {close_e}")
                    else:
                        print(f"      Причина: {risk_check['reason']}")
                
                print()
            
            # Статистика (только консольный вывод, без Telegram)
            if current_time - last_stats_time >= STATS_INTERVAL:
                stats = self.arbitrage_engine.get_statistics()
                pos_stats = self.position_manager.get_statistics()
                
                print(f"📈 Статистика (итерация {iteration}):")
                print(f"   Возможностей найдено: {stats['total_opportunities']}")
                if stats['total_opportunities'] > 0:
                    print(f"   Средний спред: {stats['avg_spread']:.3f}%")
                    print(f"   Макс спред: {stats['max_spread']:.3f}%")
                
                print(f"   Открытых позиций: {len(self.position_manager.positions)}")
                if pos_stats['total_trades'] > 0:
                    print(f"   Закрытых сделок: {pos_stats['total_trades']}")
                    print(f"   Win rate: {pos_stats['win_rate']:.1f}%")
                    print(f"   Общий PnL: {pos_stats['total_pnl']:+.2f} USD")
                print()
                last_stats_time = current_time
            
            await asyncio.sleep(ANALYSIS_INTERVAL)
    
    async def run(self, duration_seconds=None):
        """Запуск системы на определенное время (или бесконечно)"""
        self.running = True
        watchdog_task = None
        
        try:
            # Запускаем сбор данных
            await self.run_market_data_collection()
            
            # Даём время на накопление данных
            print("⏳ Ожидание первых данных (10 сек)...\n")
            await asyncio.sleep(10)
            
            # БАГ #2 FIX: Запускаем watchdog параллельно
            watchdog_task = asyncio.create_task(self.watchdog_positions())
            
            # Запускаем мониторинг
            if duration_seconds:
                print(f"▶️  Запуск мониторинга на {duration_seconds} секунд...\n")
                try:
                    await asyncio.wait_for(
                        self.run_arbitrage_monitoring(),
                        timeout=duration_seconds
                    )
                except asyncio.TimeoutError:
                    print(f"\n⏱️  Время вышло ({duration_seconds}s)")
            else:
                print(f"▶️  Запуск бесконечного мониторинга (Ctrl+C для остановки)...\n")
                await self.run_arbitrage_monitoring()
        
        except KeyboardInterrupt:
            print("\n\n⚠️  Остановка по запросу пользователя...")
        finally:
            self.running = False
            if watchdog_task:
                watchdog_task.cancel()
                try:
                    await watchdog_task
                except asyncio.CancelledError:
                    pass
            await self.cleanup()
    
    async def cleanup(self):
        """Очистка ресурсов"""
        print("\n🧹 Завершение работы...")
        
        # Закрываем открытые позиции
        if self.position_manager and self.position_manager.positions:
            open_count = len(self.position_manager.positions)
            print(f"⚠️  Закрытие {open_count} открытых позиций...")
            
            for pair_id in list(self.position_manager.positions.keys()):
                trade = self.position_manager.positions[pair_id]
                await self.telegram.log_risk_warning(
                    "Emergency Close", 
                    f"{trade.symbol}: система остановлена с открытой позицией"
                )
                await self.trading_engine.close_position(pair_id)
        
        # Останавливаем слушателей
        if self.market_data_engine:
            await self.market_data_engine.stop()
        
        # Закрываем ArbitrageEngine ThreadPoolExecutor
        if hasattr(self, 'arbitrage_engine'):
            self.arbitrage_engine.shutdown()
        
        # Закрываем ThreadPoolExecutor в main
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=False)
        
        for name, exchange in self.exchanges.items():
            try:
                await exchange.close()
                print(f"   ✓ {name} закрыт")
            except:
                pass
        
        print("✅ Система остановлена\n")


async def main():
    """Основная функция"""
    print("="*70)
    print("   CRYPTO ARBITRAGE SYSTEM — PRODUCTION READY")
    print(f"   Strategy: {STRATEGY.upper()} | Min Spread: {config.OPEN_THRESHOLD}%")
    print(f"   Auto trading | Position management | Risk control")
    print("="*70)
    
    # Выбор режима
    USE_LIVE_TRADING = False  # ← Измените на True для реальной торговли
    
    # Создаём систему
    system = ArbitrageSystem(
        use_api_keys=USE_LIVE_TRADING,  # API ключи для live режима
        initial_balance=1000,
        strategy=STRATEGY,
        demo_mode=not USE_LIVE_TRADING  # demo если не live
    )
    
    # Инициализируем
    await system.initialize()
    
    # Запускаем
    duration = None  # 2 мин для demo, бесконечно для live
    await system.run(duration_seconds=duration)
    
    print("\n" + "="*70)
    if USE_LIVE_TRADING:
        print("   Live торговля остановлена")
    else:
        print("   Demo тестирование завершено")
    print("="*70)


if __name__ == "__main__":
    asyncio.run(main())
