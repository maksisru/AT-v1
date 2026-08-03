from PySide6.QtWidgets import QCheckBox, QDoubleSpinBox, QFrame, QGridLayout, QLabel, QPushButton, QSpinBox

class CardControlPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent); self.setObjectName('Panel')
        g=QGridLayout(self); g.setContentsMargins(10,8,10,8); g.setHorizontalSpacing(8)
        self.auto=QCheckBox('Auto'); self.long=QCheckBox('Long'); self.short=QCheckBox('Short')
        for i,w in enumerate((self.auto,self.long,self.short)): g.addWidget(w,0,i)
        fields=[('Open Spread', QDoubleSpinBox()),('Close Spread', QDoubleSpinBox()),('Order Size', QDoubleSpinBox()),('Leverage', QSpinBox()),('Max Orders', QSpinBox()),('Force Stop', QDoubleSpinBox()),('Total Stop', QDoubleSpinBox())]
        self.inputs={}
        for row,(name,widget) in enumerate(fields,1):
            if hasattr(widget,'setDecimals'): widget.setDecimals(4); widget.setMaximum(1_000_000)
            else: widget.setMaximum(1000)
            self.inputs[name]=widget; g.addWidget(QLabel(name),row,0); g.addWidget(widget,row,1,1,2)
        for col,text in enumerate(('Start','Stop','Restart')):
            btn=QPushButton(text); btn.setObjectName(text); g.addWidget(btn, len(fields)+1, col)
