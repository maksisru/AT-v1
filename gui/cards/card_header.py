from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout
from gui.card_data import CardData, CardMode

MODE_COLORS = {CardMode.ACTIVE:'#24d18b',CardMode.WATCH:'#f5c84b',CardMode.PAUSED:'#4aa3ff',CardMode.ERROR:'#ff4d5e',CardMode.CLOSED:'#7b8494'}

class CardHeader(QFrame):
    close_requested = Signal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('CardHeader')
        root = QHBoxLayout(self); root.setContentsMargins(10,8,10,8)
        left = QVBoxLayout(); self.title=QLabel(); self.route=QLabel(); self.route.setObjectName('Muted')
        left.addWidget(self.title); left.addWidget(self.route); root.addLayout(left, 1)
        self.status=QLabel(); self.score=QLabel(); self.latency=QLabel(); self.connection=QLabel(); self.exchange_status=QLabel()
        for w in (self.status,self.score,self.latency,self.connection,self.exchange_status): w.setObjectName('Pill'); root.addWidget(w)
        self.close_button=QPushButton('❌'); self.close_button.setObjectName('CloseButton'); self.close_button.clicked.connect(self.close_requested)
        root.addWidget(self.close_button)
    def update_data(self, data: CardData):
        self.title.setText(data.symbol); self.route.setText(f'{data.long_exchange.upper()} → {data.short_exchange.upper()}')
        self.status.setText(data.mode.value); self.status.setStyleSheet(f"background:{MODE_COLORS.get(data.mode, '#7b8494')}; color:#071019;")
        self.score.setText(f'Score {data.score}'); self.latency.setText(f'Latency {data.latency}')
        self.connection.setText(data.connection); self.exchange_status.setText(data.exchange_status)
