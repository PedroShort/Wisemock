"""Fill-in-the-blank question widget."""
import re

from PyQt5.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget


class FillBlankQuestion(QWidget):
    """
    JSON format:
    {
      "id": "q1", "type": "fill_blank",
      "title": "Fill in the blanks:",
      "template": "for x in items:\\n    if {0}:\\n        {1}",
      "blanks": [
        ["option A", "option B"],
        ["option C", "option D"]
      ],
      "correct_answers": [0, 1]   <- optional, only used in exports
    }
    """

    def __init__(self, question_id: str, title: str, template: str, blanks: list):
        super().__init__()
        self.question_id = question_id
        self.combos: list[QComboBox] = []
        self._result_labels: list[QLabel] = []
        self._build_ui(title, template, blanks)

    def _build_ui(self, title: str, template: str, blanks: list):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 18)
        layout.setSpacing(10)
        title_label = QLabel(title)
        title_label.setObjectName("QuestionTitle")
        title_label.setWordWrap(True)
        layout.addWidget(title_label)

        template_frame = QFrame()
        template_frame.setObjectName("FillBlankTemplate")
        tpl_layout = QVBoxLayout(template_frame)
        tpl_layout.setContentsMargins(14, 10, 14, 10)
        tpl_layout.setSpacing(4)

        segments = re.split(r'(\{\d+\})', template)
        lines = [[]]
        for seg in segments:
            m = re.fullmatch(r'\{(\d+)\}', seg)
            if m:
                idx = int(m.group(1))
                if idx < len(blanks):
                    combo = QComboBox()
                    combo.addItem("— select —")
                    for opt in blanks[idx]:
                        combo.addItem(opt)
                    combo.setMinimumWidth(140)
                    combo.setStyleSheet(
                        "QComboBox { background: #fff; border: 2px solid #4a90c4;"
                        " border-radius: 3px; padding: 4px 8px; font-size: 13px;"
                        " font-weight: 600; min-height: 26px; }"
                        "QComboBox:focus { border-color: #2d6cdf; }"
                    )
                    result_lbl = QLabel("")
                    result_lbl.setFixedWidth(20)
                    result_lbl.setStyleSheet("font-size: 13px; font-weight: 700; background: transparent;")
                    self.combos.append(combo)
                    self._result_labels.append(result_lbl)
                    lines[-1].append(combo)
                    lines[-1].append(result_lbl)
            else:
                sub_lines = seg.split('\n')
                for si, sl in enumerate(sub_lines):
                    if si > 0:
                        lines.append([])
                    if sl:
                        txt = QLabel(sl)
                        txt.setStyleSheet(
                            "font-family: Consolas, 'Courier New', monospace;"
                            " font-size: 13px; color: #333; background: transparent;"
                        )
                        lines[-1].append(txt)

        for line_widgets in lines:
            row = QHBoxLayout()
            row.setSpacing(4)
            row.setContentsMargins(0, 0, 0, 0)
            for w in line_widgets:
                row.addWidget(w)
            row.addStretch()
            tpl_layout.addLayout(row)

        layout.addWidget(template_frame)

    def get_answer(self):
        answers = []
        for combo in self.combos:
            answers.append(None if combo.currentIndex() == 0 else combo.currentText())
        if all(a is None for a in answers):
            return None
        return {"selected_texts": answers}

    def show_result(self, correct_indices: list):
        all_correct = True
        for i, (combo, lbl, correct_idx) in enumerate(
            zip(self.combos, self._result_labels, correct_indices)
        ):
            student_idx = combo.currentIndex() - 1
            ok = student_idx == correct_idx
            if not ok:
                all_correct = False
            lbl.setText("✓ correct" if ok else "✗ wrong")
            lbl.setStyleSheet(
                f"color: {'#2a9e50' if ok else '#c23b3b'};"
                " font-size: 13px; font-weight: 700; background: transparent;"
            )
        badge = QLabel("✓ Correct" if all_correct else "✗ Incorrect")
        badge.setStyleSheet(
            f"color: {'#2a9e50' if all_correct else '#c23b3b'};"
            " font-size: 13px; font-weight: 700; background: transparent;"
        )
        self.layout().insertWidget(0, badge)
