"""Open-ended (essay) question with rich-text toolbar and word-limit cap."""
from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtGui import QColor, QFont, QKeyEvent, QTextCharFormat, QTextListFormat
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget

from wisemock.workers import AICheckWorker


class OpenEndedQuestion(QWidget):
    def __init__(self, question_id: str, title: str, placeholder: str = "Write your answer here...", max_words: int = None):
        super().__init__()
        self.question_id = question_id
        self.text_box = None
        self._question_title = ""
        self._max_words = max_words
        self._at_limit = False
        self._build_ui(title, placeholder)

    def _make_tb_btn(self, text, tooltip, checkable=False):
        btn = QPushButton(text)
        btn.setToolTip(tooltip)
        btn.setFixedSize(28, 28)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setCheckable(checkable)
        btn.setStyleSheet(
            "QPushButton { font-size: 13px; font-weight: bold; color: #555; background: transparent;"
            " border: 1px solid transparent; border-radius: 3px; padding: 0;"
            " text-align: center; qproperty-alignment: AlignCenter; }"
            "QPushButton:hover { background: #e0e0e0; border-color: #ccc; }"
            "QPushButton:checked { background: #d0d0d0; border-color: #bbb; color: #222; }"
        )
        return btn

    def _build_ui(self, title: str, placeholder: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 18)
        layout.setSpacing(6)
        self._question_title = title
        title_label = QLabel(title)
        title_label.setObjectName("QuestionTitle")
        title_label.setWordWrap(True)
        layout.addWidget(title_label)
        # --- Toolbar ---
        toolbar = QFrame()
        toolbar.setStyleSheet(
            "QFrame { background: #f5f5f5; border: 1px solid #ddd;"
            " border-bottom: none; border-radius: 0; padding: 2px 4px; }"
        )
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(4, 2, 4, 2)
        tb_layout.setSpacing(2)
        self._btn_bold = self._make_tb_btn("B", "Bold", True)
        self._btn_bold.setStyleSheet(self._btn_bold.styleSheet().replace("font-size: 13px;", "font-size: 14px;"))
        self._btn_italic = self._make_tb_btn("I", "Italic", True)
        self._btn_italic.setStyleSheet(self._btn_italic.styleSheet().replace("font-weight: bold;", "font-weight: bold; font-style: italic;"))
        self._btn_underline = self._make_tb_btn("U", "Underline", True)
        self._btn_underline.setStyleSheet(self._btn_underline.styleSheet().replace("font-weight: bold;", "font-weight: bold; text-decoration: underline;"))
        self._btn_strike = self._make_tb_btn("S̶", "Strikethrough", True)
        sep1 = QFrame(); sep1.setFixedSize(1, 20); sep1.setStyleSheet("background: #ccc;")
        self._btn_bullets = self._make_tb_btn("•", "Bullet list", True)
        self._btn_numbered = self._make_tb_btn("1.", "Numbered list", True)
        sep2 = QFrame(); sep2.setFixedSize(1, 20); sep2.setStyleSheet("background: #ccc;")
        self._btn_left = self._make_tb_btn("≡", "Align left")
        self._btn_center = self._make_tb_btn("≡", "Align center")
        self._btn_center.setToolTip("Align center")
        self._btn_right = self._make_tb_btn("≡", "Align right")
        self._btn_right.setToolTip("Align right")
        sep3 = QFrame(); sep3.setFixedSize(1, 20); sep3.setStyleSheet("background: #ccc;")
        self._btn_super = self._make_tb_btn("x²", "Superscript", True)
        self._btn_sub = self._make_tb_btn("x₂", "Subscript", True)
        sep4 = QFrame(); sep4.setFixedSize(1, 20); sep4.setStyleSheet("background: #ccc;")
        self._btn_quote = self._make_tb_btn("“", "Blockquote")
        self._btn_hr = self._make_tb_btn("—", "Horizontal line")
        sep5 = QFrame(); sep5.setFixedSize(1, 20); sep5.setStyleSheet("background: #ccc;")
        self._btn_clear = self._make_tb_btn("T̸", "Clear formatting")
        self._btn_undo = self._make_tb_btn("↩", "Undo")
        self._btn_redo = self._make_tb_btn("↪", "Redo")
        for w in [self._btn_bold, self._btn_italic, self._btn_underline, self._btn_strike,
                   sep1, self._btn_bullets, self._btn_numbered,
                   sep2, self._btn_left, self._btn_center, self._btn_right,
                   sep3, self._btn_super, self._btn_sub,
                   sep4, self._btn_quote, self._btn_hr,
                   sep5, self._btn_clear, self._btn_undo, self._btn_redo]:
            tb_layout.addWidget(w)
        tb_layout.addStretch()
        layout.addWidget(toolbar)
        # --- Text editor ---
        self.text_box = QTextEdit()
        self.text_box.setObjectName("OpenEndedBox")
        self.text_box.setPlaceholderText(placeholder)
        self.text_box.setMinimumHeight(140)
        self.text_box.setStyleSheet(
            "QTextEdit#OpenEndedBox { border-top-left-radius: 0; border-top-right-radius: 0; }"
        )
        layout.addWidget(self.text_box)
        # --- Word count ---
        if self._max_words:
            self._word_count_label = QLabel(f"0 / {self._max_words} Word limit")
            self._word_count_label.setAlignment(Qt.AlignRight)
            self._word_count_label.setStyleSheet(
                "font-size: 11px; color: #999; padding: 2px 4px 0 0; background: transparent;"
            )
            layout.addWidget(self._word_count_label)
            self.text_box.textChanged.connect(self._update_word_count)
            self.text_box.installEventFilter(self)
        # --- Connect toolbar buttons ---
        self._btn_bold.clicked.connect(lambda: self._toggle_format("bold"))
        self._btn_italic.clicked.connect(lambda: self._toggle_format("italic"))
        self._btn_underline.clicked.connect(lambda: self._toggle_format("underline"))
        self._btn_strike.clicked.connect(lambda: self._toggle_format("strike"))
        self._btn_bullets.clicked.connect(lambda: self._toggle_list(QTextListFormat.ListDisc))
        self._btn_numbered.clicked.connect(lambda: self._toggle_list(QTextListFormat.ListDecimal))
        self._btn_left.clicked.connect(lambda: self._set_align(Qt.AlignLeft))
        self._btn_center.clicked.connect(lambda: self._set_align(Qt.AlignCenter))
        self._btn_right.clicked.connect(lambda: self._set_align(Qt.AlignRight))
        self._btn_super.clicked.connect(lambda: self._toggle_vertical(QTextCharFormat.AlignSuperScript))
        self._btn_sub.clicked.connect(lambda: self._toggle_vertical(QTextCharFormat.AlignSubScript))
        self._btn_quote.clicked.connect(self._insert_blockquote)
        self._btn_hr.clicked.connect(lambda: self.text_box.textCursor().insertHtml("<hr>"))
        self._btn_clear.clicked.connect(self._clear_formatting)
        self._btn_undo.clicked.connect(self.text_box.undo)
        self._btn_redo.clicked.connect(self.text_box.redo)
        self.text_box.cursorPositionChanged.connect(self._update_toolbar_state)

    def _toggle_format(self, fmt):
        cursor = self.text_box.textCursor()
        char_fmt = cursor.charFormat()
        if fmt == "bold":
            char_fmt.setFontWeight(QFont.Normal if char_fmt.fontWeight() == QFont.Bold else QFont.Bold)
        elif fmt == "italic":
            char_fmt.setFontItalic(not char_fmt.fontItalic())
        elif fmt == "underline":
            char_fmt.setFontUnderline(not char_fmt.fontUnderline())
        elif fmt == "strike":
            char_fmt.setFontStrikeOut(not char_fmt.fontStrikeOut())
        cursor.mergeCharFormat(char_fmt)
        self.text_box.setCurrentCharFormat(char_fmt)

    def _toggle_list(self, style):
        cursor = self.text_box.textCursor()
        current_list = cursor.currentList()
        if current_list and current_list.format().style() == style:
            block_fmt = cursor.blockFormat()
            block_fmt.setIndent(0)
            cursor.setBlockFormat(block_fmt)
            cursor.currentList().remove(cursor.block())
        else:
            list_fmt = QTextListFormat()
            list_fmt.setStyle(style)
            list_fmt.setIndent(1)
            cursor.createList(list_fmt)

    def _set_align(self, alignment):
        cursor = self.text_box.textCursor()
        block_fmt = cursor.blockFormat()
        block_fmt.setAlignment(alignment)
        cursor.mergeBlockFormat(block_fmt)

    def _toggle_vertical(self, alignment):
        cursor = self.text_box.textCursor()
        char_fmt = cursor.charFormat()
        current = char_fmt.verticalAlignment()
        char_fmt.setVerticalAlignment(QTextCharFormat.AlignNormal if current == alignment else alignment)
        cursor.mergeCharFormat(char_fmt)
        self.text_box.setCurrentCharFormat(char_fmt)

    def _insert_blockquote(self):
        cursor = self.text_box.textCursor()
        block_fmt = cursor.blockFormat()
        if block_fmt.leftMargin() > 0:
            block_fmt.setLeftMargin(0)
            block_fmt.setProperty(0x100000, None)
        else:
            block_fmt.setLeftMargin(20)
            block_fmt.setBackground(QColor("#f0f0f0"))
        cursor.mergeBlockFormat(block_fmt)

    def _clear_formatting(self):
        cursor = self.text_box.textCursor()
        cursor.setCharFormat(QTextCharFormat())
        self.text_box.setCurrentCharFormat(QTextCharFormat())

    def _update_toolbar_state(self):
        fmt = self.text_box.currentCharFormat()
        self._btn_bold.setChecked(fmt.fontWeight() == QFont.Bold)
        self._btn_italic.setChecked(fmt.fontItalic())
        self._btn_underline.setChecked(fmt.fontUnderline())
        self._btn_strike.setChecked(fmt.fontStrikeOut())
        self._btn_super.setChecked(fmt.verticalAlignment() == QTextCharFormat.AlignSuperScript)
        self._btn_sub.setChecked(fmt.verticalAlignment() == QTextCharFormat.AlignSubScript)

    def _update_word_count(self):
        plain = self.text_box.toPlainText()
        words = plain.split()
        count = len(words)
        # Hard cap: if the user pasted or typed past the limit, delete the
        # excess from the end of the document while preserving the rich-text
        # formatting (bold/lists/etc.) in the kept portion. The eventFilter is
        # a soft guard; this is the authoritative one.
        if count > self._max_words:
            n_to_keep = self._max_words
            seen = 0
            cut_at = len(plain)
            in_word = False
            for i, ch in enumerate(plain):
                if ch.isspace():
                    in_word = False
                else:
                    if not in_word:
                        seen += 1
                        in_word = True
                        if seen > n_to_keep:
                            cut_at = i
                            break
            self.text_box.blockSignals(True)
            cursor = self.text_box.textCursor()
            cursor.setPosition(cut_at)
            cursor.movePosition(cursor.End, cursor.KeepAnchor)
            cursor.removeSelectedText()
            cursor.movePosition(cursor.End)
            self.text_box.setTextCursor(cursor)
            self.text_box.blockSignals(False)
            count = self._max_words
        self._at_limit = count >= self._max_words
        if self._at_limit:
            self._word_count_label.setStyleSheet(
                "font-size: 11px; color: #c0392b; font-weight: bold; padding: 2px 4px 0 0; background: transparent;"
            )
        else:
            self._word_count_label.setStyleSheet(
                "font-size: 11px; color: #999; padding: 2px 4px 0 0; background: transparent;"
            )
        self._word_count_label.setText(f"{count} / {self._max_words} Word limit")

    def eventFilter(self, obj, event):
        if obj == self.text_box and self._max_words and getattr(self, '_at_limit', False):
            if event.type() == QEvent.KeyPress:
                key = event.key()
                # Allow navigation, delete, backspace, select-all, copy, cut, undo, redo
                allowed = {Qt.Key_Backspace, Qt.Key_Delete, Qt.Key_Left, Qt.Key_Right,
                           Qt.Key_Up, Qt.Key_Down, Qt.Key_Home, Qt.Key_End,
                           Qt.Key_PageUp, Qt.Key_PageDown}
                if key in allowed:
                    return False
                # Allow Ctrl+A, Ctrl+C, Ctrl+X, Ctrl+Z, Ctrl+Y
                if event.modifiers() & Qt.ControlModifier and key in {Qt.Key_A, Qt.Key_C, Qt.Key_X, Qt.Key_Z, Qt.Key_Y}:
                    return False
                # Block all other character input
                if event.text():
                    return True
        return super().eventFilter(obj, event)

    def get_answer(self):
        return self.text_box.toPlainText().strip()

    def get_answer_html(self):
        return self.text_box.toHtml()

    def show_result(self, suggested_answer: str, api_key: str = ""):
        self.text_box.setReadOnly(True)
        header = QLabel("Suggested answer:")
        header.setStyleSheet("font-size: 12px; font-weight: 700; color: #2a9e50; background: transparent;")
        suggested_box = QLabel(suggested_answer)
        suggested_box.setObjectName("SuggestedAnswerBox")
        suggested_box.setWordWrap(True)
        self.layout().addWidget(header)
        self.layout().addWidget(suggested_box)
        if api_key:
            self._ai_btn = QPushButton("✨ Check with AI")
            self._ai_btn.setObjectName("AIButton")
            self._ai_btn.setFixedWidth(170)
            self._ai_btn.setCursor(Qt.PointingHandCursor)
            self._ai_btn.clicked.connect(lambda: self._run_ai_check(suggested_answer, api_key))
            self._ai_feedback = QLabel("")
            self._ai_feedback.setObjectName("AIFeedbackBox")
            self._ai_feedback.setWordWrap(True)
            self._ai_feedback.hide()
            self.layout().addWidget(self._ai_btn)
            self.layout().addWidget(self._ai_feedback)

    def _run_ai_check(self, suggested: str, api_key: str):
        self._ai_btn.setEnabled(False)
        self._ai_btn.setText("Checking…")
        self._worker = AICheckWorker(api_key, self._question_title, suggested,
                                     self.text_box.toPlainText().strip())
        self._worker.result_ready.connect(self._on_ai_result)
        self._worker.error_occurred.connect(self._on_ai_error)
        self._worker.setTerminationEnabled(True)
        self._worker.start()

    def _on_ai_result(self, text: str):
        self._ai_feedback.setText(text)
        self._ai_feedback.show()
        self._ai_btn.hide()

    def _on_ai_error(self, error: str):
        self._ai_feedback.setText(f"AI check failed: {error}")
        self._ai_feedback.show()
        self._ai_btn.setText("✨ Check with AI")
        self._ai_btn.setEnabled(True)
