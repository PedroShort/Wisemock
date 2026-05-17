"""Performance tab — shows exam history with stats and per-record review dialog."""
from datetime import datetime

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QFileDialog, QFrame, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from wisemock.config import PDF_SUPPORT
from wisemock.core.grading import compute_results
from wisemock.core.history import format_seconds, load_history, save_history
from wisemock.export.exam_file import export_exam_file_dialog
from wisemock.export.pdf import _build_pdf_html, _render_pdf


class PerformanceTab(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("SetupRoot")
        self._build_ui()

    def _build_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: #e8e8e8; border: none; }")
        inner = QWidget()
        inner.setObjectName("SetupRoot")
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(40, 32, 40, 32)
        layout.setSpacing(20)
        title = QLabel("Performance")
        title.setObjectName("GuideTitle")
        layout.addWidget(title)
        sub = QLabel("Track your progress across all mock exams.")
        sub.setObjectName("GuideSubtitle")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        self._stats_row = QHBoxLayout()
        self._stats_row.setSpacing(16)
        self._stat_total = self._make_stat_card("0", "EXAMS TAKEN")
        self._stat_avg = self._make_stat_card("—", "AVERAGE SCORE")
        self._stat_best = self._make_stat_card("—", "BEST SCORE")
        self._stat_time = self._make_stat_card("0h", "TOTAL STUDY TIME")
        for card in (self._stat_total, self._stat_avg, self._stat_best, self._stat_time):
            self._stats_row.addWidget(card)
        layout.addLayout(self._stats_row)

        layout.addWidget(self._make_section_label("RECENT EXAMS"))
        self._table = QTableWidget()
        self._table.setObjectName("HistoryTable")
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(["Date", "Title", "Score", "Questions", "Time"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setMinimumHeight(300)
        self._table.setToolTip("Double-click an exam to review your answers")
        self._table.doubleClicked.connect(self._on_row_double_click)
        layout.addWidget(self._table, 1)

        self._empty_label = QLabel("No exams yet — complete a mock to see your history here.")
        self._empty_label.setObjectName("EmptyHistory")
        self._empty_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._empty_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("SecondaryButton")
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.setToolTip("Reload history from disk")
        refresh_btn.clicked.connect(self.refresh)
        btn_row.addWidget(refresh_btn)
        clear_btn = QPushButton("Clear History")
        clear_btn.setObjectName("SecondaryButton")
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setToolTip("Delete all saved exam history")
        clear_btn.clicked.connect(self._clear_history)
        btn_row.addWidget(clear_btn)
        layout.addLayout(btn_row)

        scroll.setWidget(inner)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)
        self.refresh()

    def _make_stat_card(self, value: str, label: str) -> QFrame:
        card = QFrame()
        card.setObjectName("StatCard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(4)
        lay.setAlignment(Qt.AlignCenter)
        val = QLabel(value)
        val.setObjectName("StatValue")
        val.setAlignment(Qt.AlignCenter)
        card._value_label = val
        lbl = QLabel(label)
        lbl.setObjectName("StatLabel")
        lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(val)
        lay.addWidget(lbl)
        return card

    def _make_section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("SettingGroupLabel")
        return lbl

    def refresh(self):
        records = load_history()
        self._records = list(reversed(records))
        n = len(records)
        self._stat_total._value_label.setText(str(n))
        if n > 0:
            scores = [r.get("score_pct", 0) for r in records]
            avg, best = sum(scores) / len(scores), max(scores)
            total_time = sum(r.get("time_spent_seconds", 0) for r in records)
            hours = total_time / 3600
            self._stat_avg._value_label.setText(f"{avg:.0f}%")
            self._stat_best._value_label.setText(f"{best:.0f}%")
            self._stat_time._value_label.setText(f"{hours:.1f}h" if hours >= 1 else f"{total_time // 60}min")
        else:
            self._stat_avg._value_label.setText("—")
            self._stat_best._value_label.setText("—")
            self._stat_time._value_label.setText("0h")

        self._table.setRowCount(0)
        self._empty_label.setVisible(n == 0)
        self._table.setVisible(n > 0)
        for record in reversed(records):
            row = self._table.rowCount()
            self._table.insertRow(row)
            try:
                dt = datetime.fromisoformat(record["date"])
                date_str = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, KeyError):
                date_str = "—"
            self._table.setItem(row, 0, QTableWidgetItem(date_str))
            self._table.setItem(row, 1, QTableWidgetItem(record.get("title", "—")))
            score_item = QTableWidgetItem(f"{record.get('score_pct', 0):.0f}%")
            score_item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row, 2, score_item)
            q_item = QTableWidgetItem(f"{record.get('correct', 0)}/{record.get('total', 0)}")
            q_item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row, 3, q_item)
            time_item = QTableWidgetItem(format_seconds(record.get("time_spent_seconds", 0)))
            time_item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row, 4, time_item)

    def _on_row_double_click(self, index):
        row = index.row()
        if row < 0 or row >= len(self._records):
            return
        record = self._records[row]
        questions = record.get("questions")
        answers = record.get("answers")
        if not questions:
            QMessageBox.information(
                self, "Not available",
                "Detailed review is not available for this exam.\n"
                "Only exams taken after this feature was added can be reviewed."
            )
            return

        results = compute_results(questions, answers)
        auto_graded = [r for r in results.values() if r in ("correct", "incorrect", "unanswered")]
        auto_correct = sum(1 for r in auto_graded if r == "correct")
        auto_total = len(auto_graded)
        score_pct = round(auto_correct / auto_total * 100) if auto_total > 0 else 0

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Review — {record.get('title', 'Exam')}")
        dlg.resize(700, 600)
        dlg_layout = QVBoxLayout(dlg)

        header = QLabel(
            f"<b>{record.get('title', 'Exam')}</b> &nbsp; | &nbsp; "
            f"Score: {score_pct}% &nbsp; | &nbsp; {auto_correct}/{auto_total} correct"
        )
        header.setStyleSheet(
            "font-size: 15px; padding: 10px 14px; background: #f0f0f0;"
            " border-left: 4px solid #3c3c3c; border-radius: 4px;"
        )
        dlg_layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(16)
        content_layout.setContentsMargins(12, 12, 12, 12)

        for i, q in enumerate(questions, 1):
            q_id = q.get("id", "")
            q_type = q.get("type", "")
            result = results.get(q_id, "")
            answer = (answers or {}).get(q_id, {})

            _result_styles = {
                "correct": ("#27ae60", "#fafafa", "✓"),
                "incorrect": ("#c0392b", "#fdf0f0", "✗"),
                "unanswered": ("#d0a020", "#fdf8e8", "—"),
                "open": ("#777", "#f5f5f5", "✎"),
            }
            border_color, bg_color, icon = _result_styles.get(result, ("#bbb", "#fafafa", "—"))

            q_frame = QFrame()
            q_frame.setStyleSheet(
                f"QFrame {{ background: {bg_color}; border: 1px solid {border_color};"
                f" border-left: 4px solid {border_color}; border-radius: 4px; padding: 12px; }}"
            )
            q_lay = QVBoxLayout(q_frame)
            q_lay.setSpacing(6)
            title_lbl = QLabel(f"<b>{icon} Q{i}. {q.get('title', '')}</b>")
            title_lbl.setWordWrap(True)
            title_lbl.setStyleSheet("background: transparent; font-size: 14px;")
            q_lay.addWidget(title_lbl)

            if q_type == "mc":
                options = q.get("options", [])
                correct_letter = q.get("correct_answer", "").upper()
                selected = answer.get("selected_letter", "").upper() if isinstance(answer, dict) else ""
                for j, opt in enumerate(options):
                    letter = chr(ord("A") + j)
                    is_correct = letter == correct_letter
                    is_selected = letter == selected
                    if is_correct and is_selected:
                        prefix, color, weight, bg = "✓", "#27ae60", "bold", "rgba(39,174,96,0.10)"
                    elif is_selected and not is_correct:
                        prefix, color, weight, bg = "✗", "#c0392b", "bold", "rgba(192,57,43,0.08)"
                    elif is_correct and not is_selected:
                        prefix, color, weight, bg = "→", "#27ae60", "600", "rgba(39,174,96,0.06)"
                    else:
                        prefix, color, weight, bg = " ", "#999", "normal", "transparent"
                    opt_lbl = QLabel(f"  {prefix}  {letter})  {opt}")
                    opt_lbl.setStyleSheet(
                        f"background: {bg}; font-size: 13px; color: {color};"
                        f" font-weight: {weight}; padding: 3px 6px;"
                        f" border-radius: 3px; margin: 1px 0;"
                    )
                    q_lay.addWidget(opt_lbl)
            elif q_type == "open":
                student_text = (answer.get("text", "") or answer.get("value", "")) if isinstance(answer, dict) else str(answer)
                if student_text:
                    ans_lbl = QLabel(f"<b>Your answer:</b><br>{student_text}")
                else:
                    ans_lbl = QLabel("<b>Your answer:</b> <i>No answer provided</i>")
                ans_lbl.setWordWrap(True)
                ans_lbl.setStyleSheet(
                    "background: white; font-size: 13px; padding: 8px;"
                    " border: 1px solid #ddd; border-radius: 3px;"
                )
                q_lay.addWidget(ans_lbl)
                suggested = q.get("suggested_answer", "")
                if suggested:
                    sug_lbl = QLabel(f"<b>Suggested answer:</b><br>{suggested}")
                    sug_lbl.setWordWrap(True)
                    sug_lbl.setStyleSheet(
                        "background: rgba(39,174,96,0.06); font-size: 13px; color: #1e6a3f;"
                        " padding: 8px; border: 1px solid #a9dfbf; border-left: 4px solid #27ae60;"
                        " border-radius: 3px;"
                    )
                    q_lay.addWidget(sug_lbl)
            elif q_type == "fill_blank":
                selected_texts = answer.get("selected_texts", []) if isinstance(answer, dict) else []
                correct_answers = q.get("correct_answers", [])
                blanks = q.get("blanks", [])
                for b_idx, sel in enumerate(selected_texts):
                    correct_idx = correct_answers[b_idx] if b_idx < len(correct_answers) else -1
                    correct_text = blanks[b_idx][correct_idx] if b_idx < len(blanks) and 0 <= correct_idx < len(blanks[b_idx]) else "?"
                    if sel == correct_text:
                        bl_lbl = QLabel(f"  ✓  Blank {b_idx + 1}: {sel}")
                        bl_lbl.setStyleSheet(
                            "background: rgba(39,174,96,0.08); font-size: 13px; color: #27ae60;"
                            " font-weight: bold; padding: 3px 6px; border-radius: 3px;"
                        )
                    else:
                        bl_lbl = QLabel(f"  ✗  Blank {b_idx + 1}: {sel}  →  {correct_text}")
                        bl_lbl.setStyleSheet(
                            "background: rgba(192,57,43,0.08); font-size: 13px; color: #c0392b;"
                            " font-weight: bold; padding: 3px 6px; border-radius: 3px;"
                        )
                    q_lay.addWidget(bl_lbl)
            content_layout.addWidget(q_frame)

        content_layout.addStretch()
        scroll.setWidget(content)
        dlg_layout.addWidget(scroll, 1)

        close_btn = QPushButton("Close")
        close_btn.setObjectName("PrimaryButton")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(dlg.accept)
        btn_row = QHBoxLayout()
        if PDF_SUPPORT:
            export_btn = QPushButton("Export PDF")
            export_btn.setCursor(Qt.PointingHandCursor)
            export_btn.setStyleSheet(
                "QPushButton { background: #4a4a4a; color: #fff; border: none;"
                " border-radius: 4px; padding: 8px 18px; font-weight: 600; }"
                "QPushButton:hover { background: #333; }"
            )
            export_btn.clicked.connect(
                lambda: self._export_review_pdf(dlg, record.get("title", "Exam"), questions, answers, results)
            )
            btn_row.addWidget(export_btn)
        export_exam_btn = QPushButton("Export Exam File")
        export_exam_btn.setCursor(Qt.PointingHandCursor)
        export_exam_btn.setToolTip(
            "Save this exam as a .exam.json file you can re-import without using AI again."
        )
        export_exam_btn.setStyleSheet(
            "QPushButton { background: #fff; color: #1a1a1a; border: 1px solid #ccc;"
            " border-radius: 4px; padding: 8px 18px; font-weight: 600; }"
            "QPushButton:hover { background: #f2f2f2; }"
        )
        export_exam_btn.clicked.connect(
            lambda: export_exam_file_dialog(
                dlg,
                {"title": record.get("title", "Exam"),
                 "questions": questions,
                 "sections": record.get("sections")},
                default_stem=record.get("title", "exam"),
            )
        )
        btn_row.addWidget(export_exam_btn)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        dlg_layout.addLayout(btn_row)
        dlg.exec_()

    def _export_review_pdf(self, parent_dlg, title, questions, answers, results):
        path, _ = QFileDialog.getSaveFileName(
            parent_dlg, "Export review as PDF", f"{title}_review.pdf", "PDF files (*.pdf)"
        )
        if not path:
            return
        html = _build_pdf_html(title, "Review export", questions, answers, results)
        _render_pdf(html, path)
        QMessageBox.information(parent_dlg, "Exported", f"PDF saved to:\n{path}")

    def _clear_history(self):
        reply = QMessageBox.question(
            self, "Clear history", "Are you sure you want to delete all exam history?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            save_history([])
            self.refresh()
