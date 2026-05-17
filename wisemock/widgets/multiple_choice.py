"""Multiple-choice question widget."""
import re

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from wisemock.widgets.option import ClickableOption


class MultipleChoiceQuestion(QWidget):
    def __init__(self, question_id: str, title: str, options: list, allow_multiple: bool = False):
        super().__init__()
        self.question_id = question_id
        self.option_widgets = []
        self.allow_multiple = allow_multiple
        self.selected_index = None
        self.selected_indices = set()
        self._build_ui(title, options)

    def _build_ui(self, title: str, options: list):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 18)
        layout.setSpacing(10)
        title_label = QLabel(title)
        title_label.setObjectName("QuestionTitle")
        title_label.setWordWrap(True)
        layout.addWidget(title_label)
        if self.allow_multiple:
            hint = QLabel("Select all that apply")
            hint.setStyleSheet("color: #888888; font-size: 12px; font-style: italic;")
            layout.addWidget(hint)
        letters = ["A", "B", "C", "D", "E", "F", "G", "H"]
        for i, text in enumerate(options):
            cleaned = re.sub(r'^[A-Ha-h]\s*[\.\)\-]\s*', '', text).strip()
            option = ClickableOption(letter=letters[i], text=cleaned if cleaned else text)
            option.clicked.connect(lambda checked=False, idx=i: self.select_option(idx))
            self.option_widgets.append(option)
            layout.addWidget(option)

    def select_option(self, idx: int):
        if not self.isEnabled():
            return
        if self.allow_multiple:
            if idx in self.selected_indices:
                self.selected_indices.discard(idx)
                self.option_widgets[idx].set_selected(False)
            else:
                self.selected_indices.add(idx)
                self.option_widgets[idx].set_selected(True)
        else:
            self.selected_index = idx
            for i, opt in enumerate(self.option_widgets):
                opt.set_selected(i == idx)

    def get_answer(self):
        letters = ["A", "B", "C", "D", "E", "F", "G", "H"]
        if self.allow_multiple:
            if not self.selected_indices:
                return None
            s = sorted(self.selected_indices)
            return {
                "selected_indices": s,
                "selected_letters": [letters[i] for i in s],
                "selected_texts": [self.option_widgets[i].text for i in s],
            }
        else:
            if self.selected_index is None:
                return None
            return {
                "selected_index": self.selected_index,
                "selected_letter": chr(ord("A") + self.selected_index),
                "selected_text": self.option_widgets[self.selected_index].text,
            }

    def show_result(self, correct_letter):
        # `correct_letter` may be a single letter string ("C") or a list of
        # letters (["A", "C"]) when the question is multi-answer.
        if isinstance(correct_letter, list):
            correct_indices = {ord(str(letter).strip().upper()) - ord("A")
                               for letter in correct_letter if str(letter).strip()}
        else:
            correct_indices = {ord(str(correct_letter).strip().upper()) - ord("A")} if str(correct_letter).strip() else set()
        for i, opt in enumerate(self.option_widgets):
            if i in correct_indices:
                if self.allow_multiple:
                    state = "correct" if i in self.selected_indices else "missed"
                else:
                    state = "correct"
                opt.set_result(state)
            elif (not self.allow_multiple and self.selected_index == i) or \
                 (self.allow_multiple and i in self.selected_indices):
                opt.set_result("wrong")
        if self.allow_multiple:
            result_ok = set(self.selected_indices) == correct_indices
        else:
            result_ok = self.selected_index in correct_indices
        badge = QLabel("✓ Correct" if result_ok else "✗ Incorrect")
        badge.setStyleSheet(
            f"color: {'#2a9e50' if result_ok else '#c23b3b'};"
            " font-size: 13px; font-weight: 700; background: transparent;"
        )
        self.layout().insertWidget(0, badge)
