from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QMessageBox, QVBoxLayout
from gui.card_data import CardData
from gui.cards.card_header import CardHeader
from gui.cards.card_control_panel import CardControlPanel
from gui.cards.card_market import CardMarket
from gui.cards.card_metrics import CardMetrics
from gui.cards.card_spread_graph import CardSpreadGraph
from gui.cards.card_footer import CardFooter

class ArbitrageCard(QFrame):
    remove_requested = Signal(str)
    def __init__(self, data: CardData, parent=None):
        super().__init__(parent); self.card_id=data.card_id; self._last_data=None; self.setObjectName('ArbitrageCard')
        self.setMinimumWidth(330); self.setMaximumWidth(390)
        layout=QVBoxLayout(self); layout.setContentsMargins(0,0,0,0); layout.setSpacing(1)
        self.header=CardHeader(); self.controls=CardControlPanel(); self.market=CardMarket(); self.metrics=CardMetrics(); self.graph=CardSpreadGraph(); self.footer=CardFooter()
        for w in (self.header,self.controls,self.market,self.metrics,self.graph,self.footer): layout.addWidget(w)
        self.header.close_requested.connect(self._confirm_remove); self.update_data(data)
    def update_data(self,data:CardData):
        if data == self._last_data: return
        self._last_data=data
        for w in (self.header,self.market,self.metrics,self.graph,self.footer): w.update_data(data)
    def _confirm_remove(self):
        if QMessageBox.question(self,'Удалить карточку?','Удалить карточку?',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes:
            self.remove_requested.emit(self.card_id)
