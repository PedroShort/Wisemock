# ──────────────────────────────────────────────────────────
#  INSTALLATION
# ──────────────────────────────────────────────────────────
# Before running this app, install the required dependencies:
#
# Required:
#   pip install PyQt5 PyQtWebEngine
#
# Optional (for document support):
#   pip install pymupdf        # PDF support
#   pip install python-docx    # Word document support
#   pip install python-pptx    # PowerPoint support (may already be installed)
#   pip install pytesseract Pillow  # OCR support; also requires Tesseract binary
#
# API:
#   - Get a free Groq API key at https://console.groq.com/keys
#     (used for AI exam generation and answer review)
# ──────────────────────────────────────────────────────────

import sys
import os
import json
import re
import random
import time
import copy
import html
from datetime import datetime
from pathlib import Path

# QtWebEngine can crash on some macOS + Conda GPU stacks.
# Default to software rendering so the HTML frontend remains usable.
os.environ.setdefault("QT_OPENGL", "software")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
_chromium_flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip()
for _flag in (
    "--disable-gpu",
    "--disable-gpu-compositing",
    "--autoplay-policy=no-user-gesture-required",
):
    if _flag not in _chromium_flags:
        _chromium_flags = f"{_chromium_flags} {_flag}".strip()
if sys.platform.startswith("win"):
    # Some Windows QtWebEngine builds apply the OS DPI scale inside Chromium,
    # making the HTML UI look zoomed-in even when the QMainWindow fits.
    _flag = "--force-device-scale-factor=1"
    if _flag not in _chromium_flags:
        _chromium_flags = f"{_chromium_flags} {_flag}".strip()
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = _chromium_flags
del _chromium_flags, _flag

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread, QPropertyAnimation, QEasingCurve, QRectF, QSize, pyqtProperty, QObject, pyqtSlot, QUrl
from PyQt5.QtGui import QFont, QPixmap, QTextDocument, QTextCharFormat, QTextListFormat, QColor, QPainter
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QPushButton,
    QTextEdit,
    QScrollArea,
    QSizePolicy,
    QMainWindow,
    QMessageBox,
    QFileDialog,
    QSpinBox,
    QCheckBox,
    QLineEdit,
    QComboBox,
    QTabWidget,
    QDialog,
    QDialogButtonBox,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QProgressBar,
    QAbstractButton,
)

# Web/PDF Qt classes — pulled in conditionally; capability flags live in wisemock.config
try:
    from PyQt5.QtWebChannel import QWebChannel
    from PyQt5.QtWebEngineWidgets import QWebEngineView
except ImportError:
    pass

try:
    from PyQt5.QtPrintSupport import QPrinter
except ImportError:
    pass

# Networking for Groq API calls (used by groq_request below)
import urllib.request
import urllib.error

# Optional document-extraction libs: keep names available so legacy code still
# works; the boolean flags themselves come from wisemock.config.
try:
    import fitz as pymupdf  # PyMuPDF
except ImportError:
    pymupdf = None

try:
    import docx as python_docx  # python-docx
except ImportError:
    python_docx = None

try:
    from pptx import Presentation as PptxPresentation  # python-pptx
except ImportError:
    PptxPresentation = None

try:
    import io as _ocr_io
    import pytesseract
    from PIL import Image as _OcrImage
except Exception:
    _ocr_io = None
    pytesseract = None
    _OcrImage = None

from wisemock.config import (
    GROQ_API_URL, AI_MODEL, AI_AVAILABLE,
    SUPPORTED_DOC_EXTENSIONS,
    HISTORY_DIR, HISTORY_FILE, ASSETS_DIR,
    WEB_FRONTEND_AVAILABLE, PDF_SUPPORT,
    PDF_EXTRACT, DOCX_EXTRACT, PPTX_EXTRACT, OCR_EXTRACT,
)
from wisemock.style import STYLE
from wisemock.prompts import GENERATE_EXAM_PROMPT, FULL_REVIEW_PROMPT
from wisemock.core.extract import extract_text_from_file, _table_to_markdown, _ocr_page_images
from wisemock.core.chunking import chunk_text, _strip_markdown_fences
from wisemock.core.grading import compute_results
from wisemock.core.exam_io import load_questions_from_json, _exam_file_payload
from wisemock.core.history import load_history, save_history, add_history_entry, format_seconds
from wisemock.api.groq import groq_request, _parse_retry_after, _handle_worker_error
from wisemock.workers import AICheckWorker, ExamGeneratorWorker, FullReviewWorker
from wisemock.export.pdf import _build_pdf_html, _render_pdf
from wisemock.export.exam_file import export_exam_file_dialog
from wisemock.widgets.helpers import _restyle_widget, _start_btn_animation, _stop_btn_animation
from wisemock.widgets.toggle import ToggleSwitch
from wisemock.widgets.option import ClickableOption
from wisemock.widgets.multiple_choice import MultipleChoiceQuestion
from wisemock.widgets.open_ended import OpenEndedQuestion
from wisemock.widgets.fill_blank import FillBlankQuestion
from wisemock.widgets.drop_zone import DropZone
from wisemock.pages.performance import PerformanceTab
from wisemock.pages.assessment import AssessmentPage, MainWindow
from wisemock.pages.setup import SetupPage, SetupWindow
from wisemock.runtime.payloads import (
    _json_dumps, _clean_option_text, _count_question_types, _questions_summary_text,
    _history_total_time_label, _format_history_date, _compute_score_summary,
    _build_answer_key_from_questions, _serialize_answers_for_history,
    _history_payload, _review_payload, _question_payload, _section_summary,
    _exam_payload_from_session, _build_full_review_prompt, _report_to_html,
)
from wisemock.runtime.prepare import (
    _prepare_mc_question, _resolve_section_questions, _prepare_runtime_exam,
    _normalized_answers_from_frontend, _export_submission_json,
)
from wisemock.runtime.web_view import FrontendWebView
from wisemock.runtime.bridge import FrontendBridge
from wisemock.runtime.windows import WebFrontendWindow, FRONTEND_HTML


# ──────────────────────────────────────────────────────────
#  ENTRY POINT
# ──────────────────────────────────────────────────────────
# The app now lives under the `wisemock/` package. This file is kept as a
# convenience launcher (the WiseMock.app bundle still calls `python wiseflow.py`)
# and as a backward-compat facade — imports above re-export the package's
# public symbols so any code that says `import wiseflow; wiseflow.X` still works.
#
# New code should import from `wisemock.*` directly, e.g.:
#     from wisemock import main
#     from wisemock.runtime.windows import WebFrontendWindow
#     python -m wisemock        # CLI entry

from wisemock.app import main

if __name__ == "__main__":
    main()
