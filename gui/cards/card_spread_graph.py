from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget
from gui.card_data import CardData

class CardSpreadGraph(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent); self.setMinimumHeight(120); self._points=()
    def update_data(self,data:CardData):
        points=data.graph_points[-3000:]
        if points != self._points:
            self._points=points; self.update()
    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing); r=self.rect().adjusted(8,8,-8,-8)
        p.fillRect(self.rect(), QColor('#0b1622')); p.setPen(QPen(QColor('#203247'),1))
        for i in range(6): y=r.top()+i*r.height()/5; p.drawLine(r.left(),int(y),r.right(),int(y))
        if len(self._points)<2: return
        vals=[v for _,g,n in self._points for v in (g,n)]; mn=min(vals); mx=max(vals); span=(mx-mn) or 1
        def draw(idx,color):
            p.setPen(QPen(QColor(color),2)); prev=None; count=len(self._points)
            for i,pt in enumerate(self._points):
                x=r.left()+i*r.width()/max(1,count-1); y=r.bottom()-((pt[idx]-mn)/span)*r.height()
                if prev: p.drawLine(prev[0],prev[1],int(x),int(y))
                prev=(int(x),int(y))
        draw(1,'#24d18b'); draw(2,'#ff4d5e')
