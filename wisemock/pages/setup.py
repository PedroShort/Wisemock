"""Setup page — picks a file, configures exam options, and starts generation."""
import json
from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QSizePolicy, QSpinBox, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from wisemock.config import ASSETS_DIR
from wisemock.core.input_loading import dedupe_paths, file_list_summary
from wisemock.pages.assessment import MainWindow
from wisemock.pages.performance import PerformanceTab
from wisemock.runtime.geometry import fit_window_to_screen
from wisemock.widgets.drop_zone import DropZone
from wisemock.widgets.helpers import _start_btn_animation, _stop_btn_animation
from wisemock.widgets.toggle import ToggleSwitch
from wisemock.workers import DocumentLoadWorker, ExamGeneratorWorker


class SetupPage(QWidget):
    start_requested = pyqtSignal(dict, dict)

    def __init__(self):
        super().__init__()
        self.setObjectName("SetupRoot")
        self.exam_data = None
        self._questions_path = None
        self._doc_path = None
        self._doc_paths = []
        self._doc_text = ""
        self._load_queue = []
        self._load_worker = None
        self._gen_worker = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("SetupHeader")
        header.setFixedHeight(58)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(28, 0, 28, 0)

        logo_container = QFrame()
        logo_container.setFixedSize(36, 36)
        logo_container.setStyleSheet(
            "background: rgba(255,255,255,0.12); border-radius: 10px;"
            " border: 1px solid rgba(255,255,255,0.15);"
        )
        logo_label = QLabel()
        # Prefer the new mountain icon set (matches the macOS app + intro);
        # fall back to the legacy "logo wisemock.png" if it's the only one available.
        icon_candidates = [
            ASSETS_DIR / "icons" / "icon_64x64.png",
            ASSETS_DIR / "logo wisemock.png",
        ]
        icon_path = next((str(p) for p in icon_candidates if p.exists()), "")
        if icon_path:
            pixmap = QPixmap(icon_path).scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_label.setPixmap(pixmap)
        else:
            logo_label.setText("W")
            logo_label.setStyleSheet("font-size: 16px; font-weight: 700; color: #e8e8e8; background: transparent;")
        logo_label.setAlignment(Qt.AlignCenter)
        logo_label.setStyleSheet(logo_label.styleSheet() + " background: transparent;")
        logo_inner = QVBoxLayout(logo_container)
        logo_inner.setContentsMargins(0, 0, 0, 0)
        logo_inner.addWidget(logo_label)

        app_title = QLabel("WiseMock")
        app_title.setObjectName("AppTitle")
        app_tag = QLabel("by students, for students")
        app_tag.setObjectName("AppTagline")
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_col.addWidget(app_title)
        title_col.addWidget(app_tag)
        h_layout.addWidget(logo_container)
        h_layout.addSpacing(8)
        h_layout.addLayout(title_col)
        h_layout.addStretch()

        help_btn = QPushButton("Help")
        help_btn.setCursor(Qt.PointingHandCursor)
        help_btn.setToolTip("How to use WiseMock")
        help_btn.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.08); color: #cccccc; "
            "border-radius: 7px; font-size: 13px; font-weight: 500; "
            "border: 1px solid rgba(255,255,255,0.15); padding: 7px 16px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.15); color: #ffffff; }"
        )
        help_btn.clicked.connect(self._show_help)
        h_layout.addWidget(help_btn)
        root.addWidget(header)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_setup_tab(), "  Setup  ")
        self.tabs.addTab(PerformanceTab(), "  Performance  ")
        root.addWidget(self.tabs, 1)

    def _build_setup_tab(self) -> QWidget:
        tab = QWidget()
        tab.setObjectName("SetupRoot")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: #dcdcdc; border: none; }")

        wrapper = QWidget()
        wrapper.setStyleSheet("background: #dcdcdc;")
        wrapper_layout = QHBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(20, 32, 20, 64)
        wrapper_layout.setSpacing(0)

        body = QWidget()
        body.setMaximumWidth(820)
        body.setMinimumWidth(500)
        body.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # ── DROP CARD (top rounded corners) ──
        drop_card = QFrame()
        drop_card.setObjectName("DropCard")
        drop_card.setStyleSheet(
            "QFrame#DropCard { background-color: #ffffff;"
            " border-top: 1px solid #e8e8e8;"
            " border-left: 1px solid #e8e8e8;"
            " border-right: 1px solid #e8e8e8;"
            " border-bottom: 0px solid #ffffff;"
            " border-top-left-radius: 14px; border-top-right-radius: 14px; }"
        )
        dc_lay = QVBoxLayout(drop_card)
        dc_lay.setContentsMargins(0, 0, 0, 0)
        dc_lay.setSpacing(0)
        self.drop_zone = DropZone()
        self.drop_zone.file_dropped.connect(self._on_file_dropped)
        self.drop_zone.files_dropped.connect(self._on_files_dropped)
        dc_lay.addWidget(self.drop_zone)
        dc_lay.addWidget(self._divider())
        paste_btn = QPushButton("⎘  Paste JSON text instead")
        paste_btn.setCursor(Qt.PointingHandCursor)
        paste_btn.setStyleSheet(
            "QPushButton { font-size: 13px; font-weight: 500; color: #555555;"
            " background: none; border: none; padding: 13px 28px; text-align: center; }"
            "QPushButton:hover { color: #1a1a1a; }"
        )
        paste_btn.clicked.connect(self._on_paste_json)
        dc_lay.addWidget(paste_btn)

        # Generation options (hidden by default)
        self._gen_options = QFrame()
        self._gen_options.setVisible(False)
        self._gen_options.setStyleSheet("QFrame { background: transparent; border: none; }")
        gen_layout = QVBoxLayout(self._gen_options)
        gen_layout.setContentsMargins(28, 0, 28, 16)
        gen_layout.setSpacing(10)
        gen_layout.addWidget(self._divider())
        gen_layout.addWidget(self._section_label("GENERATION OPTIONS"))
        diff_row = QHBoxLayout()
        diff_row.addWidget(QLabel("Difficulty"))
        self.gen_difficulty = QComboBox()
        self.gen_difficulty.addItems(["Easy", "Medium", "Hard"])
        self.gen_difficulty.setCurrentIndex(1)
        diff_row.addWidget(self.gen_difficulty, 1)
        gen_layout.addLayout(diff_row)
        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("Exam size"))
        self.gen_size = QComboBox()
        self.gen_size.addItems(["Small (~10 Q)", "Medium (~20 Q)", "Large (~30 Q)", "Custom"])
        self.gen_size.setCurrentIndex(1)
        size_row.addWidget(self.gen_size, 1)
        gen_layout.addLayout(size_row)
        custom_size_row = QHBoxLayout()
        custom_size_row.addWidget(QLabel("Custom count"))
        self.gen_custom_count = QSpinBox()
        self.gen_custom_count.setRange(1, 200)
        self.gen_custom_count.setValue(24)
        custom_size_row.addWidget(self.gen_custom_count, 1)
        self._gen_custom_size_row = QWidget()
        self._gen_custom_size_row.setLayout(custom_size_row)
        self._gen_custom_size_row.setVisible(False)
        gen_layout.addWidget(self._gen_custom_size_row)
        self.gen_size.currentIndexChanged.connect(
            lambda index: self._gen_custom_size_row.setVisible(index == 3)
        )
        gen_layout.addWidget(QLabel("Question types:"))
        self.chk_gen_mc = QCheckBox("Multiple choice")
        self.chk_gen_mc.setChecked(True)
        self.chk_gen_open = QCheckBox("Open-ended")
        self.chk_gen_open.setChecked(True)
        self.chk_gen_fill = QCheckBox("Fill in the blank")
        self.chk_gen_fill.setChecked(True)
        gen_layout.addWidget(self.chk_gen_mc)
        gen_layout.addWidget(self.chk_gen_open)
        gen_layout.addWidget(self.chk_gen_fill)
        self._gen_status = QLabel("")
        self._gen_status.setWordWrap(True)
        self._gen_status.setStyleSheet("color: #666; font-size: 12px; background: transparent;")
        gen_layout.addWidget(self._gen_status)
        self.gen_btn = QPushButton("Generate Exam")
        self.gen_btn.setObjectName("StartButton")
        self.gen_btn.setCursor(Qt.PointingHandCursor)
        self.gen_btn.clicked.connect(self._on_generate)
        gen_layout.addWidget(self.gen_btn)
        dc_lay.addWidget(self._gen_options)

        body_layout.addWidget(drop_card)

        # ── SETTINGS CARD (no rounded corners) ──
        settings_card = QFrame()
        settings_card.setObjectName("SettingsCard")
        settings_card.setStyleSheet(
            "QFrame#SettingsCard { background-color: #ffffff; border: 1px solid #e8e8e8; border-top: none; }"
        )
        sc_lay = QVBoxLayout(settings_card)
        sc_lay.setContentsMargins(0, 0, 0, 0)
        sc_lay.setSpacing(0)

        # Section: Exam Info
        sec1_title = QLabel("EXAM INFO")
        sec1_title.setObjectName("SettingGroupLabel")
        sec1_title.setStyleSheet(
            "font-size: 11px; font-weight: 700; letter-spacing: 0.08em;"
            " color: #aaa; padding: 20px 28px 0 28px; background: transparent;"
        )
        sc_lay.addWidget(sec1_title)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(28, 16, 28, 14)
        title_row.setSpacing(16)
        title_lbl = QLabel("Title")
        title_lbl.setFixedWidth(100)
        title_lbl.setStyleSheet("font-size: 15px; font-weight: 500; color: #555; background: transparent;")
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("e.g. Data Structures [6 pts]")
        title_row.addWidget(title_lbl)
        title_row.addWidget(self.title_input, 1)
        sc_lay.addLayout(title_row)

        dur_div = QFrame()
        dur_div.setFixedHeight(1)
        dur_div.setStyleSheet("background: #e8e8e8; margin-left: 28px; margin-right: 28px;")
        sc_lay.addWidget(dur_div)

        dur_row = QHBoxLayout()
        dur_row.setContentsMargins(28, 14, 28, 14)
        dur_row.setSpacing(16)
        dur_lbl = QLabel("Duration")
        dur_lbl.setFixedWidth(100)
        dur_lbl.setStyleSheet("font-size: 15px; font-weight: 500; color: #555; background: transparent;")
        self._hours_val = 1
        self._mins_val = 0
        h_widget, self._hours_label = self._make_stepper("h", 0, 12, 1, self._on_hours_change)
        m_widget, self._mins_label = self._make_stepper("min", 0, 59, 0, self._on_mins_change, pad=2)
        dur_ctrl = QHBoxLayout()
        dur_ctrl.setSpacing(4)
        dur_ctrl.addWidget(h_widget)
        h_unit = QLabel("hour")
        h_unit.setStyleSheet("font-size: 13px; color: #aaa; font-weight: 500; background: transparent;")
        dur_ctrl.addWidget(h_unit)
        dur_ctrl.addSpacing(12)
        dur_ctrl.addWidget(m_widget)
        m_unit = QLabel("min")
        m_unit.setStyleSheet("font-size: 13px; color: #aaa; font-weight: 500; background: transparent;")
        dur_ctrl.addWidget(m_unit)
        dur_ctrl.addStretch()
        dur_row.addWidget(dur_lbl)
        dur_row.addLayout(dur_ctrl, 1)
        sc_lay.addLayout(dur_row)

        sc_lay.addWidget(self._divider())

        # Section: Questions
        sec2_title = QLabel("QUESTIONS")
        sec2_title.setObjectName("SettingGroupLabel")
        sec2_title.setStyleSheet(
            "font-size: 11px; font-weight: 700; letter-spacing: 0.08em;"
            " color: #aaa; padding: 20px 28px 0 28px; background: transparent;"
        )
        sc_lay.addWidget(sec2_title)
        self.chk_shuffle_q = self._make_toggle_row("Shuffle question order", None, False, sc_lay)
        self.chk_shuffle_o = self._make_toggle_row("Shuffle answer options", None, False, sc_lay)

        sc_lay.addWidget(self._divider())

        # Section: Behaviour
        sec3_title = QLabel("BEHAVIOUR")
        sec3_title.setObjectName("SettingGroupLabel")
        sec3_title.setStyleSheet(
            "font-size: 11px; font-weight: 700; letter-spacing: 0.08em;"
            " color: #aaa; padding: 20px 28px 0 28px; background: transparent;"
        )
        sc_lay.addWidget(sec3_title)
        self.chk_fullscreen = self._make_toggle_row(
            "Launch in fullscreen", "Hides distractions during the exam", True, sc_lay)

        sc_lay.addWidget(self._divider())

        # Section: AI Features
        sec4_title = QLabel("AI FEATURES — GROQ")
        sec4_title.setObjectName("SettingGroupLabel")
        sec4_title.setStyleSheet(
            "font-size: 11px; font-weight: 700; letter-spacing: 0.08em;"
            " color: #aaa; padding: 20px 28px 0 28px; background: transparent;"
        )
        sc_lay.addWidget(sec4_title)
        ai_note = QLabel(
            "A free Groq API key powers exam generation from PDF/DOCX/PPTX "
            "study material and reviews open-ended answers after the exam. "
            "Get one at console.groq.com/keys."
        )
        ai_note.setWordWrap(True)
        ai_note.setStyleSheet(
            "font-size: 12px; color: #aaa; padding: 14px 28px 0 28px;"
            " background: transparent;"
        )
        sc_lay.addWidget(ai_note)
        api_row = QHBoxLayout()
        api_row.setContentsMargins(28, 14, 28, 20)
        api_row.setSpacing(16)
        api_lbl = QLabel("API Key")
        api_lbl.setFixedWidth(100)
        api_lbl.setStyleSheet("font-size: 15px; font-weight: 500; color: #555; background: transparent;")
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("gsk_…")
        self.api_key_input.setEchoMode(QLineEdit.Password)
        api_row.addWidget(api_lbl)
        api_row.addWidget(self.api_key_input, 1)
        sc_lay.addLayout(api_row)

        body_layout.addWidget(settings_card)

        # ── BOTTOM CARD (rounded bottom corners) ──
        bottom_card = QFrame()
        bottom_card.setObjectName("BottomCard")
        bottom_card.setStyleSheet(
            "QFrame#BottomCard { background-color: #ffffff; border: 1px solid #e8e8e8; border-top: none;"
            " border-top-left-radius: 0px; border-top-right-radius: 0px;"
            " border-bottom-left-radius: 14px; border-bottom-right-radius: 14px; }"
        )
        bc_lay = QVBoxLayout(bottom_card)
        bc_lay.setContentsMargins(0, 0, 0, 0)
        start_wrap = QHBoxLayout()
        start_wrap.setContentsMargins(24, 24, 24, 24)
        start_wrap.addStretch()
        self.start_btn = QPushButton("Start Exam")
        self.start_btn.setObjectName("StartButton")
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self._on_start)
        start_wrap.addWidget(self.start_btn)
        start_wrap.addStretch()
        bc_lay.addLayout(start_wrap)
        body_layout.addWidget(bottom_card)

        wrapper_layout.addStretch()
        wrapper_layout.addWidget(body, 0, Qt.AlignTop)
        wrapper_layout.addStretch()
        scroll.setWidget(wrapper)
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)
        return tab

    def _make_toggle_row(self, label, sublabel, checked, parent_layout):
        row = QFrame()
        row.setCursor(Qt.PointingHandCursor)
        row.setStyleSheet(
            "QFrame { background: transparent; border: none;"
            " border-top: 1px solid #e8e8e8; }"
        )
        r_lay = QHBoxLayout(row)
        r_lay.setContentsMargins(28, 16, 28, 16)
        r_lay.setSpacing(16)
        toggle = ToggleSwitch(checked=checked)
        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        lbl = QLabel(label)
        lbl.setStyleSheet("font-size: 15px; font-weight: 400; color: #1a1a1a; background: transparent;")
        lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        text_col.addWidget(lbl)
        if sublabel:
            sub = QLabel(sublabel)
            sub.setStyleSheet("font-size: 12px; color: #aaa; background: transparent;")
            sub.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            text_col.addWidget(sub)
        r_lay.addWidget(toggle)
        r_lay.addLayout(text_col, 1)
        def on_row_click(event, t=toggle):
            t.click()
        row.mousePressEvent = on_row_click
        parent_layout.addWidget(row)
        return toggle

    def _show_help(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("How to use WiseMock")
        dlg.resize(560, 480)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(12)
        title = QLabel("How to use WiseMock")
        title.setObjectName("GuideTitle")
        layout.addWidget(title)
        content = QTextEdit()
        content.setReadOnly(True)
        content.setHtml("""
        <div style="font-size:13px; line-height:1.7; color:#333;">

        <h3 style="color:#1a2744;">Getting started</h3>
        <ol>
            <li><b>Drag a file</b> into the drop zone — or click to browse</li>
            <li>Configure your exam settings on the right panel</li>
            <li>Click <b>Start Exam</b> and go!</li>
        </ol>

        <h3 style="color:#1a2744;">Supported file formats</h3>
        <ul>
            <li><b>.json</b> — WiseMock exam JSON files (loaded directly)</li>
            <li><b>.pdf</b> — PDF study material for AI generation</li>
            <li><b>.docx</b> — Word study documents</li>
            <li><b>.pptx</b> — PowerPoint study slides</li>
        </ul>
        <p>For PDF, Word, and PowerPoint files, WiseMock extracts the text and uses
        AI to generate exam questions automatically. You choose the difficulty, size,
        and question types.</p>

        <h3 style="color:#1a2744;">WiseMock JSON structure</h3>
        <p>You can also create your own JSON file and load it directly. Here is a tiny Portuguese survival exam:</p>
        <pre style="white-space:pre-wrap; background:#f7f7f7; border:1px solid #e0e4ec; padding:10px; border-radius:6px;">{
  "title": "Portuguese Survival Exam",
  "questions": [
    {"id":"q1","type":"mc","title":"What is the correct emergency move when someone offers you a pastel de Belem?","options":["Refuse politely","Ask for a salad instead","Eat it before it gets cold","Start a spreadsheet about custard"],"correct_answer":"C"},
    {"id":"q2","type":"fill_blank","title":"Complete the sentence:","template":"The capital of Portugal is {0}.","blanks":[["Porto","Lisbon","Madrid","Pastelaria"]],"correct_answers":[1]},
    {"id":"q3","type":"open","title":"Explain why coffee and a pastel de nata can be a valid study strategy before an exam.","suggested_answer":"A strong answer mentions morale, energy, cultural wisdom, and not covering the keyboard in custard.","max_words":120}
  ],
  "sections": [
    {"name":"Section I","questions":["q1","q2","q3"]}
  ]
}</pre>

        <h3 style="color:#1a2744;">AI features</h3>
        <ul>
            <li><b>Exam generation</b> — Creates questions from your study material</li>
            <li><b>Answer review</b> — Checks open-ended answers after submission</li>
            <li><b>Study report</b> — Generates a personalised study plan based on your results</li>
        </ul>
        <p>To use AI features, enter your free Groq API key in the setup panel.</p>

        <h3 style="color:#1a2744;">After the exam</h3>
        <ul>
            <li><b>Review Mistakes</b> — See only the questions you got wrong</li>
            <li><b>AI Study Report</b> — Get strengths, weaknesses, and study tips</li>
            <li><b>Save as PDF</b> — Export your results with answer key</li>
        </ul>

        <h3 style="color:#1a2744;">Performance</h3>
        <p>Every completed exam is saved automatically. Switch to the
        <b>Performance</b> tab to track your average score, best score,
        and total study time.</p>

        </div>
        """)
        content.setStyleSheet(
            "QTextEdit { background: #ffffff; border: 1px solid #e0e4ec; "
            "border-radius: 6px; padding: 12px; }"
        )
        layout.addWidget(content, 1)
        close_btn = QPushButton("Got it!")
        close_btn.setObjectName("PrimaryButton")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(dlg.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        dlg.exec_()

    def _make_stepper(self, suffix, min_val, max_val, initial, callback, pad=0):
        container = QFrame()
        container.setFixedWidth(110)
        container.setFixedHeight(38)
        container.setStyleSheet(
            "QFrame { background: #f7f7f7; border: 1px solid #d0d0d0; border-radius: 8px; }"
        )
        h = QHBoxLayout(container)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        btn_style = (
            "QPushButton {{ font-size: 18px; font-weight: 300; color: #555;"
            " background: transparent; border: none; padding: 0px;"
            " text-align: center; {extra} }}"
            "QPushButton:hover {{ background: #e8e8e8; color: #1a1a1a; }}"
            "QPushButton:pressed {{ background: #ddd; }}"
        )
        minus = QPushButton("−")
        minus.setFixedSize(36, 38)
        minus.setCursor(Qt.PointingHandCursor)
        minus.setStyleSheet(btn_style.format(extra="border-top-left-radius: 8px; border-bottom-left-radius: 8px;"))
        fmt = (lambda v: f"{v:0{pad}d}") if pad else (lambda v: str(v))
        field = QLineEdit(fmt(initial))
        field.setAlignment(Qt.AlignCenter)
        field.setFixedHeight(36)
        field.setFixedWidth(36)
        field.setStyleSheet(
            "QLineEdit { font-family: 'DM Mono', monospace; font-size: 15px; font-weight: 500; color: #1a1a1a;"
            " background: #fff; border: none; border-left: 1px solid #d0d0d0;"
            " border-right: 1px solid #d0d0d0; border-radius: 0; padding: 0; }"
        )
        plus = QPushButton("+")
        plus.setFixedSize(36, 38)
        plus.setCursor(Qt.PointingHandCursor)
        plus.setStyleSheet(btn_style.format(extra="border-top-right-radius: 8px; border-bottom-right-radius: 8px;"))
        h.addWidget(minus)
        h.addWidget(field)
        h.addWidget(plus)

        def _parse_val():
            txt = field.text().strip().split()[0]
            try:
                return max(min_val, min(max_val, int(txt)))
            except ValueError:
                return min_val

        def on_minus():
            v = max(min_val, _parse_val() - 1)
            field.setText(fmt(v))
            callback(v)

        def on_plus():
            v = min(max_val, _parse_val() + 1)
            field.setText(fmt(v))
            callback(v)

        def on_edited():
            v = _parse_val()
            field.setText(fmt(v))
            callback(v)

        minus.clicked.connect(on_minus)
        plus.clicked.connect(on_plus)
        field.editingFinished.connect(on_edited)
        return container, field

    def _on_hours_change(self, val):
        self._hours_val = val

    def _on_mins_change(self, val):
        self._mins_val = val

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("SettingGroupLabel")
        return lbl

    def _divider(self) -> QFrame:
        line = QFrame()
        line.setObjectName("SectionDivider")
        line.setFrameShape(QFrame.HLine)
        return line

    @staticmethod
    def _dedupe_paths(paths):
        return dedupe_paths(paths)

    @staticmethod
    def _file_list_summary(paths):
        return file_list_summary(paths)

    def _doc_source_name(self):
        if len(self._doc_paths) > 1:
            return f"{len(self._doc_paths)} study files"
        return Path(self._doc_path).stem if self._doc_path else "study material"

    def _doc_display_name(self):
        if len(self._doc_paths) > 1:
            return f"{len(self._doc_paths)} study files"
        return Path(self._doc_path).name if self._doc_path else "study document"

    def _on_file_dropped(self, path: str):
        self._on_files_dropped([path])

    def _on_files_dropped(self, paths):
        paths = self._dedupe_paths(paths)
        if not paths:
            return
        self._load_queue.append(paths)
        if self._load_worker is not None:
            self.drop_zone.set_loading(
                0,
                f"Queued {len(self._load_queue)} load(s). Current import is still running...",
            )
            return
        self._start_next_load()

    def _start_next_load(self):
        if self._load_worker is not None or not self._load_queue:
            return
        paths = self._load_queue.pop(0)
        self.drop_zone.set_loading(0, "Queued import is starting...")
        self._gen_options.setVisible(False)
        self.start_btn.setEnabled(False)
        self.gen_btn.setEnabled(False)
        worker = DocumentLoadWorker(paths)
        self._load_worker = worker
        worker.progress.connect(self._on_document_load_progress)
        worker.finished_ok.connect(self._on_document_load_ok)
        worker.finished_err.connect(self._on_document_load_err)
        worker.finished.connect(lambda: self._on_document_load_finished(worker))
        worker.start()

    def _on_document_load_progress(self, percent, message):
        suffix = f" {len(self._load_queue)} queued." if self._load_queue else ""
        self.drop_zone.set_loading(percent, f"{message}{suffix}")

    def _on_document_load_ok(self, result):
        kind = result.get("kind")
        if kind == "json_exam":
            self._gen_options.setVisible(False)
            self._doc_path = None
            self._doc_paths = []
            self._doc_text = ""
            self._load_exam_data(result["data"], label=result["label"], base_path=result["base_path"])
            return

        self._doc_path = result.get("path")
        self._doc_paths = result.get("paths") or ([self._doc_path] if self._doc_path else [])
        self._doc_text = result.get("text", "")
        status = result.get("status", "")
        file_info = result.get("file") or {}
        self.drop_zone.set_doc_loaded(file_info.get("name") or self._doc_display_name())
        self.start_btn.setEnabled(False)
        self.exam_data = None

        self._gen_options.setVisible(True)
        self._gen_status.setText(status)
        self.gen_btn.setEnabled(True)

    def _on_document_load_err(self, message):
        QMessageBox.warning(self, "Could not load file", message)
        if self._doc_path:
            self.drop_zone.set_doc_loaded(self._doc_display_name())
        else:
            self.drop_zone.reset()
        self.gen_btn.setEnabled(True)

    def _on_document_load_finished(self, worker):
        if self._load_worker is worker:
            self._load_worker = None
        worker.deleteLater()
        if self._load_queue:
            self._start_next_load()

    def _on_generate(self):
        api_key = self.api_key_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, "API Key required",
                                "Enter your free Groq API key on the right panel to generate exams.")
            return
        q_types = []
        if self.chk_gen_mc.isChecked(): q_types.append("mc")
        if self.chk_gen_open.isChecked(): q_types.append("open")
        if self.chk_gen_fill.isChecked(): q_types.append("fill_blank")
        if not q_types:
            QMessageBox.warning(self, "No types", "Select at least one question type.")
            return
        difficulty = self.gen_difficulty.currentText().lower()
        size = {0: "small", 1: "medium", 2: "large", 3: "custom"}.get(
            self.gen_size.currentIndex(), "medium"
        )
        self.gen_btn.setEnabled(False)
        self._gen_status.setText("Starting generation…")
        _start_btn_animation(self, self.gen_btn, "_gen_anim_timer", "_gen_dots", "Generating")
        self._gen_worker = ExamGeneratorWorker(
            api_key=api_key, text=self._doc_text, difficulty=difficulty,
            size=size, q_types=q_types, source_name=self._doc_source_name(),
            custom_question_count=self.gen_custom_count.value(),
        )
        self._gen_worker.progress.connect(self._on_gen_progress)
        self._gen_worker.finished_ok.connect(self._on_gen_ok)
        self._gen_worker.finished_err.connect(self._on_gen_err)
        self._gen_worker.start()

    def _on_gen_progress(self, msg: str):
        self._gen_status.setText(msg)

    def _on_gen_ok(self, exam_data: dict):
        _stop_btn_animation(self, self.gen_btn, "_gen_anim_timer", "Generate Exam")
        self._gen_status.setText(f"Generated {len(exam_data.get('questions', []))} questions successfully!")
        self._load_exam_data(exam_data, label=f"{self._doc_display_name()} (AI)", base_path=self._doc_path)

    def _on_gen_err(self, msg: str):
        _stop_btn_animation(self, self.gen_btn, "_gen_anim_timer", "Generate Exam")
        self._gen_status.setText(f"Error: {msg}")
        QMessageBox.warning(self, "Generation failed", msg)

    def _on_paste_json(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Paste JSON")
        dlg.resize(600, 440)
        layout = QVBoxLayout(dlg)
        layout.setSpacing(10)
        hint = QLabel("Paste your questions JSON below:")
        hint.setStyleSheet("color: #555; font-size: 13px;")
        layout.addWidget(hint)
        editor = QPlainTextEdit()
        editor.setPlaceholderText('{\n  "questions": [ ... ]\n}')
        editor.setStyleSheet(
            "font-family: monospace; font-size: 12px; background: #f8f8f8; border: 1px solid #ccc;"
        )
        layout.addWidget(editor, 1)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        if dlg.exec_() != QDialog.Accepted:
            return
        raw = editor.toPlainText().strip()
        if not raw:
            return
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            QMessageBox.warning(self, "Invalid JSON", str(e))
            return
        self._load_exam_data(data, label="pasted JSON", base_path=None)

    def _load_exam_data(self, data: dict, label: str, base_path):
        questions = data.get("questions", [])
        if not questions:
            QMessageBox.warning(self, "No questions", "The JSON contains no questions.")
            return
        self.exam_data = data
        self._questions_path = base_path
        self._doc_path = None
        self._doc_paths = []
        self._doc_text = ""
        types = [q.get("type", "?") for q in questions]
        if not self.title_input.text():
            self.title_input.setText(data.get("title", ""))
        self.drop_zone.set_loaded(label, len(questions), types)
        self.start_btn.setEnabled(True)

    def _on_start(self):
        if self.exam_data is None:
            return
        total_seconds = self._hours_val * 3600 + self._mins_val * 60
        if total_seconds == 0:
            total_seconds = 60
        if self._questions_path:
            base = Path(self._questions_path).parent
        else:
            desktop = Path.home() / "Desktop"
            base = desktop if desktop.exists() else Path.home()
        config = {
            "exam_title": self.title_input.text().strip() or "Exam",
            "exam_duration_seconds": total_seconds,
            "launch_fullscreen": self.chk_fullscreen.isChecked(),
            "force_kill_process_on_exit": True,
            "shuffle_questions": self.chk_shuffle_q.isChecked(),
            "shuffle_options": self.chk_shuffle_o.isChecked(),
            "api_key": self.api_key_input.text().strip(),
        }
        self.start_requested.emit(config, self.exam_data)


class SetupWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WiseMock")
        self.exam_window = None
        self.page = SetupPage()
        self.page.start_requested.connect(self._launch_exam)
        self.setCentralWidget(self.page)
        fit_window_to_screen(self, preferred_size=(880, 660), minimum_size=(700, 520))

    def _launch_exam(self, config: dict, exam_data: dict):
        self.hide()
        self.exam_window = MainWindow(config=config, exam_data=exam_data)
        if config.get("launch_fullscreen"):
            self.exam_window.showFullScreen()
        else:
            self.exam_window.show()
