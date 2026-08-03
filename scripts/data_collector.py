"""
Data Collector — сбор статистики спредов для анализа прибыльности.

Запуск:
    python data_collector.py          # 24 часа
    python data_collector.py 48       # 48 часов
    python data_collector.py 2        # 2 часа (тест)

Результат: data_collection/spreads_YYYYMMDD_HHMMSS.csv
"""
import asyncio
import csv
import sys
import os
import logging
import signal
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

from exchanges.mexc import MEXCExchange
from exchanges.gate import GateExchange
from exchanges.normalize import validate_spread

# Настройка логирования аномалий
logging.basicConfig(level=logging.INFO)
anomaly_logger = logging.getLogger("anomaly")
anomaly_handler = logging.FileHandler("data_collection/anomalies.log")
anomaly_handler.setLevel(logging.CRITICAL)
anomaly_logger.addHandler(anomaly_handler)
from exchanges.bybit import BybitExchange
from core.engines.market_data_engine import MarketDataEngine
from core.engines.arbitrage_engine import ArbitrageEngine
from core.utils.env_loader import get_telegram_config
from utils.telegram_logger import TelegramLogger


# ─── Конфигурация ────────────────────────────────────────────────────────────

OUTPUT_DIR = Path("data_collection")

# Порог для записи: пишем ТОЛЬКО спреды выше этого значения.
# 0 = писать всё (большие файлы), 0.5 = только интересное.
MIN_SPREAD_TO_RECORD = 0.5

# Интервал анализа в секундах
ANALYSIS_INTERVAL = 2.0

# Максимум строк в одном файле (защита от гигантских CSV)
MAX_ROWS_PER_FILE = 500_000

# Батчинг записи: накапливать строки перед flush
BATCH_SIZE = 100  # flush каждые 100 строк
BATCH_FLUSH_INTERVAL = 10.0  # или каждые 10 сек

# Порог аномального спреда для немедленного алерта
ANOMALY_SPREAD_THRESHOLD = 10.0


# ─── CSV-схема ────────────────────────────────────────────────────────────────

CSV_FIELDS = [
    "timestamp",          # ISO-8601, UTC
    "exchange_long",      # биржа где LONG
    "exchange_short",     # биржа где SHORT
    "symbol",             # BTCUSDT
    "gross_spread_pct",   # сырой спред, %
    "price_long",         # ask на long-бирже
    "price_short",        # bid на short-бирже
    "funding_long",       # funding rate long-биржи
    "funding_short",      # funding rate short-биржи
    "funding_diff_pct",   # разница funding, %
    "effective_spread_pct",  # спред с учётом funding
]


# ─── Collector ────────────────────────────────────────────────────────────────

