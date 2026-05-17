"""Clickable lettered option used inside multiple-choice questions."""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout

from wisemock.widgets.helpers import _restyle_widget


class ClickableOption(QPushButton):
    def __init__(self, letter: str, text: str, selected: bool = False):
        super().__init__()
        self.letter = letter
        self.text = text
        self.selected = selected
        self.container = None
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setMinimumHeight(52)
        self._build_ui()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.container = QFrame()
        self.container.setObjectName("OptionCardSelected" if self.selected else "OptionCard")
        container_layout = QHBoxLayout(self.container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        container_layout.setAlignment(Qt.AlignTop)
        letter_box = QLabel(self.letter)
        letter_box.setObjectName("LetterBox")
        letter_box.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        letter_box.setContentsMargins(0, 12, 0, 0)
        text_wrap = QFrame()
        text_wrap.setStyleSheet("background: transparent;")
        text_layout = QVBoxLayout(text_wrap)
        text_layout.setContentsMargins(10, 10, 10, 10)
        text_layout.setSpacing(0)
        text_box = QLabel(self.text)
        text_box.setObjectName("OptionTextBox")
        text_box.setWordWrap(True)
        text_layout.addWidget(text_box)
        container_layout.addWidget(letter_box)
        container_layout.addWidget(text_wrap, 1)
        root.addWidget(self.container)

    def set_selected(self, value: bool):
        self.selected = value
        self.container.setObjectName("OptionCardSelected" if value else "OptionCard")
        _restyle_widget(self.container)

    def set_result(self, state: str):
        name_map = {"correct": "OptionCardCorrect", "wrong": "OptionCardWrong", "missed": "OptionCardCorrect"}
        self.container.setObjectName(name_map.get(state, "OptionCard"))
        _restyle_widget(self.container)
