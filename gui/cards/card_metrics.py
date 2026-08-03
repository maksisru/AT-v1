from PySide6.QtWidgets import QFrame, QGridLayout, QLabel
from gui.card_data import CardData

METRICS=['Gross Spread','Effective Spread','Funding Diff','Fee','Net Edge','Score','Trend','PnL','Status']
class CardMetrics(QFrame):
    def __init__(self,parent=None):
        super().__init__(parent); self.setObjectName('Panel'); g=QGridLayout(self); g.setContentsMargins(10,8,10,8); self.values={}
        for i,name in enumerate(METRICS):
            g.addWidget(QLabel(name), i//2, (i%2)*2); v=QLabel('—'); v.setObjectName('Metric'); self.values[name]=v; g.addWidget(v, i//2, (i%2)*2+1)
    def update_data(self,data:CardData):
        for name,label in self.values.items(): label.setText(str(data.metrics.get(name,'—')))