class SpreadDataCollector:
    """Собирает и записывает статистику спредов в CSV."""

    def __init__(self, duration_hours: float = 24.0):
        self.duration_seconds = duration_hours * 3600
        self.exchanges = {
            "mexc": MEXCExchange(),
            "gate": GateExchange(),
            "bybit": BybitExchange(),
        }
        self.market_data_engine = MarketDataEngine(self.exchanges)
        self.arbitrage_engine = ArbitrageEngine(max_workers=4)

        OUTPUT_DIR.mkdir(exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.csv_path = OUTPUT_DIR / f"spreads_{ts}.csv"

        self._csv_file = None
        self._writer = None
        self._rows_written = 0
        self._file_index = 0
        self._shutdown_requested = False

        # Батчинг записи
        self._batch = []
        self._last_flush = 0.0

        # Telegram logger
        telegram_bot_token, telegram_chat_id = get_telegram_config()
        self.telegram = TelegramLogger(telegram_bot_token, telegram_chat_id)

        # Статистика сессии
        self.stats = defaultdict(lambda: {
            "count": 0,
            "max_spread": 0.0,
            "total_spread": 0.0,
        })
        
        # Статистика по биржам
        self.exchange_stats = defaultdict(lambda: {
            "data_received": 0,
            "ws_reconnects": 0,
            "last_seen": None,
        })
        
        # Обработка Ctrl+C
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _signal_handler(self, sig, frame):
        """Обработчик Ctrl+C для корректного закрытия файла"""
        print("\n\n⚠️  Получен сигнал остановки, сохраняю данные...")
        self._shutdown_requested = True
        self._flush_batch(force=True)
        if self._csv_file and not self._csv_file.closed:
            self._csv_file.close()
            abs_path = os.path.abspath(self.csv_path)
            print(f"✅ Файл сохранён: {abs_path}")
            print(f"   Размер: {os.path.getsize(abs_path) / 1024:.1f} KB")
            print(f"   Записей: {self._rows_written}")

    # ── Файловые операции ────────────────────────────────────────────────────

    def _open_csv(self):
        """Открывает новый CSV-файл для записи."""
        if self._csv_file:
            self._flush_batch(force=True)
            self._csv_file.close()

        if self._file_index == 0:
            path = self.csv_path
        else:
            stem = self.csv_path.stem
            path = OUTPUT_DIR / f"{stem}_part{self._file_index}.csv"

        self._csv_file = open(path, "w", newline="", encoding="utf-8", buffering=8192)
        self._writer = csv.DictWriter(self._csv_file, fieldnames=CSV_FIELDS)
        self._writer.writeheader()
        self._csv_file.flush()
        self._rows_written = 0
        self._file_index += 1
        abs_path = os.path.abspath(path)
        print(f"   📄 Запись в: {abs_path}")

    def _flush_batch(self, force=False):
        """Сбрасывает накопленный батч на диск."""
        if not self._batch:
            return
        
        try:
            for row in self._batch:
                self._writer.writerow(row)
            self._csv_file.flush()
            os.fsync(self._csv_file.fileno())
            self._batch.clear()
            self._last_flush = asyncio.get_event_loop().time()
        except Exception as e:
            print(f"⚠️  Ошибка flush: {e}")

    def _write_row(self, row: dict):
        """Добавляет строку в батч, при необходимости сбрасывает."""
        try:
            if self._writer is None or self._rows_written >= MAX_ROWS_PER_FILE:
                self._open_csv()
            
            self._batch.append(row)
            self._rows_written += 1
            
            # Flush по размеру батча или по времени
            now = asyncio.get_event_loop().time()
            if len(self._batch) >= BATCH_SIZE or (now - self._last_flush) >= BATCH_FLUSH_INTERVAL:
                self._flush_batch()
        
        except Exception as e:
            print(f"⚠️  Ошибка записи в CSV: {e}")

    def _close(self):
        self._flush_batch(force=True)
        if self._csv_file and not self._csv_file.closed:
            self._csv_file.close()

    # ── Основной цикл ────────────────────────────────────────────────────────

    async def run(self):
        """Запускает сбор данных."""
        print(f"\n{'='*60}")
        print(f"  DATA COLLECTOR — сбор спредов")
        print(f"  Длительность: {self.duration_seconds/3600:.1f} ч")
        print(f"  Min спред для записи: {MIN_SPREAD_TO_RECORD}%")
        print(f"  Интервал: {ANALYSIS_INTERVAL}s")
        print(f"{'='*60}\n")

        # Инициализация бирж
        print("🔌 Инициализация бирж...")
        for name, exchange in self.exchanges.items():
            await exchange.initialize()
            print(f"   ✓ {name}")

        # Подписка на символы
        print("\n🔍 Получение торговых пар...")
        pairwise = await self.market_data_engine.get_common_symbols(limit=None)
        all_symbols = set()
        for k, v in pairwise.items():
            if k != "all":
                all_symbols.update(v)
        print(f"   ✓ {len(all_symbols)} уникальных пар")

        await self.market_data_engine.subscribe_all(list(all_symbols))

        print("\n⏳ Прогрев (10 сек)...")
        await asyncio.sleep(10)
        
        # Проверка что данные поступают
        test_data = self.market_data_engine.get_latest_data()
        if not test_data or not any(test_data.values()):
            print("❌ ОШИБКА: Данные не поступают после прогрева!")
            await self.telegram.send("❌ <b>Data Collector failed</b>\n\nНет данных от бирж")
            return
        
        print(f"   ✓ Данные поступают от {len([v for v in test_data.values() if v])} бирж")

        self._open_csv()

        start = asyncio.get_event_loop().time()
        end = start + self.duration_seconds
        iteration = 0
        total_recorded = 0

        print(f"\n▶  Сбор данных до {datetime.now(timezone.utc).strftime('%H:%M UTC')} + "
              f"{self.duration_seconds/3600:.1f}ч\n")

        # Уведомление в Telegram о старте
        await self.telegram.send(
            f"🔍 <b>Data Collector запущен</b>\n\n"
            f"⏱ Длительность: {self.duration_seconds/3600:.1f}ч\n"
            f"📊 Min спред: {MIN_SPREAD_TO_RECORD}%\n"
            f"📈 Пар: {len(all_symbols)}\n"
            f"🕐 {datetime.now(timezone.utc).strftime('%H:%M UTC')}"
        )

        try:
            no_data_count = 0  # Счётчик итераций без данных
            last_connection_check = 0
            last_anomaly_alert = 0
            
            while asyncio.get_event_loop().time() < end:
                iteration += 1
                
                # Проверка на сигнал остановки
                if self._shutdown_requested:
                    break
                
                # Проверяем подключения каждые 60 секунд
                now_time = asyncio.get_event_loop().time()
                if now_time - last_connection_check > 60:
                    last_connection_check = now_time
                    active_exchanges = []
                    for name, exchange in self.exchanges.items():
                        try:
                            if hasattr(exchange, 'ws') and exchange.ws:
                                active_exchanges.append(name)
                                self.exchange_stats[name]["last_seen"] = now_time
                        except:
                            pass
                    if iteration > 10:  # Только после прогрева
                        print(f"   🔌 Активные WS: {', '.join(active_exchanges)} ({len(active_exchanges)}/3)")
                
                try:
                    market_data = self.market_data_engine.get_latest_data()

                    if not market_data or not any(market_data.values()):
                        no_data_count += 1
                        if no_data_count >= 30:  # 30 * 2s = 60 секунд без данных
                            print(f"⚠️  Нет данных уже {no_data_count * ANALYSIS_INTERVAL:.0f}с")
                            await self.telegram.send(
                                f"⚠️ <b>Data Collector: нет данных</b>\n\n"
                                f"Итераций без данных: {no_data_count}"
                            )
                            no_data_count = 0
                        await asyncio.sleep(ANALYSIS_INTERVAL)
                        continue
                    
                    no_data_count = 0  # Сбрасываем если данные пришли
                    
                    # Обновляем статистику бирж
                    for name, data in market_data.items():
                        if data:
                            self.exchange_stats[name]["data_received"] += 1

                    # Ищем все возможности без порога (порог применяем при записи)
                    opportunities = await asyncio.get_event_loop().run_in_executor(
                        None,
                        self.arbitrage_engine.find_opportunities_parallel,
                        market_data,
                        0.0,  # Ищем ВСЕ спреды, фильтруем при записи
                        50,
                    )

                    now_iso = datetime.now(timezone.utc).isoformat() + "Z"
                    
                    # Если нет opportunities - пропускаем
                    if not opportunities:
                        await asyncio.sleep(ANALYSIS_INTERVAL)
                        continue

                    for opp in opportunities:
                        try:
                            # Применяем порог MIN_SPREAD_TO_RECORD
                            if opp.spread < MIN_SPREAD_TO_RECORD:
                                continue
                            
                            # БАГ #4 FIX: Фильтр аномалий через validate_spread
                            if not validate_spread(
                                opp.exchange_long, opp.exchange_short,
                                opp.symbol, opp.price_long, opp.price_short
                            ):
                                continue  # Аномалия — пропускаем, она уже залогирована
                            
                            # Детекция аномалий для алертов
                            if opp.spread >= ANOMALY_SPREAD_THRESHOLD:
                                if (now_time - last_anomaly_alert) > 300:  # Не чаще 1 раза в 5 мин
                                    await self.telegram.send(
                                        f"🚨 <b>АНОМАЛЬНЫЙ СПРЕД!</b>\n\n"
                                        f"📊 {opp.symbol}\n"
                                        f"💹 Спред: {opp.spread:.2f}%\n"
                                        f"🏦 {opp.exchange_long} ↔ {opp.exchange_short}\n"
                                        f"💰 Long: ${opp.price_long:.4f}\n"
                                        f"💰 Short: ${opp.price_short:.4f}"
                                    )
                                    last_anomaly_alert = now_time
                                    anomaly_logger.critical(
                                        f"{now_iso},{opp.symbol},{opp.spread:.4f},"
                                        f"{opp.exchange_long},{opp.exchange_short}"
                                    )
                            
                            # Funding rate уже в %, не нужно умножать на 100!
                            funding_diff = (
                                (opp.data_short.funding_rate - opp.data_long.funding_rate)
                                if opp.data_long and opp.data_short
                                else 0.0
                            )

                            row = {
                                "timestamp": now_iso,
                                "exchange_long": opp.exchange_long,
                                "exchange_short": opp.exchange_short,
                                "symbol": opp.symbol,
                                "gross_spread_pct": round(opp.spread, 4),
                                "price_long": round(opp.price_long, 6),
                                "price_short": round(opp.price_short, 6),
                                "funding_long": round(
                                    opp.data_long.funding_rate if opp.data_long else 0, 6
                                ),
                                "funding_short": round(
                                    opp.data_short.funding_rate if opp.data_short else 0, 6
                                ),
                                "funding_diff_pct": round(funding_diff, 6),
                                "effective_spread_pct": round(opp.spread - funding_diff, 4),
                            }
                            
                            # Проверка что данные не пустые
                            if not row["symbol"] or not row["exchange_long"]:
                                continue
                            
                            self._write_row(row)
                            total_recorded += 1

                            # Обновляем статистику
                            key = f"{opp.symbol}|{opp.exchange_long}↔{opp.exchange_short}"
                            s = self.stats[key]
                            s["count"] += 1
                            s["total_spread"] += opp.spread
                            s["max_spread"] = max(s["max_spread"], opp.spread)
                        
                        except Exception as e:
                            if iteration <= 5:
                                print(f"⚠️  Ошибка обработки opportunity: {e}")
                            continue

                    # Прогресс каждые 5 минут
                    elapsed = asyncio.get_event_loop().time() - start
                    if iteration % int(300 / ANALYSIS_INTERVAL) == 0:
                        await self._print_progress(elapsed, total_recorded)
                
                except Exception as e:
                    if iteration <= 5:
                        print(f"⚠️  Ошибка в итерации {iteration}: {e}")
                    # Продолжаем работу

                await asyncio.sleep(ANALYSIS_INTERVAL)

        except KeyboardInterrupt:
            print("\n\n⚠  Остановлено пользователем")
        except Exception as e:
            print(f"\n\n❌ Критическая ошибка: {e}")
            import traceback
            traceback.print_exc()
            await self.telegram.send(f"❌ <b>Data Collector crash</b>\n\n{e}")
        finally:
            print("\n🔄 Завершение...")
            self._close()
            await self._print_summary(total_recorded)
            await self._cleanup()

    async def _print_progress(self, elapsed: float, total: int):
        pct = elapsed / self.duration_seconds * 100
        top = sorted(
            self.stats.items(),
            key=lambda x: x[1]["max_spread"],
            reverse=True,
        )[:3]
        print(f"[{elapsed/3600:.1f}ч / {pct:.0f}%] Записано: {total}")
        
        # Формируем сообщение для Telegram
        msg = f"📊 <b>Прогресс сбора данных</b>\n\n"
        msg += f"⏱ Время: {elapsed/3600:.1f}ч ({pct:.0f}%)\n"
        msg += f"📝 Записано: {total}\n\n"
        
        # Статистика по биржам
        msg += "<b>Биржи:</b>\n"
        for name, stat in self.exchange_stats.items():
            if stat["data_received"] > 0:
                uptime = stat["data_received"] / (elapsed / ANALYSIS_INTERVAL) * 100
                msg += f"• {name}: {uptime:.0f}% uptime\n"
        
        msg += "\n<b>Топ-3 по спреду:</b>\n"
        
        for key, s in top:
            sym, pair = key.split("|")
            avg = s["total_spread"] / s["count"] if s["count"] else 0
            print(f"   {sym} {pair}: max={s['max_spread']:.2f}% avg={avg:.2f}% n={s['count']}")
            msg += f"• {sym} {pair}\n  max={s['max_spread']:.2f}% avg={avg:.2f}% n={s['count']}\n"
        
        # Отправляем в Telegram и ЖДЁМ завершения
        await self.telegram.send(msg)

    async def _print_summary(self, total: int):
        print(f"\n{'='*60}")
        print(f"  ИТОГ: {total} записей")
        print(f"  Файл: {self.csv_path}")
        print(f"\n  Топ-10 пар по максимальному спреду:")

        top = sorted(
            self.stats.items(),
            key=lambda x: x[1]["max_spread"],
            reverse=True,
        )[:10]

        # Формируем сообщение для Telegram
        msg = f"✅ <b>Data Collector завершён</b>\n\n"
        msg += f"📝 Всего записей: {total}\n"
        msg += f"📄 Файл: {self.csv_path.name}\n\n"
        msg += "<b>Топ-10 пар:</b>\n"

        for key, s in top:
            sym, pair = key.split("|")
            avg = s["total_spread"] / s["count"] if s["count"] else 0
            print(f"  {sym:12s} {pair:30s}  max={s['max_spread']:5.2f}%  "
                  f"avg={avg:5.2f}%  n={s['count']}")
            msg += f"• {sym} {pair}\n  max={s['max_spread']:.2f}% avg={avg:.2f}% n={s['count']}\n"
        
        print(f"{'='*60}\n")
        
        # Отправляем итоги в Telegram и ЖДЁМ
        await self.telegram.send(msg)

    async def _cleanup(self):
        for exchange in self.exchanges.values():
            try:
                await exchange.close()
            except Exception:
                pass


# ─── Точка входа ─────────────────────────────────────────────────────────────

async def main():
    hours = float(sys.argv[1]) if len(sys.argv) > 1 else 24.0
    collector = SpreadDataCollector(duration_hours=hours)
    await collector.run()


if __name__ == "__main__":
    asyncio.run(main())