"""Assessment page — the live exam-taking screen and its wrapping window."""
import copy
import json
import os
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QProgressBar, QPushButton, QScrollArea, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from wisemock.config import PDF_SUPPORT
from wisemock.core.grading import compute_results
from wisemock.core.history import add_history_entry, format_seconds
from wisemock.export.pdf import _build_pdf_html, _render_pdf
from wisemock.prompts import FULL_REVIEW_PROMPT
from wisemock.runtime.geometry import fit_window_to_screen
from wisemock.widgets.fill_blank import FillBlankQuestion
from wisemock.widgets.multiple_choice import MultipleChoiceQuestion
from wisemock.widgets.open_ended import OpenEndedQuestion
from wisemock.workers import FullReviewWorker

# `random` is used inside _create_question_widget when shuffle_options is on
import random


class AssessmentPage(QWidget):
    def __init__(self, config: dict, exam_data: dict):
        super().__init__()
        self.config = config
        self.exam_data = exam_data
        self.remaining_seconds = int(config["exam_duration_seconds"])
        self.time_up = False
        self.is_submitted = False
        self.question_widgets = []
        self.main_content_widgets = []
        self.timer_label = None
        self.time_up_banner = None
        self.countdown_timer = QTimer(self)
        self.countdown_timer.timeout.connect(self.update_countdown)
        self._build_ui()
        self.countdown_timer.start(1000)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(0)
        card = QFrame()
        card.setObjectName("PageCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(36, 30, 36, 30)
        card_layout.setSpacing(18)

        top_row = QHBoxLayout()
        title = QLabel(self.config["exam_title"])
        title.setObjectName("SectionTitle")
        self.timer_label = QLabel(f"⏳ Time left: {format_seconds(self.remaining_seconds)}")
        self.timer_label.setObjectName("TimerBox")
        self.timer_label.setAlignment(Qt.AlignCenter)
        self._paused = False
        self.pause_btn = QPushButton("⏸")
        self.pause_btn.setToolTip("Pause exam")
        self.pause_btn.setCursor(Qt.PointingHandCursor)
        self.pause_btn.setFixedSize(36, 36)
        self.pause_btn.setStyleSheet(
            "QPushButton { font-size: 16px; background: #f0f0f0; border: 1px solid #ccc;"
            " border-radius: 4px; color: #555; padding: 0; text-align: center;"
            " line-height: 36px; }"
            "QPushButton:hover { background: #e0e0e0; }"
        )
        self.pause_btn.clicked.connect(self._toggle_pause)
        exit_btn = QPushButton("Exit")
        exit_btn.setObjectName("DangerButton")
        exit_btn.setCursor(Qt.PointingHandCursor)
        exit_btn.setFixedWidth(100)
        exit_btn.clicked.connect(self.handle_exit)
        top_row.addWidget(title, 1)
        top_row.addWidget(self.timer_label)
        top_row.addSpacing(6)
        top_row.addWidget(self.pause_btn)
        top_row.addSpacing(6)
        top_row.addWidget(exit_btn)

        self.time_up_banner = QLabel("Time is over. The exam is locked. You can only click Submit.")
        self.time_up_banner.setObjectName("TimeUpBanner")
        self.time_up_banner.hide()
        self.score_banner = QLabel("")
        self.score_banner.setObjectName("ScoreBanner")
        self.score_banner.hide()
        card_layout.addLayout(top_row)

        self._total_seconds = int(self.config["exam_duration_seconds"])
        self._total_ms = self._total_seconds * 1000
        self._elapsed_ms = 0
        self.time_bar = QProgressBar()
        self.time_bar.setRange(0, self._total_ms)
        self.time_bar.setValue(self._total_ms)
        self.time_bar.setTextVisible(False)
        self.time_bar.setFixedHeight(6)
        self.time_bar.setStyleSheet(
            "QProgressBar { background: #e0e0e0; border: none; border-radius: 3px; }"
            "QProgressBar::chunk { background: #3c3c3c; border-radius: 3px; }"
        )
        card_layout.addWidget(self.time_bar)

        self._bar_timer = QTimer(self)
        self._bar_timer.timeout.connect(self._update_bar)
        self._bar_timer.start(50)

        card_layout.addWidget(self.time_up_banner)
        card_layout.addWidget(self.score_banner)

        for block in self.exam_data.get("intro", []):
            btype = block.get("type")
            if btype in ("text", "code"):
                label = QLabel(block.get("content", ""))
                label.setObjectName("BodyText" if btype == "text" else "CodeBlock")
                label.setWordWrap(True)
                if btype == "text":
                    label.setTextFormat(Qt.RichText)
                else:
                    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
                card_layout.addWidget(label)
                self.main_content_widgets.append(label)

        card_layout.addSpacing(8)

        questions_data = copy.deepcopy(list(self.exam_data.get("questions", [])))
        self.questions_data = questions_data

        # Multi-answer is now per-question (driven by `correct_answer` shape).
        # No global flag.
        shuffle_opts = self.config.get("shuffle_options", False)
        show_numbers = True  # always-on; was previously a removed setup toggle

        sections = self.exam_data.get("sections")
        if sections:
            self._section_tabs = QTabWidget()
            self._section_tabs.setStyleSheet(
                "QTabWidget::pane { border: none; border-top: 1px solid #d0d0d0; background: white; }"
                "QTabBar { background: transparent; }"
                "QTabBar::tab { background: transparent; color: #888; padding: 8px 20px;"
                " border: none; border-bottom: 3px solid transparent;"
                " font-size: 13px; font-weight: 600; margin-right: 2px; }"
                "QTabBar::tab:selected { color: #333; border-bottom: 3px solid #4a4a4a; }"
                "QTabBar::tab:hover:!selected { color: #555; border-bottom: 3px solid #ccc; }"
            )
            q_data_map = {q["id"]: q for q in questions_data}
            global_num = 0
            for sec in sections:
                sec_widget = QWidget()
                sec_layout = QVBoxLayout(sec_widget)
                sec_layout.setContentsMargins(8, 16, 8, 16)
                sec_layout.setSpacing(14)
                instr = sec.get("instructions", "").strip()
                if instr:
                    instr_lbl = QLabel(instr)
                    instr_lbl.setWordWrap(True)
                    instr_lbl.setStyleSheet(
                        "font-size: 13px; color: #555; font-style: italic;"
                        " background: transparent; padding: 4px 0;"
                    )
                    sec_layout.addWidget(instr_lbl)
                sec_questions = copy.deepcopy(sec.get("questions", []))
                if self.config.get("shuffle_questions"):
                    random.shuffle(sec_questions)
                shown_contexts = set()
                for question in sec_questions:
                    global_num += 1
                    q_type = question.get("type")
                    q_id = question.get("id")
                    q_title = question.get("title", "")
                    if q_id in q_data_map:
                        question = q_data_map[q_id]
                    self._render_context(question, shown_contexts, sec_layout)
                    if show_numbers:
                        q_title = f"Q{global_num}. {q_title}"
                    widget = self._create_question_widget(question, q_type, q_id, q_title, shuffle_opts)
                    if widget:
                        self.question_widgets.append(widget)
                        sec_layout.addWidget(widget)
                sec_layout.addStretch()
                sec_scroll = QScrollArea()
                sec_scroll.setWidgetResizable(True)
                sec_scroll.setStyleSheet("QScrollArea { border: none; background: white; }")
                sec_scroll.setWidget(sec_widget)
                self._section_tabs.addTab(sec_scroll, f"  {sec.get('name', 'Section')}  ")
            card_layout.addWidget(self._section_tabs, 1)
        else:
            shown_contexts = set()
            for num, question in enumerate(questions_data, 1):
                q_type = question.get("type")
                q_id = question.get("id")
                q_title = question.get("title", "")
                self._render_context(question, shown_contexts, card_layout)
                if show_numbers:
                    q_title = f"Q{num}. {q_title}"
                widget = self._create_question_widget(question, q_type, q_id, q_title, allow_multi, shuffle_opts)
                if widget:
                    self.question_widgets.append(widget)
                    card_layout.addWidget(widget)

        btn_row = QHBoxLayout()
        submit_btn = QPushButton("Submit")
        submit_btn.setObjectName("PrimaryButton")
        submit_btn.setCursor(Qt.PointingHandCursor)
        submit_btn.setFixedWidth(120)
        submit_btn.clicked.connect(self.handle_submit)
        btn_row.addWidget(submit_btn)

        self._review_btn = QPushButton("Review Mistakes")
        self._review_btn.setObjectName("SecondaryButton")
        self._review_btn.setCursor(Qt.PointingHandCursor)
        self._review_btn.setFixedWidth(150)
        self._review_btn.setToolTip("Review only the questions you got wrong")
        self._review_btn.clicked.connect(self._show_mistakes_review)
        self._review_btn.hide()
        btn_row.addWidget(self._review_btn)

        self._ai_review_btn = QPushButton("AI Study Report")
        self._ai_review_btn.setObjectName("SecondaryButton")
        self._ai_review_btn.setCursor(Qt.PointingHandCursor)
        self._ai_review_btn.setFixedWidth(150)
        self._ai_review_btn.setToolTip("Get a personalised study report from AI based on your results")
        self._ai_review_btn.clicked.connect(self._request_full_ai_review)
        self._ai_review_btn.hide()
        btn_row.addWidget(self._ai_review_btn)
        btn_row.addStretch()

        card_layout.addSpacing(4)
        card_layout.addLayout(btn_row)
        outer.addWidget(card)

    @staticmethod
    def _plain_to_html(text: str) -> str:
        import html as _html
        text = _html.escape(text)
        lines = text.split("\n")
        result, in_list = [], False
        for line in lines:
            stripped = line.strip()
            is_bullet = stripped and stripped[0] in ("•", "-", "*", "–") and len(stripped) > 1
            if is_bullet:
                if not in_list:
                    result.append("<ul style='margin:6px 0 6px 16px;'>")
                    in_list = True
                result.append(f"<li>{stripped[1:].strip()}</li>")
            else:
                if in_list:
                    result.append("</ul>")
                    in_list = False
                if stripped:
                    result.append(f"<p style='margin:4px 0;'>{stripped}</p>")
        if in_list:
            result.append("</ul>")
        return "\n".join(result)

    def _render_context(self, question, shown_contexts, target_layout):
        ctx = question.get("context", "").strip()
        if ctx and ctx not in shown_contexts:
            shown_contexts.add(ctx)
            ctx_frame = QFrame()
            ctx_frame.setObjectName("ContextBlock")
            ctx_frame.setStyleSheet(
                "QFrame#ContextBlock { background: #ffffff; border: 1px solid #d5d5d5;"
                " border-left: 4px solid #4a4a4a; border-radius: 3px;"
                " padding: 14px 16px; margin-top: 8px; }"
            )
            ctx_lay = QVBoxLayout(ctx_frame)
            ctx_lay.setContentsMargins(0, 0, 0, 0)
            ctx_lbl = QLabel(self._plain_to_html(ctx))
            ctx_lbl.setWordWrap(True)
            ctx_lbl.setTextFormat(Qt.RichText)
            ctx_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            ctx_lbl.setStyleSheet("font-size: 13px; color: #333; background: transparent;")
            ctx_lay.addWidget(ctx_lbl)
            target_layout.addWidget(ctx_frame)
            self.main_content_widgets.append(ctx_frame)

    def _create_question_widget(self, question, q_type, q_id, q_title, shuffle_opts):
        if q_type == "mc":
            options = list(question.get("options", []))
            # Per-question multi detection: `correct_answer` may be str or list.
            raw_correct = question.get("correct_answer", "")
            correct_letters = (
                [str(c).strip().upper() for c in raw_correct if str(c).strip()]
                if isinstance(raw_correct, list)
                else ([str(raw_correct).strip().upper()] if str(raw_correct).strip() else [])
            )
            allow_multiple = len(correct_letters) >= 2
            if shuffle_opts and options:
                correct_texts = []
                for letter in correct_letters:
                    idx = ord(letter) - ord("A")
                    if 0 <= idx < len(options):
                        correct_texts.append(options[idx])
                random.shuffle(options)
                new_letters = [
                    chr(ord("A") + options.index(text))
                    for text in correct_texts
                    if text in options
                ]
                if new_letters:
                    question["correct_answer"] = new_letters[0] if len(new_letters) == 1 else new_letters
            return MultipleChoiceQuestion(question_id=q_id, title=q_title,
                                          options=options, allow_multiple=allow_multiple)
        elif q_type == "open":
            return OpenEndedQuestion(question_id=q_id, title=q_title,
                                     placeholder=question.get("placeholder", "Write your answer here..."),
                                     max_words=question.get("max_words"))
        elif q_type == "fill_blank":
            return FillBlankQuestion(question_id=q_id, title=q_title,
                                     template=question.get("template", ""),
                                     blanks=question.get("blanks", []))
        return None

    def _update_bar(self):
        if self.time_up or self.is_submitted or self._paused:
            self._bar_timer.stop()
            return
        self._elapsed_ms += 50
        remaining_ms = max(0, self._total_ms - self._elapsed_ms)
        self.time_bar.setValue(remaining_ms)
        pct = remaining_ms / self._total_ms if self._total_ms else 0
        if pct < 0.1:
            self.time_bar.setStyleSheet(
                "QProgressBar { background: #e0e0e0; border: none; border-radius: 3px; }"
                "QProgressBar::chunk { background: #c0392b; border-radius: 3px; }"
            )
        elif pct < 0.2:
            self.time_bar.setStyleSheet(
                "QProgressBar { background: #e0e0e0; border: none; border-radius: 3px; }"
                "QProgressBar::chunk { background: #e67e22; border-radius: 3px; }"
            )

    def _toggle_pause(self):
        if self.time_up or self.is_submitted:
            return
        self._paused = not self._paused
        if self._paused:
            self.countdown_timer.stop()
            self._bar_timer.stop()
            self.pause_btn.setText("▶")
            self.pause_btn.setToolTip("Resume exam")
            self.timer_label.setText("⏸ Paused")
        else:
            self.countdown_timer.start(1000)
            self._bar_timer.start(50)
            self.pause_btn.setText("⏸")
            self.pause_btn.setToolTip("Pause exam")
            self.timer_label.setText(f"⏳ Time left: {format_seconds(self.remaining_seconds)}")

    def update_countdown(self):
        if self.time_up or self.is_submitted or self._paused:
            return
        self.remaining_seconds -= 1
        if self.remaining_seconds <= 0:
            self.remaining_seconds = 0
            self.timer_label.setText("⏳ Time left: 00:00:00")
            self.time_bar.setValue(0)
            self._bar_timer.stop()
            self._lock_exam()
            self.countdown_timer.stop()
            self.handle_submit()  # always auto-submit when time expires
            return
        self.timer_label.setText(f"⏳ Time left: {format_seconds(self.remaining_seconds)}")

    def _lock_exam(self):
        self.time_up = True
        self.time_up_banner.show()
        for w in self.question_widgets:
            w.setEnabled(False)
        for w in self.main_content_widgets:
            w.setEnabled(False)

    def _collect_answers(self) -> dict:
        return {w.question_id: w.get_answer() for w in self.question_widgets}

    def _build_answer_key(self) -> dict:
        key = {}
        for q in self.questions_data:
            q_id, q_type, entry = q.get("id"), q.get("type"), {}
            if q_type == "mc" and "correct_answer" in q:
                entry["correct_answer"] = q["correct_answer"]
            if q_type == "open" and "suggested_answer" in q:
                entry["suggested_answer"] = q["suggested_answer"]
            if q_type == "fill_blank" and "correct_answers" in q:
                blanks = q.get("blanks", [])
                indices = q["correct_answers"]
                entry["correct_answers_indices"] = indices
                entry["correct_answers_texts"] = [
                    blanks[i][idx] if i < len(blanks) and idx < len(blanks[i]) else "?"
                    for i, idx in enumerate(indices)
                ]
            if entry:
                key[q_id] = entry
        return key

    def _show_feedback(self):
        q_map = {q["id"]: q for q in self.questions_data}
        auto_total, auto_correct = 0, 0
        for widget in self.question_widgets:
            q = q_map.get(widget.question_id, {})
            q_type = q.get("type")
            if q_type == "mc" and "correct_answer" in q:
                auto_total += 1
                widget.show_result(q["correct_answer"])
                answer = widget.get_answer()
                if answer and answer.get("selected_letter") == q["correct_answer"].upper():
                    auto_correct += 1
            elif q_type == "open" and "suggested_answer" in q:
                widget.show_result(suggested_answer=q["suggested_answer"],
                                   api_key=self.config.get("api_key", ""))
            elif q_type == "fill_blank" and "correct_answers" in q:
                auto_total += 1
                correct_indices = q["correct_answers"]
                widget.show_result(correct_indices)
                answer = widget.get_answer()
                if answer:
                    student_texts = answer.get("selected_texts", [])
                    blanks = q.get("blanks", [])
                    all_ok = all(
                        i < len(blanks) and ci < len(blanks[i]) and
                        student_texts[i] == blanks[i][ci]
                        for i, ci in enumerate(correct_indices)
                        if i < len(student_texts)
                    )
                    if all_ok:
                        auto_correct += 1
        if auto_total > 0:
            self.score_banner.setText(
                f"Score: {auto_correct}/{auto_total} auto-graded questions correct"
                + ("  ✓" if auto_correct == auto_total else "")
            )
            self.score_banner.show()

    def _export_json(self, answers: dict, results: dict = None):
        answer_key = self._build_answer_key()
        questions_summary = []
        for q in self.exam_data.get("questions", []):
            q_id = q.get("id")
            entry = {
                "id": q_id, "type": q.get("type"), "title": q.get("title", ""),
                "student_answer": answers.get(q_id),
                "result": (results or {}).get(q_id, "unknown"),
            }
            if q_id in answer_key:
                entry["answer_key"] = answer_key[q_id]
            questions_summary.append(entry)
        auto_graded = [r for r in (results or {}).values() if r in ("correct", "incorrect", "unanswered")]
        auto_correct = sum(1 for r in auto_graded if r == "correct")
        payload = {
            "exam_title": self.config["exam_title"],
            "exam_duration_seconds": self.config["exam_duration_seconds"],
            "submitted_at": datetime.now().isoformat(),
            "time_remaining_seconds": self.remaining_seconds,
            "time_expired": self.time_up,
            "score_auto_graded": f"{auto_correct}/{len(auto_graded)}" if auto_graded else "n/a",
            "questions": questions_summary,
        }
        with Path(self.config["export_file"]).open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=4, ensure_ascii=False)

    def _export_pdf(self, answers: dict, results: dict = None):
        if not PDF_SUPPORT:
            return
        results = results or {}
        subtitle = (f"Submitted: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                    f" &nbsp;|&nbsp; Time remaining: {format_seconds(self.remaining_seconds)}")
        html = _build_pdf_html(self.config['exam_title'], subtitle,
                               list(self.exam_data.get("questions", [])),
                               answers, results)
        _render_pdf(html, self.config["export_pdf_file"])

    def handle_submit(self):
        if self.is_submitted:
            return
        answers = self._collect_answers()
        self.is_submitted = True
        self.countdown_timer.stop()
        results = compute_results(self.questions_data, answers)
        self._last_answers = answers
        self._last_results = results
        self._show_feedback()
        q_map = {q["id"]: q for q in self.exam_data.get("questions", [])}
        for w in self.question_widgets:
            if q_map.get(w.question_id, {}).get("type") in ("mc", "fill_blank"):
                w.setEnabled(False)
        has_mistakes = any(r == "incorrect" for r in results.values())
        if has_mistakes:
            self._review_btn.show()
        if self.config.get("api_key"):
            self._ai_review_btn.show()
        auto_graded = [r for r in results.values() if r in ("correct", "incorrect", "unanswered")]
        auto_correct = sum(1 for r in auto_graded if r == "correct")
        time_spent = self.config["exam_duration_seconds"] - self.remaining_seconds
        serializable_answers = {}
        for qid, ans in answers.items():
            serializable_answers[qid] = ans if isinstance(ans, dict) else {"text": str(ans)}
        add_history_entry(
            title=self.config.get("exam_title", "Exam"),
            correct=auto_correct, total=len(auto_graded),
            time_spent=time_spent, time_available=self.config["exam_duration_seconds"],
            questions=self.questions_data, answers=serializable_answers, results=results,
        )
        QMessageBox.information(
            self, "Submitted",
            "Your answers were submitted. Review the feedback below, then close the window."
        )

    def _request_full_ai_review(self):
        api_key = self.config.get("api_key", "")
        if not api_key:
            QMessageBox.warning(self, "No API key", "Groq API key is required for AI review.")
            return
        q_map = {q["id"]: q for q in self.questions_data}
        answer_key = self._build_answer_key()
        lines = []
        for q_id, result in self._last_results.items():
            q = q_map.get(q_id, {})
            answer = self._last_answers.get(q_id, {})
            ak = answer_key.get(q_id, {})
            line = f"- Question: {q.get('title', '?')}\n  Type: {q.get('type', '?')}\n  Result: {result}\n"
            if isinstance(answer, dict):
                if "selected_letter" in answer:
                    line += f"  Student answered: {answer['selected_letter']} — {answer.get('selected_text', '')}\n"
                elif "text" in answer or "value" in answer:
                    line += f"  Student answered: {answer.get('text', '') or answer.get('value', '')}\n"
                elif "selected_texts" in answer:
                    line += f"  Student answered: {', '.join(answer['selected_texts'])}\n"
            if "correct_answer" in ak:
                line += f"  Correct answer: {ak['correct_answer']}\n"
            elif "suggested_answer" in ak:
                line += f"  Suggested answer: {ak['suggested_answer']}\n"
            elif "correct_answers_texts" in ak:
                line += f"  Correct answers: {', '.join(ak['correct_answers_texts'])}\n"
            lines.append(line)
        auto_graded = [r for r in self._last_results.values() if r in ("correct", "incorrect", "unanswered")]
        correct = sum(1 for r in auto_graded if r == "correct")
        total = len(auto_graded)
        pct = round(correct / total * 100) if total > 0 else 0
        prompt = FULL_REVIEW_PROMPT.format(
            title=self.config.get("exam_title", "Exam"),
            correct=correct, total=total, pct=pct, details="\n".join(lines),
        )
        self._ai_review_btn.setEnabled(False)
        self._ai_review_btn.setText("Generating…")
        self._full_review_worker = FullReviewWorker(api_key, prompt)
        self._full_review_worker.result_ready.connect(self._show_ai_review_dialog)
        self._full_review_worker.error_occurred.connect(self._on_ai_review_error)
        self._full_review_worker.start()

    def _show_ai_review_dialog(self, report: str):
        self._ai_review_btn.setEnabled(True)
        self._ai_review_btn.setText("AI Study Report")
        dlg = QDialog(self.window())
        dlg.setWindowTitle("AI Study Report")
        dlg.resize(650, 500)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        header = QLabel("AI Study Report")
        header.setObjectName("GuideTitle")
        layout.addWidget(header)
        html = report.replace("**", "<b>", 1)
        while "**" in html:
            html = html.replace("**", "</b>", 1)
            if "**" in html:
                html = html.replace("**", "<b>", 1)
        html = html.replace("\n- ", "\n• ").replace("\n", "<br>")
        text = QTextEdit()
        text.setReadOnly(True)
        text.setHtml(f"<div style='font-size:13px; line-height:1.6;'>{html}</div>")
        text.setStyleSheet(
            "QTextEdit { background: #ffffff; border: 1px solid #e0e4ec; "
            "border-radius: 6px; padding: 16px; }"
        )
        layout.addWidget(text, 1)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setObjectName("SecondaryButton")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        dlg.exec_()

    def _on_ai_review_error(self, msg: str):
        self._ai_review_btn.setEnabled(True)
        self._ai_review_btn.setText("AI Study Report")
        QMessageBox.warning(self, "AI Review failed", msg)

    def _show_mistakes_review(self):
        dlg = QDialog(self.window())
        dlg.setWindowTitle("Review Mistakes")
        dlg.resize(700, 550)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)
        header = QLabel("Questions you got wrong")
        header.setObjectName("GuideTitle")
        layout.addWidget(header)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: #f8f9fc; }")
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(12, 12, 12, 12)
        inner_layout.setSpacing(16)
        q_map = {q["id"]: q for q in self.questions_data}
        answer_key = self._build_answer_key()
        mistake_count = 0
        for q_id, result in self._last_results.items():
            if result != "incorrect":
                continue
            mistake_count += 1
            q = q_map.get(q_id, {})
            answer = self._last_answers.get(q_id, {})
            ak = answer_key.get(q_id, {})
            card = QFrame()
            card.setObjectName("SetupCard")
            card_lay = QVBoxLayout(card)
            card_lay.setContentsMargins(16, 12, 16, 12)
            card_lay.setSpacing(8)
            title = QLabel(f"Q{mistake_count}. {q.get('title', '?')}")
            title.setObjectName("QuestionTitle")
            title.setWordWrap(True)
            card_lay.addWidget(title)
            q_type = q.get("type")
            if q_type == "mc" and isinstance(answer, dict):
                your = answer.get("selected_letter", "—")
                your_text = answer.get("selected_text", "")
                your_lbl = QLabel(f"Your answer:  <b>{your}</b> — {your_text}")
                your_lbl.setStyleSheet("color: #b02020; font-size: 13px;")
                your_lbl.setWordWrap(True)
                card_lay.addWidget(your_lbl)
                correct = ak.get("correct_answer", "?")
                correct_idx = ord(correct.upper()) - ord("A")
                options = q.get("options", [])
                correct_text = options[correct_idx] if correct_idx < len(options) else ""
                correct_lbl = QLabel(f"Correct answer:  <b>{correct}</b> — {correct_text}")
                correct_lbl.setStyleSheet("color: #1a7a3a; font-size: 13px;")
                correct_lbl.setWordWrap(True)
                card_lay.addWidget(correct_lbl)
            elif q_type == "fill_blank" and isinstance(answer, dict):
                student_texts = answer.get("selected_texts", [])
                correct_texts = ak.get("correct_answers_texts", [])
                for i, (st, ct) in enumerate(zip(student_texts, correct_texts)):
                    if st != ct:
                        lbl = QLabel(
                            f"Blank {i+1}:  yours = <b style='color:#b02020;'>{st}</b>"
                            f"  ·  correct = <b style='color:#1a7a3a;'>{ct}</b>"
                        )
                        lbl.setStyleSheet("font-size: 13px;")
                        lbl.setWordWrap(True)
                        card_lay.addWidget(lbl)
            inner_layout.addWidget(card)
        scroll.setWidget(inner)
        layout.addWidget(scroll, 1)
        close_btn = QPushButton("Close")
        close_btn.setObjectName("SecondaryButton")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(dlg.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        dlg.exec_()

    def handle_exit(self):
        self.window().close()

    def force_close_app(self):
        try:
            self.countdown_timer.stop()
        except Exception:
            pass
        app = QApplication.instance()
        if app is not None:
            app.closeAllWindows()
            app.quit()
        if self.config.get("force_kill_process_on_exit"):
            os._exit(0)


class MainWindow(QMainWindow):
    def __init__(self, config: dict, exam_data: dict):
        super().__init__()
        self.config = config
        self.setWindowTitle(config.get("exam_title", "WiseMock"))
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.page = AssessmentPage(config=config, exam_data=exam_data)
        scroll.setWidget(self.page)
        self.setCentralWidget(scroll)
        fit_window_to_screen(self, preferred_size=(900, 860), minimum_size=(700, 520))

    def closeEvent(self, event):
        msg = ("Are you sure you want to close the review?" if self.page.is_submitted
               else "Are you sure you want to close the exam?")
        reply = QMessageBox.question(self, "Close", msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            event.accept()
            for w in self.page.question_widgets:
                worker = getattr(w, "_worker", None)
                if worker is not None and worker.isRunning():
                    worker.terminate()
                    worker.wait(500)
            self.page.force_close_app()
        else:
            event.ignore()
