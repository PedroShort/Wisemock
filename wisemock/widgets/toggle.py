"""iOS-style toggle switch."""
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRectF, QSize, pyqtProperty
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import QAbstractButton


class ToggleSwitch(QAbstractButton):
    def __init__(self, parent=None, checked=False):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(44, 26)
        self.setCursor(Qt.PointingHandCursor)
        self._offset = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)
        self.toggled.connect(self._animate)

    def _get_offset(self):
        return self._offset

    def _set_offset(self, value):
        self._offset = value
        self.update()

    offset = pyqtProperty(float, _get_offset, _set_offset)

    def _animate(self, checked):
        self._anim.stop()
        self._anim.setStartValue(self._offset)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def sizeHint(self):
        return QSize(44, 26)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        track_color = QColor("#3c3c3c") if self.isChecked() else QColor("#d0d0d0")
        p.setBrush(track_color)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(0, 0, 44, 26), 13, 13)
        knob_x = 2 + self._offset * 18
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(knob_x, 2, 22, 22))
        p.end()
