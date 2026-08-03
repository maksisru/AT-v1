from PySide6.QtWidgets import QScrollArea, QWidget
from gui.flow_layout import FlowLayout

class Workspace(QScrollArea):
    def __init__(self,parent=None):
        super().__init__(parent); self.setWidgetResizable(True); self.setObjectName('Workspace')
        self.container=QWidget(); self.flow=FlowLayout(self.container); self.container.setLayout(self.flow); self.setWidget(self.container); self.cards={}
    def add_card(self,card):
        self.cards[card.card_id]=card; self.flow.addWidget(card)
    def remove_card(self,card_id):
        card=self.cards.pop(card_id,None)
        if card: card.setParent(None); card.deleteLater()
