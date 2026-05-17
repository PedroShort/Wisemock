"""Shared widget helpers — restyling and button animation."""
from PyQt5.QtCore import QTimer


def _restyle_widget(widget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def _start_btn_animation(owner, btn, timer_attr, dots_attr, label):
    """Shared animation starter for generate/parse buttons."""
    setattr(owner, dots_attr, 0)
    timer = QTimer(owner)
    setattr(owner, timer_attr, timer)
    def animate():
        d = (getattr(owner, dots_attr) % 3) + 1
        setattr(owner, dots_attr, d)
        btn.setText(label + "." * d)
    timer.timeout.connect(animate)
    timer.start(400)
    animate()


def _stop_btn_animation(owner, btn, timer_attr, default_text):
    """Shared animation stopper for generate/parse buttons."""
    timer = getattr(owner, timer_attr, None)
    if timer and timer.isActive():
        timer.stop()
    btn.setText(default_text)
    btn.setEnabled(True)
