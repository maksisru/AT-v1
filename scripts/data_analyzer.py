"""
Data Analyzer — анализ собранных данных для выбора стратегии

Анализирует:
- Оптимальные пороги открытия
- Частоту разных диапазонов спредов
- Среднюю ликвидность
- Качество данных (data age)
- Рекомендации по настройкам

Использование:
    python data_analyzer.py data_collection/spreads_20260605_120000.csv
"""
import sys
import csv
import statistics
from pathlib import Path
from datetime import datetime
from collections import defaultdict


class DataAnalyzer:
    """Анализатор собранных данных"""
    
    def __init__(self, csv_file):
        self.csv_file = Path(csv_file)
        self.data = []
        self._load_data()
    
    def _load_data(self):
        """Загрузка данных из CSV"""
        if not self.csv_file.exists():
            print(f"❌ Файл не найден: {self.csv_file}")
            sys.exit(1)
        
        with open(self.csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            self.data = list(reader)
        
        print(f"✅ Загружено {len(self.data)} записей из {self.csv_file.name}")
    
    def analyze(self):
        """Полный анализ данных"""
        print("\n" + "="*80)
        print("📊 АНАЛИЗ СОБРАННЫХ ДАННЫХ")
        print("="*80)
        
        if not self.data:
            print("❌ Нет данных для анализа")
            return
        
        self._analyze_spread_distribution()
        self._analyze_approved_vs_rejected()
        self._analyze_rejection_reasons()
        self._analyze_net_edge()
        self._analyze_data_quality()
        self._analyze_liquidity()
        self._analyze_funding_rates()
        self._analyze_exchange_pairs()
        self._generate_recommendations()
    
    def _analyze_spread_distribution(self):
        """Распределение спредов"""
        print("\n📈 РАСПРЕДЕЛЕНИЕ СПРЕДОВ")
        print("-"*80)
        
        spreads = [float(row['gross_spread_pct']) for row in self.data]
        
        buckets = {
            "0.3-0.5%": [s for s in spreads if 0.3 <= s < 0.5],
            "0.5-0.7%": [s for s in spreads if 0.5 <= s < 0.7],
            "0.7-1.0%": [s for s in spreads if 0.7 <= s < 1.0],
            "1.0-1.5%": [s for s in spreads if 1.0 <= s < 1.5],
            "1.5-2.0%": [s for s in spreads if 1.5 <= s < 2.0],
            "2.0-3.0%": [s for s in spreads if 2.0 <= s < 3.0],
            "3.0-5.0%": [s for s in spreads if 3.0 <= s < 5.0],
            "5.0%+":    [s for s in spreads if s >= 5.0]
        }
        
        for bucket, values in buckets.items():
            count = len(values)
            pct = count / len(spreads) * 100
            bar = "█" * int(pct / 2)
            print(f"{bucket:12} {count:6} ({pct:5.1f}%) {bar}")
        
        print(f"\nСтатистика:")
        print(f"  Среднее:  {statistics.mean(spreads):.2f}%")
        print(f"  Медиана:  {statistics.median(spreads):.2f}%")
        print(f"  Макс:     {max(spreads):.2f}%")
        print(f"  Мин:      {min(spreads):.2f}%")
    
    def _analyze_approved_vs_rejected(self):
        """Анализ одобренных vs отклонённых"""
        print("\n✅ ОДОБРЕННЫЕ vs ❌ ОТКЛОНЁННЫЕ")
        print("-"*80)
        
        approved = [row for row in self.data if row['approved'] == 'True']
        rejected = [row for row in self.data if row['approved'] == 'False']
        
        print(f"Одобрено:   {len(approved):6} ({len(approved)/len(self.data)*100:5.1f}%)")
        print(f"Отклонено:  {len(rejected):6} ({len(rejected)/len(self.data)*100:5.1f}%)")
        
        if approved:
            approved_spreads = [float(row['gross_spread_pct']) for row in approved]
            print(f"\nОдобренные спреды:")
            print(f"  Среднее:  {statistics.mean(approved_spreads):.2f}%")
            print(f"  Медиана:  {statistics.median(approved_spreads):.2f}%")
            print(f"  Min-Max:  {min(approved_spreads):.2f}% - {max(approved_spreads):.2f}%")
    
    def _analyze_rejection_reasons(self):
        """Анализ причин отклонения"""
        print("\n🚫 ПРИЧИНЫ ОТКЛОНЕНИЯ")
        print("-"*80)
        
        rejected = [row for row in self.data if row['approved'] == 'False']
        
        if not rejected:
            print("Все возможности одобрены!")
            return
        
        # Подсчёт причин
        reasons = defaultdict(int)
        for row in rejected:
            reason = row.get('reject_reason', 'Unknown')
            # Упрощаем причину для группировки
            if 'Net edge insufficient' in reason:
                reasons['Net edge < MIN_NET_EDGE'] += 1
            elif 'Gross spread too low' in reason:
                reasons['Gross spread < MIN_GROSS_SPREAD'] += 1
            elif 'Gross spread suspicious' in reason or 'Gross spread anomaly' in reason:
                reasons['Gross spread > MAX (suspicious)'] += 1
            elif 'Stale data' in reason or 'old data' in reason:
                reasons['Stale data (age > threshold)'] += 1
            elif 'Bid-ask too wide' in reason:
                reasons['Bid-ask spread too wide'] += 1
            else:
                reasons[reason[:50]] += 1
        
        # Сортируем по частоте
        sorted_reasons = sorted(reasons.items(), key=lambda x: x[1], reverse=True)
        
        for reason, count in sorted_reasons:
            pct = count / len(rejected) * 100
            print(f"  {reason:45} {count:5} ({pct:5.1f}%)")
    
    def _analyze_net_edge(self):
        """Анализ net edge"""
        print("\n💰 NET EDGE (Чистая прибыль)")
        print("-"*80)
        
        net_edges = [float(row['net_edge_pct']) for row in self.data]
        positive = [n for n in net_edges if n > 0]
        negative = [n for n in net_edges if n <= 0]
        
        print(f"Положительный net edge: {len(positive):6} ({len(positive)/len(net_edges)*100:5.1f}%)")
        print(f"Отрицательный net edge: {len(negative):6} ({len(negative)/len(net_edges)*100:5.1f}%)")
        
        if positive:
            print(f"\nПоложительный net edge:")
            print(f"  Среднее:  {statistics.mean(positive):.3f}%")
            print(f"  Медиана:  {statistics.median(positive):.3f}%")
            print(f"  Макс:     {max(positive):.3f}%")
            
            # С учётом плеча 5x
            print(f"\nС плечом 5x:")
            print(f"  Средний ROI:  {statistics.mean(positive) * 5:.1f}%")
            print(f"  Макс ROI:     {max(positive) * 5:.1f}%")
    
    def _analyze_data_quality(self):
        """Анализ качества данных"""
        print("\n📡 КАЧЕСТВО ДАННЫХ (data age)")
        print("-"*80)
        
        data_ages = [float(row['data_age_ms']) for row in self.data]
        
        fresh = len([a for a in data_ages if a <= 500])
        stale = len([a for a in data_ages if a > 500])
        
        print(f"Свежие (<500ms):  {fresh:6} ({fresh/len(data_ages)*100:5.1f}%)")
        print(f"Старые (>500ms):  {stale:6} ({stale/len(data_ages)*100:5.1f}%)")
        print(f"\nСреднее data age: {statistics.mean(data_ages):.1f}ms")
        print(f"Медиана:          {statistics.median(data_ages):.1f}ms")
    
    def _analyze_liquidity(self):
        """Анализ ликвидности"""
        print("\n💧 ЛИКВИДНОСТЬ")
        print("-"*80)
        
        volumes_long = [float(row['volume_long']) for row in self.data if float(row['volume_long']) > 0]
        volumes_short = [float(row['volume_short']) for row in self.data if float(row['volume_short']) > 0]
        
        if volumes_long:
            print(f"Volume Long:")
            print(f"  Среднее:  ${statistics.mean(volumes_long):.0f}")
            print(f"  Медиана:  ${statistics.median(volumes_long):.0f}")
            print(f"  Min-Max:  ${min(volumes_long):.0f} - ${max(volumes_long):.0f}")
        
        if volumes_short:
            print(f"\nVolume Short:")
            print(f"  Среднее:  ${statistics.mean(volumes_short):.0f}")
            print(f"  Медиана:  ${statistics.median(volumes_short):.0f}")
            print(f"  Min-Max:  ${min(volumes_short):.0f} - ${max(volumes_short):.0f}")
    
    def _analyze_funding_rates(self):
        """Анализ funding rates"""
        print("\n💸 FUNDING RATES")
        print("-"*80)
        
        funding_diffs = [float(row['funding_diff']) for row in self.data]
        funding_longs = [float(row['funding_rate_long']) for row in self.data]
        funding_shorts = [float(row['funding_rate_short']) for row in self.data]
        
        print(f"Funding Difference:")
        print(f"  Среднее:  {statistics.mean(funding_diffs):.6f} ({statistics.mean(funding_diffs)*100:.4f}%)")
        print(f"  Медиана:  {statistics.median(funding_diffs):.6f}")
        print(f"  Макс:     {max(funding_diffs):.6f}")
        print(f"  Мин:      {min(funding_diffs):.6f}")
        
        # Стоимость funding за 8 часов на позицию $1000 с плечом 5x
        avg_funding_cost = abs(statistics.mean(funding_diffs)) * 1000 * 5
        print(f"\nСтоимость funding (8ч, $1000 позиция, 5x):")
        print(f"  ~${avg_funding_cost:.2f} каждые 8 часов")
        print(f"  ~${avg_funding_cost * 3:.2f} в день")
    
    def _analyze_exchange_pairs(self):
        """Анализ пар бирж"""
        print("\n🏦 ПОПУЛЯРНЫЕ ПАРЫ БИРЖ")
        print("-"*80)
        
        pairs = defaultdict(int)
        for row in self.data:
            pair = f"{row['exchange_long']} ↔ {row['exchange_short']}"
            pairs[pair] += 1
        
        sorted_pairs = sorted(pairs.items(), key=lambda x: x[1], reverse=True)
        for pair, count in sorted_pairs[:10]:
            pct = count / len(self.data) * 100
            print(f"  {pair:30} {count:6} ({pct:5.1f}%)")
    
    def _generate_recommendations(self):
        """Генерация рекомендаций"""
        print("\n🎯 РЕКОМЕНДАЦИИ ПО НАСТРОЙКАМ")
        print("="*80)
        
        approved = [row for row in self.data if row['approved'] == 'True']
        
        if not approved:
            print("❌ Нет одобренных возможностей — ослабьте фильтры")
            return
        
        approved_spreads = [float(row['gross_spread_pct']) for row in approved]
        approved_net_edges = [float(row['net_edge_pct']) for row in approved]
        
        # Определяем оптимальные пороги
        min_spread = min(approved_spreads)
        avg_spread = statistics.mean(approved_spreads)
        median_spread = statistics.median(approved_spreads)
        
        min_net_edge = min(approved_net_edges)
        avg_net_edge = statistics.mean(approved_net_edges)
        
        # Частота
        duration_hours = self._estimate_duration()
        if duration_hours:
            freq_per_hour = len(approved) / duration_hours
            freq_per_day = freq_per_hour * 24
        else:
            freq_per_day = len(approved)
        
        print(f"\n📊 Текущие результаты:")
        print(f"  Одобренных возможностей: {len(approved)}")
        print(f"  Частота: ~{freq_per_day:.1f} возможностей/день")
        print(f"  Средний спред: {avg_spread:.2f}%")
        print(f"  Средний net edge: {avg_net_edge:.3f}%")
        
        print(f"\n⚙️ РЕКОМЕНДУЕМЫЕ НАСТРОЙКИ:")
        print("-"*80)
        
        # Консервативный режим
        print("\n1️⃣ КОНСЕРВАТИВНЫЙ (текущий оптимум):")
        print(f"   OPEN_THRESHOLD = {median_spread:.1f}")
        print(f"   MAX_SPREAD_OPEN = 3.0")
        print(f"   MIN_NET_EDGE = {max(0.3, avg_net_edge * 0.8):.2f}")
        print(f"   MAX_LEVERAGE = 5")
        print(f"   → Ожидаемо: ~{freq_per_day:.0f} сделок/день")
        
        # Агрессивный режим
        aggressive_threshold = max(0.8, min_spread * 0.9)
        aggressive_freq = freq_per_day * 1.5
        print(f"\n2️⃣ АГРЕССИВНЫЙ (больше сделок, выше риск):")
        print(f"   OPEN_THRESHOLD = {aggressive_threshold:.1f}")
        print(f"   MAX_SPREAD_OPEN = 5.0")
        print(f"   MIN_NET_EDGE = 0.25")
        print(f"   MAX_LEVERAGE = 5")
        print(f"   → Ожидаемо: ~{aggressive_freq:.0f} сделок/день")
        
        # Очень консервативный
        conservative_threshold = avg_spread * 1.2
        conservative_freq = freq_per_day * 0.5
        print(f"\n3️⃣ ОЧЕНЬ КОНСЕРВАТИВНЫЙ (качество > количество):")
        print(f"   OPEN_THRESHOLD = {conservative_threshold:.1f}")
        print(f"   MAX_SPREAD_OPEN = 3.0")
        print(f"   MIN_NET_EDGE = {avg_net_edge:.2f}")
        print(f"   MAX_LEVERAGE = 3")
        print(f"   → Ожидаемо: ~{conservative_freq:.0f} сделок/день")
        
        print("\n" + "="*80)
    
    def _estimate_duration(self):
        """Оценка длительности сбора"""
        if len(self.data) < 2:
            return None
        
        try:
            first = datetime.fromisoformat(self.data[0]['timestamp'])
            last = datetime.fromisoformat(self.data[-1]['timestamp'])
            duration = (last - first).total_seconds() / 3600
            return duration
        except:
            return None


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python data_analyzer.py <путь_к_csv>")
        print("\nПример:")
        print("  python data_analyzer.py data_collection/spreads_20260605_120000.csv")
        
        # Показываем доступные файлы
        data_dir = Path("data_collection")
        if data_dir.exists():
            csv_files = list(data_dir.glob("spreads_*.csv"))
            if csv_files:
                print("\nДоступные файлы:")
                for f in sorted(csv_files, reverse=True):
                    print(f"  {f}")
        sys.exit(1)
    
    csv_file = sys.argv[1]
    analyzer = DataAnalyzer(csv_file)
    analyzer.analyze()
