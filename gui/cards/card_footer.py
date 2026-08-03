from datetime import datetime, timezone
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel
from gui.card_data import CardData

class CardFooter(QFrame):
    def __init__(self,parent=None):
        super().__init__(parent); self.setObjectName('Footer'); h=QHBoxLayout(self); h.setContentsMargins(10,6,10,6); self.labels=[QLabel() for _ in range(4)]
        for w in self.labels: w.setObjectName('Muted'); h.addWidget(w)
    def update_data(self,data:CardData):
        ts=data.last_update.strftime('%H:%M:%S') if isinstance(data.last_update, datetime) else str(data.last_update)
        for label,text in zip(self.labels,(f'Updated {ts}',f'Msg {data.message_count}',f'Life {data.lifetime}',f'Last trade {data.last_trade}')): label.setText(text)
