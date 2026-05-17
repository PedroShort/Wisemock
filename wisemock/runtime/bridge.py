"""QObject bridge exposed to the JS frontend via QWebChannel.

Every `@pyqtSlot` is invokable from JavaScript through `window.bridge.<method>(...)`.
Each `pyqtSignal` is a one-way push of a JSON-encoded payload to JS.
"""
import copy
import json
from datetime import datetime
from functools import partial
from pathlib import Path

from PyQt5.QtCore import QObject, QTimer, QUrl, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QFileDialog

from wisemock.config import PACKAGE_DIR, PDF_SUPPORT
from wisemock.core.input_loading import dedupe_paths, file_list_summary
from wisemock.core.grading import compute_results
from wisemock.core.history import add_history_entry, format_seconds, load_history, save_history
from wisemock.export.exam_file import export_exam_file_dialog
from wisemock.export.pdf import _build_pdf_html, _render_pdf
from wisemock.runtime.payloads import (
    _build_full_review_prompt,
    _compute_score_summary,
    _exam_payload_from_session,
    _history_payload,
    _json_dumps,
    _questions_summary_text,
    _report_to_html,
    _review_payload,
    _serialize_answers_for_history,
)
from wisemock.runtime.prepare import (
    _export_submission_json,
    _normalized_answers_from_frontend,
    _prepare_runtime_exam,
)
from wisemock.workers import (
    AICheckWorker,
    DocumentLoadWorker,
    ExamGeneratorWorker,
    FullReviewWorker,
)


