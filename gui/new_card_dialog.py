from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLineEdit

EXCHANGES=['Bybit','OKX','Binance','MEXC','Gate','Bitget']
class NewCardDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent); self.setWindowTitle('Новая карточка')
        form=QFormLayout(self); self.symbol=QLineEdit('BTCUSDT'); self.long_exchange=QComboBox(); self.short_exchange=QComboBox()
        self.long_exchange.addItems(EXCHANGES); self.short_exchange.addItems(EXCHANGES); self.short_exchange.setCurrentText('MEXC')
        form.addRow('Символ',self.symbol); form.addRow('Биржа LONG',self.long_exchange); form.addRow('Биржа SHORT',self.short_exchange)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); buttons.button(QDialogButtonBox.Ok).setText('Создать'); buttons.button(QDialogButtonBox.Cancel).setText('Отмена')
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); form.addWidget(buttons)
    def values(self): return self.symbol.text().strip() or 'BTCUSDT', self.long_exchange.currentText(), self.short_exchange.currentText()
