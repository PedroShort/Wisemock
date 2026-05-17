"""Module-level constants, paths, and capability flags."""
from pathlib import Path

# ── Groq API ──────────────────────────────────────────────
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# Model routing waterfall. groq_request() tries these in order, advancing to
# the next model on rate-limit / 413 / transient error instead of failing.
# All models share one endpoint and one API key — only the `model` string
# changes. Free-tier TPM in comments (the constraint that drives ordering).
#
# QUALITY_FIRST: default. Best models first; 8B only as a tolerable last
#   resort (it was the root cause of the correct_answer / fill_blank bugs).
QUALITY_FIRST = [
    "llama-3.3-70b-versatile",                      # 12K TPM, strong
    "meta-llama/llama-4-scout-17b-16e-instruct",    # 30K TPM, modern
    "openai/gpt-oss-120b",                          #  8K TPM, strong reasoning
    # "qwen/qwen3-32b",  # optional: enable before 8B once quality is verified
    "llama-3.1-8b-instant",                         #  6K TPM, last resort
]
# TPM_FIRST: for large inputs — highest TPM model first to avoid 413s.
TPM_FIRST = [
    "meta-llama/llama-4-scout-17b-16e-instruct",    # 30K TPM
    "llama-3.3-70b-versatile",                      # 12K TPM
    "openai/gpt-oss-120b",                          #  8K TPM
    # "qwen/qwen3-32b",
    "llama-3.1-8b-instant",                         #  6K TPM, last resort
]
# QUALITY_NO_LOW: grading (AICheckWorker) — NEVER degrade to the weak 8B.
# A misleading "Score: 18/20" on garbage erodes trust; better to report the
# grader as temporarily unavailable than to show an unreliable number.
QUALITY_NO_LOW = [
    "llama-3.3-70b-versatile",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "openai/gpt-oss-120b",
    # "qwen/qwen3-32b",
]
# Models considered low-quality — triggers meta["low_quality_fallback"].
LOW_QUALITY_MODELS = {"llama-3.1-8b-instant"}

ROUTING_MODES = {
    "quality": QUALITY_FIRST,
    "tpm": TPM_FIRST,
    "quality_no_low": QUALITY_NO_LOW,
}

# Back-compat: any legacy import of AI_MODEL gets the top quality model.
AI_MODEL = QUALITY_FIRST[0]
AI_AVAILABLE = True

# ── File support ──────────────────────────────────────────
SUPPORTED_DOC_EXTENSIONS = (".pdf", ".docx", ".pptx")

# ── Paths ─────────────────────────────────────────────────
PACKAGE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = PACKAGE_DIR / "assets"
HISTORY_DIR = Path.home() / ".wiseflow"
HISTORY_FILE = HISTORY_DIR / "history.json"

# ── Optional dependency capability flags ──────────────────
try:
    from PyQt5.QtWebChannel import QWebChannel  # noqa: F401
    from PyQt5.QtWebEngineWidgets import QWebEngineView  # noqa: F401
    WEB_FRONTEND_AVAILABLE = True
except ImportError:
    WEB_FRONTEND_AVAILABLE = False

try:
    from PyQt5.QtPrintSupport import QPrinter  # noqa: F401
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

try:
    import fitz as pymupdf  # noqa: F401  PyMuPDF
    PDF_EXTRACT = True
except ImportError:
    PDF_EXTRACT = False

try:
    import docx as python_docx  # noqa: F401
    DOCX_EXTRACT = True
except ImportError:
    DOCX_EXTRACT = False

try:
    from pptx import Presentation as PptxPresentation  # noqa: F401
    PPTX_EXTRACT = True
except ImportError:
    PPTX_EXTRACT = False

OCR_INSTALL_HINT = (
    "Install Tesseract to extract scanned/image-only PDF pages reliably: "
    "macOS: brew install tesseract · Linux: apt-get install tesseract-ocr · "
    "Windows: https://github.com/UB-Mannheim/tesseract/wiki"
)

# OCR is best-effort: needs both the Python wrapper AND the Tesseract binary
# installed on the OS. If either is missing we skip OCR and let extraction add
# a document-level warning only when the source actually looks image-based.
try:
    import pytesseract  # noqa: F401
    from PIL import Image  # noqa: F401
    pytesseract.get_tesseract_version()
    OCR_EXTRACT = True
except Exception:
    OCR_EXTRACT = False