class FrontendBridge(QObject):
    initialStateReady = pyqtSignal(str)
    setupFileLoaded = pyqtSignal(str)
    generationStateChanged = pyqtSignal(str)
    examStarted = pyqtSignal(str)
    timerUpdated = pyqtSignal(str)
    examLocked = pyqtSignal(str)
    submissionCompleted = pyqtSignal(str)
    examPayloadUpdated = pyqtSignal(str)
    mistakesReviewReady = pyqtSignal(str)
    aiStudyReportReady = pyqtSignal(str)
    openAnswerReviewReady = pyqtSignal(str)
    historyReady = pyqtSignal(str)
    historyReviewReady = pyqtSignal(str)
    errorRaised = pyqtSignal(str)

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.exam_data = None
        self._questions_path = None
        self._doc_path = None
        self._doc_paths = []
        self._doc_text = ""
        self._current_file = None
        self._show_generate = False
        self._doc_status = ""
        self._generator_status = ""
        self._generation_busy = False
        self._loading_document = False
        self._loading_percent = 0
        self._loading_message = ""
        self._load_queue = []
        self._load_worker = None
        self._active_load_previous_file = None
        self._gen_worker = None
        self._full_review_worker = None
        self._open_review_workers = {}  # question_id -> AICheckWorker
        self._exam_session = None
        self._fullscreen_during_exam = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_timer_tick)
        # Latest API key the user typed in the setup screen. Pushed by the
        # frontend on every "input" event so the bridge always has the latest
        # value for any operation that needs it.
        self._current_api_key = ""

    def _default_setup_state(self):
        return {
            "exam_title": "",
            "duration_hours": 1,
            "duration_minutes": 0,
            "shuffle_questions": False,
            "shuffle_options": False,
            "launch_fullscreen": True,
            "api_key": "",
        }

    def _emit_error(self, message, kind="error"):
        self.errorRaised.emit(_json_dumps({"message": message, "kind": kind}))

    def _cleanup_worker_attr(self, attr_name, worker):
        if getattr(self, attr_name, None) is worker:
            setattr(self, attr_name, None)
        worker.deleteLater()

    def _cleanup_open_review_worker(self, question_id, worker):
        if self._open_review_workers.get(question_id) is worker:
            self._open_review_workers.pop(question_id, None)
        worker.deleteLater()

    def _options_from_json(self, options_json):
        if isinstance(options_json, dict):
            return options_json
        try:
            return json.loads(str(options_json or "{}"))
        except (TypeError, json.JSONDecodeError):
            return {}

    def _setup_payload(self):
        return {
            "file": self._current_file,
            "title": self.exam_data.get("title", "") if self.exam_data else "",
            "can_start": self.exam_data is not None,
            "show_generate": self._show_generate,
            "doc_status": self._doc_status,
            "generator_status": self._generator_status,
            "generation_busy": self._generation_busy,
            "loading_document": self._loading_document,
            "loading_percent": self._loading_percent,
            "loading_message": self._loading_message,
            "queued_loads": len(self._load_queue),
        }

    def _emit_setup(self, changed=False):
        signal = self.generationStateChanged if changed else self.setupFileLoaded
        signal.emit(_json_dumps(self._setup_payload()))

    def _clear_doc_state(self):
        self._doc_path = None
        self._doc_paths = []
        self._doc_text = ""
        self._show_generate = False
        self._doc_status = ""
        self._generator_status = ""
        self._generation_busy = False

    def _load_exam_data(self, data, label, base_path):
        questions = data.get("questions", [])
        if not questions:
            self._emit_error("The JSON contains no questions.")
            return
        self.exam_data = data
        self._questions_path = base_path
        self._clear_doc_state()
        self._current_file = {
            "name": label,
            "subtext": _questions_summary_text(questions),
        }
        self._emit_setup()

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

    def _load_paths(self, paths):
        paths = self._dedupe_paths(paths)
        if not paths:
            self._emit_error("No files were provided.")
            return
        self._load_queue.append(paths)
        if self._loading_document or self._load_worker is not None:
            self._loading_message = f"Queued {len(self._load_queue)} load(s). Current import is still running..."
            self._emit_setup(changed=True)
            return
        self._start_next_load()

    def _start_next_load(self):
        if self._load_worker is not None or not self._load_queue:
            return
        paths = self._load_queue.pop(0)
        self._loading_document = True
        self._loading_percent = 0
        self._loading_message = "Queued import is starting..."
        self._active_load_previous_file = self._current_file
        self._current_file = {
            "name": "Loading document...",
            "subtext": self._loading_message,
        }
        self._show_generate = False
        self._generator_status = ""
        self._emit_setup(changed=True)
        worker = DocumentLoadWorker(paths)
        self._load_worker = worker
        worker.progress.connect(self._on_document_load_progress)
        worker.finished_ok.connect(self._on_document_load_ok)
        worker.finished_err.connect(self._on_document_load_err)
        worker.finished.connect(partial(self._on_document_load_finished, worker))
        worker.start()

    def _on_document_load_progress(self, percent, message):
        self._loading_document = True
        self._loading_percent = percent
        suffix = f" {len(self._load_queue)} queued." if self._load_queue else ""
        self._loading_message = f"{message}{suffix}"
        self._current_file = {
            "name": f"Loading document... {percent}%",
            "subtext": self._loading_message,
        }
        self._emit_setup(changed=True)

    def _on_document_load_ok(self, result):
        self._loading_document = False
        self._loading_percent = 100
        self._loading_message = result.get("status", "Loaded.")
        self._active_load_previous_file = None
        kind = result.get("kind")
        if kind == "json_exam":
            self._load_exam_data(result["data"], result["label"], result["base_path"])
            return
        self.exam_data = None
        self._questions_path = None
        self._doc_path = result.get("path")
        self._doc_paths = result.get("paths") or ([self._doc_path] if self._doc_path else [])
        self._doc_text = result.get("text", "")
        self._doc_status = result.get("status", "")
        self._current_file = result.get("file")
        self._show_generate = True
        self._generator_status = self._doc_status
        self._emit_setup()

    def _on_document_load_err(self, message):
        self._loading_document = False
        self._loading_percent = 0
        self._loading_message = ""
        self._current_file = self._active_load_previous_file
        self._active_load_previous_file = None
        self._emit_setup(changed=True)
        self._emit_error(f"Could not load file: {message}")

    def _on_document_load_finished(self, worker):
        if self._load_worker is worker:
            self._load_worker = None
        worker.deleteLater()
        if self._load_queue:
            QTimer.singleShot(0, self._start_next_load)

    def _record_by_history_id(self, history_id):
        records = load_history()
        try:
            index = int(history_id)
        except (TypeError, ValueError):
            return None, None
        if 0 <= index < len(records):
            return index, records[index]
        return None, None

    @pyqtSlot()
    def requestInitialState(self):
        payload = {
            "setup": {
                "defaults": self._default_setup_state(),
                "file": self._setup_payload() if self._current_file else None,
            },
            "history": _history_payload(),
        }
        self.initialStateReady.emit(_json_dumps(payload))

    @pyqtSlot()
    def openHelp(self):
        return

    @pyqtSlot()
    def pickInputFile(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self.window,
            "Select study file(s) or WiseMock JSON",
            "",
            "Supported files (*.json *.pdf *.docx *.pptx);;JSON files (*.json);;All files (*)",
        )
        if paths:
            self._load_paths(paths)

    @pyqtSlot(str)
    def handleDroppedFile(self, path):
        self._load_paths([path])

    @pyqtSlot(list)
    def handleDroppedFiles(self, paths):
        self._load_paths(paths)

    @pyqtSlot(str)
    def setCurrentApiKey(self, api_key):
        """Frontend pushes the current API key on every keystroke so the
        bridge can use it for operations that don't go through generateExam
        (e.g. multi-file drops, where the Qt drop event has no payload)."""
        self._current_api_key = (api_key or "").strip()

    @pyqtSlot()
    def loadSampleExam(self):
        sample_path = PACKAGE_DIR.parent / "examples" / "sample_exam.json"
        if not sample_path.exists():
            self._emit_error(
                "Sample exam not found. Expected examples/sample_exam.json next to the app."
            )
            return
        self._load_paths([str(sample_path)])

    @pyqtSlot(str)
    def openExternalUrl(self, url):
        """Open a URL in the user's default system browser. Used to make
        documentation / sign-up links (e.g. Groq's console) clickable from
        within the embedded QWebEngineView without navigating away from
        the app UI itself.
        """
        cleaned = (url or "").strip()
        # Only allow http(s) — defensive against any injected javascript:/file: URLs.
        if not (cleaned.startswith("http://") or cleaned.startswith("https://")):
            return
        QDesktopServices.openUrl(QUrl(cleaned))

    @pyqtSlot()
    @pyqtSlot(str)
    def generateExam(self, options_json="{}"):
        if self._generation_busy:
            self._emit_error("Exam generation is already running.")
            return
        if not self._doc_text or not self._doc_path:
            self._emit_error("Load a study document first.")
            return
        options = self._options_from_json(options_json)
        if not options:
            self._emit_error("Invalid generation settings.")
            return
        api_key = (options.get("api_key") or self.window.current_api_key() or "").strip()
        if not api_key:
            self._emit_error("Enter your Groq API key before generating an exam.")
            return
        q_types = options.get("q_types") or []
        if not q_types:
            self._emit_error("Select at least one question type.")
            return
        self._generation_busy = True
        self._generator_status = "Starting generation..."
        self._emit_setup(changed=True)
        self._gen_worker = ExamGeneratorWorker(
            api_key=api_key,
            text=self._doc_text,
            difficulty=options.get("difficulty", "medium"),
            size=options.get("size", "medium"),
            q_types=q_types,
            source_name=self._doc_source_name(),
            custom_question_count=options.get("custom_question_count"),
        )
        self._gen_worker.progress.connect(self._on_generation_progress)
        self._gen_worker.finished_ok.connect(self._on_generation_ok)
        self._gen_worker.finished_err.connect(self._on_generation_err)
        self._gen_worker.finished.connect(
            partial(self._cleanup_worker_attr, "_gen_worker", self._gen_worker)
        )
        self._gen_worker.start()

    def _on_generation_progress(self, message):
        self._generator_status = message
        self._emit_setup(changed=True)

    def _on_generation_ok(self, exam_data):
        self._generation_busy = False
        self._generator_status = f"Generated {len(exam_data.get('questions', []))} questions successfully."
        self._load_exam_data(exam_data, f"{self._doc_display_name()} (AI)", self._doc_path)

    def _on_generation_err(self, message):
        self._generation_busy = False
        self._generator_status = f"Error: {message}"
        self._emit_setup(changed=True)
        self._emit_error(message)

    @pyqtSlot(str)
    def startExam(self, setup_state_json):
        if self.exam_data is None:
            self._emit_error("Load an exam before starting.")
            return
        try:
            setup_state = json.loads(setup_state_json)
        except json.JSONDecodeError:
            self._emit_error("Invalid setup state.")
            return
        total_seconds = int(setup_state.get("duration_hours", 0)) * 3600 + int(setup_state.get("duration_minutes", 0)) * 60
        if total_seconds <= 0:
            total_seconds = 60
        if self._questions_path:
            base = Path(self._questions_path).parent
        else:
            desktop = Path.home() / "Desktop"
            base = desktop if desktop.exists() else Path.home()
        config = {
            "exam_title": setup_state.get("exam_title") or self.exam_data.get("title", "Exam") or "Exam",
            "student_name": setup_state.get("student_name", ""),
            "exam_duration_seconds": total_seconds,
            "export_answers_on_submit": bool(setup_state.get("export_answers_on_submit", True)),
            "export_file": str(base / "submitted_answers.json"),
            "export_pdf_on_submit": bool(setup_state.get("export_pdf_on_submit", PDF_SUPPORT)) and PDF_SUPPORT,
            "export_pdf_file": str(base / "submitted_answers.pdf"),
            "launch_fullscreen": bool(setup_state.get("launch_fullscreen", True)),
            "shuffle_questions": bool(setup_state.get("shuffle_questions", False)),
            "shuffle_options": bool(setup_state.get("shuffle_options", False)),
            "api_key": setup_state.get("api_key", "").strip(),
        }
        runtime_questions, runtime_sections = _prepare_runtime_exam(config, self.exam_data)
        self._exam_session = {
            "config": config,
            "intro_blocks": [
                block for block in copy.deepcopy(self.exam_data.get("intro", []))
                if isinstance(block, dict) and (block.get("content") or "").strip()
            ],
            "questions": runtime_questions,
            "sections": runtime_sections,
            "remaining_seconds": total_seconds,
            "is_paused": False,
            "time_up": False,
            "is_submitted": False,
            "answers": {},
            "results": {},
        }
        self._fullscreen_during_exam = bool(config.get("launch_fullscreen"))
        if self._fullscreen_during_exam:
            self.window.showFullScreen()
        self._timer.start(1000)
        self.examStarted.emit(_json_dumps(_exam_payload_from_session(self._exam_session)))
        # Backstop for the "half setup / half exam" stale-paint glitch under
        # software rendering: after the JS swaps screens and renders the exam
        # (a couple of animation frames), force the web view to repaint its
        # whole surface so no old setup pixels survive on any machine/size.
        self._force_view_repaint()

    def _force_view_repaint(self):
        view = getattr(self.window, "view", None)
        if view is None:
            return

        def _nudge():
            try:
                view.update()
                view.repaint()
            except Exception:
                pass

        # Two nudges: one right after the screen swap, one after the exam
        # questions have rendered (JS double-rAF + DOM build).
        QTimer.singleShot(0, _nudge)
        QTimer.singleShot(200, _nudge)

    @pyqtSlot()
    def togglePause(self):
        if not self._exam_session or self._exam_session.get("is_submitted") or self._exam_session.get("time_up"):
            return
        self._exam_session["is_paused"] = not self._exam_session.get("is_paused", False)
        self.timerUpdated.emit(_json_dumps({
            "remaining_seconds": self._exam_session["remaining_seconds"],
            "remaining_display": format_seconds(self._exam_session["remaining_seconds"]),
            "is_paused": self._exam_session["is_paused"],
        }))

    def _on_timer_tick(self):
        if not self._exam_session or self._exam_session.get("is_submitted") or self._exam_session.get("is_paused"):
            return
        self._exam_session["remaining_seconds"] -= 1
        if self._exam_session["remaining_seconds"] <= 0:
            self._exam_session["remaining_seconds"] = 0
            self._exam_session["time_up"] = True
            self._timer.stop()
            self.timerUpdated.emit(_json_dumps({
                "remaining_seconds": 0,
                "remaining_display": "00:00:00",
                "is_paused": False,
            }))
            self.examLocked.emit(_json_dumps({
                "message": "Time is over. The exam is locked. You can only click Submit.",
                "auto_submit_requested": True,
            }))
            return
        self.timerUpdated.emit(_json_dumps({
            "remaining_seconds": self._exam_session["remaining_seconds"],
            "remaining_display": format_seconds(self._exam_session["remaining_seconds"]),
            "is_paused": False,
        }))

    @pyqtSlot()
    def requestExitExam(self):
        return

    @pyqtSlot()
    def confirmExitExam(self):
        self._timer.stop()
        self._exam_session = None
        if self._fullscreen_during_exam:
            self.window.showNormal()
            self._fullscreen_during_exam = False

    @pyqtSlot(str)
    def submitExam(self, answer_payload_json):
        if not self._exam_session or self._exam_session.get("is_submitted"):
            return
        try:
            raw_answers = json.loads(answer_payload_json)
        except json.JSONDecodeError:
            self._emit_error("Invalid answer payload.")
            return
        self._timer.stop()
        answers = _normalized_answers_from_frontend(
            raw_answers,
            self._exam_session["questions"],
        )
        results = compute_results(self._exam_session["questions"], answers)
        self._exam_session["answers"] = _serialize_answers_for_history(answers)
        self._exam_session["results"] = results
        self._exam_session["is_submitted"] = True
        score = _compute_score_summary(results)
        time_spent = self._exam_session["config"]["exam_duration_seconds"] - self._exam_session["remaining_seconds"]
        if self._exam_session["config"].get("export_answers_on_submit"):
            _export_submission_json(
                self._exam_session["config"],
                self._exam_session["questions"],
                self._exam_session["answers"],
                results,
                self._exam_session["remaining_seconds"],
                self._exam_session["time_up"],
            )
        if self._exam_session["config"].get("export_pdf_on_submit") and PDF_SUPPORT:
            html_doc = _build_pdf_html(
                self._exam_session["config"].get("exam_title", "Exam"),
                f"Submitted: {datetime.now().strftime('%Y-%m-%d %H:%M')} &nbsp;|&nbsp; Time remaining: {format_seconds(self._exam_session['remaining_seconds'])}",
                self._exam_session["questions"],
                self._exam_session["answers"],
                results,
            )
            _render_pdf(html_doc, self._exam_session["config"]["export_pdf_file"])
        # Lightweight section structure for history: name + question_ids.
        # Used by the review modal to render section groupings on replay.
        sections_for_history = [
            {
                "name": section.get("name", ""),
                "question_ids": [q.get("id", "") for q in section.get("questions", [])],
            }
            for section in self._exam_session.get("sections", [])
        ]
        history_id = add_history_entry(
            title=self._exam_session["config"].get("exam_title", "Exam"),
            correct=score["correct"],
            total=score["total"],
            time_spent=time_spent,
            time_available=self._exam_session["config"]["exam_duration_seconds"],
            questions=self._exam_session["questions"],
            answers=self._exam_session["answers"],
            results=results,
            sections=sections_for_history,
        )
        self.submissionCompleted.emit(_json_dumps({
            "exam": _exam_payload_from_session(self._exam_session),
            "score": score,
            "history_id": history_id,
        }))
        self.historyReady.emit(_json_dumps(_history_payload()))

    @pyqtSlot(str)
    def setApiKeyAfterExam(self, api_key):
        """Allow the student to provide a Groq API key AFTER submitting the
        exam. Lets them unlock AI Study Report and per-question AI checks
        when they forgot to enter the key during setup.
        """
        if not self._exam_session:
            self._emit_error("No exam session in progress.")
            return
        if not self._exam_session.get("is_submitted"):
            self._emit_error("Submit the exam before activating an API key.")
            return
        cleaned = (api_key or "").strip()
        if not cleaned:
            self._emit_error("Please paste a valid Groq API key.")
            return
        self._exam_session["config"]["api_key"] = cleaned
        # Push a fresh exam payload so the frontend picks up has_api_key=true
        # and can_ai_report=true (AI buttons / "Check with AI" will show).
        # Use a dedicated signal so this doesn't replay the "Exam submitted
        # successfully" toast that fires on submissionCompleted.
        self.examPayloadUpdated.emit(_json_dumps({
            "exam": _exam_payload_from_session(self._exam_session),
            "score": _compute_score_summary(self._exam_session.get("results", {})),
        }))

    @pyqtSlot()
    def requestReviewMistakes(self):
        if not self._exam_session or not self._exam_session.get("results"):
            self._emit_error("Submit the exam before reviewing mistakes.")
            return
        sections = [
            {
                "name": section.get("name", ""),
                "question_ids": [q.get("id", "") for q in section.get("questions", [])],
            }
            for section in self._exam_session.get("sections", [])
        ]
        payload = _review_payload(
            self._exam_session["config"].get("exam_title", "Exam"),
            self._exam_session["questions"],
            self._exam_session["answers"],
            self._exam_session["results"],
            only_incorrect=True,
            sections=sections,
        )
        self.mistakesReviewReady.emit(_json_dumps(payload))

    @pyqtSlot()
    def requestAIStudyReport(self):
        if not self._exam_session or not self._exam_session.get("results"):
            self._emit_error("Submit the exam before requesting an AI study report.")
            return
        api_key = self._exam_session["config"].get("api_key", "")
        if not api_key:
            self._emit_error("Groq API key is required for AI review.")
            return
        prompt = _build_full_review_prompt(
            self._exam_session["config"].get("exam_title", "Exam"),
            self._exam_session["questions"],
            self._exam_session["answers"],
            self._exam_session["results"],
        )
        self._full_review_worker = FullReviewWorker(api_key, prompt)
        self._full_review_worker.result_ready.connect(self._on_ai_report_ok)
        self._full_review_worker.error_occurred.connect(self._on_ai_report_err)
        self._full_review_worker.finished.connect(
            partial(self._cleanup_worker_attr, "_full_review_worker", self._full_review_worker)
        )
        self._full_review_worker.start()

    def _on_ai_report_ok(self, report):
        self.aiStudyReportReady.emit(_json_dumps({"html": _report_to_html(report)}))

    def _on_ai_report_err(self, message):
        self._emit_error(message)

    @pyqtSlot(str)
    def requestOpenAnswerReview(self, question_id):
        if not self._exam_session or not self._exam_session.get("results"):
            self._emit_error("Submit the exam before reviewing open answers.")
            return
        api_key = self._exam_session["config"].get("api_key", "")
        if not api_key:
            self._emit_error("Groq API key is required for AI review.")
            return
        question = next(
            (q for q in self._exam_session.get("questions", []) if q.get("id") == question_id),
            None,
        )
        if not question:
            self._emit_error(f"Question {question_id} not found.")
            return
        suggested = question.get("suggested_answer", "") or ""
        student_answer_obj = (self._exam_session.get("answers") or {}).get(question_id) or {}
        if isinstance(student_answer_obj, dict):
            student_text = (student_answer_obj.get("text") or "").strip()
        else:
            student_text = str(student_answer_obj or "").strip()
        existing_worker = self._open_review_workers.get(question_id)
        if existing_worker is not None and existing_worker.isRunning():
            return
        worker = AICheckWorker(api_key, question.get("title", ""), suggested, student_text)
        self._open_review_workers[question_id] = worker
        worker.result_ready.connect(partial(self._on_open_review_ok, question_id, worker))
        worker.error_occurred.connect(partial(self._on_open_review_err, question_id, worker))
        worker.finished.connect(partial(self._cleanup_open_review_worker, question_id, worker))
        worker.start()

    def _on_open_review_ok(self, question_id, worker, feedback):
        if self._open_review_workers.get(question_id) is not worker:
            return
        self.openAnswerReviewReady.emit(_json_dumps({
            "question_id": question_id,
            "ok": True,
            "feedback": feedback,
        }))

    def _on_open_review_err(self, question_id, worker, message):
        if self._open_review_workers.get(question_id) is not worker:
            return
        self.openAnswerReviewReady.emit(_json_dumps({
            "question_id": question_id,
            "ok": False,
            "feedback": f"AI check failed: {message}",
        }))

    @pyqtSlot()
    def refreshHistory(self):
        self.historyReady.emit(_json_dumps(_history_payload()))

    @pyqtSlot()
    def clearHistory(self):
        save_history([])
        self.historyReady.emit(_json_dumps(_history_payload()))

    @pyqtSlot(str)
    def openHistoryReview(self, history_id):
        _, record = self._record_by_history_id(history_id)
        if not record or not record.get("questions"):
            self._emit_error("Detailed review is not available for this exam.")
            return
        questions = record.get("questions", [])
        answers = record.get("answers", {})
        results = record.get("results") or compute_results(questions, answers)
        sections = record.get("sections")  # may be None on legacy entries
        payload = _review_payload(
            record.get("title", "Exam"), questions, answers, results,
            exportable_history_id=history_id,
            sections=sections,
        )
        self.historyReviewReady.emit(_json_dumps(payload))

    @pyqtSlot(str)
    def exportHistoryReviewPdf(self, history_id):
        if not PDF_SUPPORT:
            self._emit_error("Qt PDF support is not available in this build.")
            return
        _, record = self._record_by_history_id(history_id)
        if not record or not record.get("questions"):
            self._emit_error("Detailed review is not available for this exam.")
            return
        questions = record.get("questions", [])
        answers = record.get("answers", {})
        results = record.get("results") or compute_results(questions, answers)
        path, _ = QFileDialog.getSaveFileName(
            self.window,
            "Export review as PDF",
            f"{record.get('title', 'Exam')}_review.pdf",
            "PDF files (*.pdf)",
        )
        if not path:
            return
        html_doc = _build_pdf_html(record.get("title", "Exam"), "Review export", questions, answers, results)
        _render_pdf(html_doc, path)
        self._emit_error(f"PDF saved to: {path}", kind="success")

    @pyqtSlot(str)
    def exportHistoryExamFile(self, history_id):
        _, record = self._record_by_history_id(history_id)
        if not record or not record.get("questions"):
            self._emit_error("Exam definition is not available for this entry.")
            return
        title = record.get("title", "Exam")
        export_exam_file_dialog(
            self.window,
            {"title": title,
             "questions": record.get("questions", []),
             "sections": record.get("sections")},
            default_stem=title,
        )
