from PySide6.QtWidgets import QFrame, QGridLayout, QLabel
from gui.card_data import CardData

ROWS=[('Funding','funding'),('Next Funding','next_funding'),('Ask','ask'),('Bid','bid'),('Mark','mark'),('Index','index'),('OI','open_interest'),('Volume','volume'),('Bid Size','bid_size'),('Ask Size','ask_size'),('Latency','latency')]
class CardMarket(QFrame):
    def __init__(self,parent=None):
        super().__init__(parent); self.setObjectName('Panel'); self.labels={}
        self.grid=QGridLayout(self); self.grid.setContentsMargins(10,8,10,8); self.grid.addWidget(QLabel('Market'),0,0)
    def update_data(self,data:CardData):
        exchanges=[data.long_exchange, data.short_exchange]
        for col,ex in enumerate(exchanges,1): self._label((0,col), ex.upper()).setText(ex.upper())
        for row,(title,attr) in enumerate(ROWS,1):
            self._label((row,0), title).setText(title)
            for col,ex in enumerate(exchanges,1):
                snap=data.markets.get(ex) or data.markets.get(ex.lower())
                self._label((row,col),'—').setText(getattr(snap, attr, '—') if snap else '—')
    def _label(self,key,text):
        if key not in self.labels:
            w=QLabel(text); w.setObjectName('Cell'); self.labels[key]=w; self.grid.addWidget(w,*key)
        return self.labels[key]
