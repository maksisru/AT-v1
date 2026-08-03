from PySide6.QtWidgets import QMainWindow, QToolBar
from gui.cards.arbitrage_card import ArbitrageCard
from gui.new_card_dialog import NewCardDialog
from gui.terminal_service import TerminalService
from gui.workspace import Workspace

STYLE='''QMainWindow{background:#071019;color:#d8e2ef} #Workspace{background:#071019;border:0} #ArbitrageCard{background:#111e2b;border:1px solid #26384c;border-radius:10px} #CardHeader{background:#17283a;border-radius:10px} QLabel{color:#d8e2ef} #Muted{color:#8fa3bb} #Pill{border-radius:7px;padding:3px 7px;background:#24364a} #Panel{background:#0e1a27;border-top:1px solid #203247} QLineEdit,QComboBox,QDoubleSpinBox,QSpinBox{background:#071019;color:#d8e2ef;border:1px solid #2b4058;border-radius:4px;padding:3px} QPushButton{background:#1f6feb;color:white;border:0;border-radius:4px;padding:5px 9px} #CloseButton{background:transparent;color:#ff6b76} #Stop{background:#9d2634}'''
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle('Arbitrage Terminal'); self.resize(1440,900); self.setStyleSheet(STYLE)
        self.service=TerminalService(self); self.workspace=Workspace(); self.setCentralWidget(self.workspace)
        tb=QToolBar('Terminal'); self.addToolBar(tb); action=tb.addAction('➕ Новая карточка'); action.triggered.connect(self.open_new_card_dialog)
        self.service.card_created.connect(self._add_card); self.service.card_updated.connect(self._update_card); self.service.card_removed.connect(self.workspace.remove_card)
    def open_new_card_dialog(self):
        dlg=NewCardDialog(self)
        if dlg.exec(): self.service.create_card(*dlg.values())
    def _add_card(self,data):
        card=ArbitrageCard(data); card.remove_requested.connect(self.service.remove_card); self.workspace.add_card(card)
    def _update_card(self,data):
        card=self.workspace.cards.get(data.card_id)
        if card: card.update_data(data)
