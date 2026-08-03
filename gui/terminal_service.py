"""Qt-facing terminal service that owns independent CardData streams."""
from __future__ import annotations

import math, random, time, uuid
from dataclasses import replace
from datetime import datetime
from PySide6.QtCore import QObject, QTimer, Signal
from gui.card_data import CardData, CardMode, ExchangeMarketSnapshot

class TerminalService(QObject):
    card_created = Signal(object)
    card_updated = Signal(object)
    card_removed = Signal(str)
    def __init__(self,parent=None):
        super().__init__(parent); self._cards={}; self._started={}; self._tick=0
        self._timer=QTimer(self); self._timer.setInterval(100); self._timer.timeout.connect(self._publish_updates); self._timer.start()
    def create_card(self,symbol,long_exchange,short_exchange):
        cid=str(uuid.uuid4()); data=CardData(card_id=cid,symbol=symbol.upper(),long_exchange=long_exchange,short_exchange=short_exchange,mode=CardMode.WATCH,score='0')
        self._cards[cid]=data; self._started[cid]=time.monotonic(); self.card_created.emit(data); return cid
    def remove_card(self,card_id):
        self._cards.pop(card_id,None); self._started.pop(card_id,None); self.card_removed.emit(card_id)
    def _publish_updates(self):
        self._tick+=1
        for cid,data in list(self._cards.items()):
            base=0.45+math.sin(self._tick/20+len(cid))*0.08; net=base-0.12+random.uniform(-0.01,0.01)
            points=(*data.graph_points, (time.time(), base, net))[-3000:]
            markets={ex: ExchangeMarketSnapshot(funding=f'{random.uniform(-0.06,0.06):+.4f}%',next_funding='03:00:00',ask=f'{68000+random.random()*100:.2f}',bid=f'{67980+random.random()*100:.2f}',mark=f'{67990+random.random()*100:.2f}',index=f'{68010+random.random()*100:.2f}',open_interest=f'{random.uniform(10,90):.1f}M',volume=f'{random.uniform(100,900):.0f}M',bid_size=f'{random.uniform(0.1,8):.3f}',ask_size=f'{random.uniform(0.1,8):.3f}',latency=f'{random.randint(8,80)} ms') for ex in (data.long_exchange,data.short_exchange)}
            metrics={'Gross Spread':f'{base:.3f}%','Effective Spread':f'{base-0.04:.3f}%','Funding Diff':f'{random.uniform(-0.02,0.02):+.4f}%','Fee':'0.080%','Net Edge':f'{net:.3f}%','Score':str(min(99,max(1,int(net*140)))),'Trend':'EXPANDING' if self._tick%2 else 'STABLE','PnL':f'{random.uniform(-2,5):+.2f} USDT','Status':data.mode.value}
            life=int(time.monotonic()-self._started[cid]); lifetime=f'{life//3600:02d}:{life%3600//60:02d}:{life%60:02d}'
            new=replace(data,mode=CardMode.ACTIVE if self._tick%50<35 else CardMode.WATCH,status='READY',score=metrics['Score'],latency=markets[data.long_exchange].latency,markets=markets,metrics=metrics,graph_points=points,last_update=datetime.utcnow(),message_count=data.message_count+1,lifetime=lifetime)
            self._cards[cid]=new; self.card_updated.emit(new)
