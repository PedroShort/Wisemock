"""Background QThread workers that talk to the Groq API.

Three workers:
- AICheckWorker:        grade one open-ended answer.
- ExamGeneratorWorker:  generate fresh questions from study material.
- FullReviewWorker:     produce a study report after an exam submission.
"""
import json
import re
import sys
import time
import urllib.error
from collections import Counter

from PyQt5.QtCore import QThread, pyqtSignal

from wisemock.api.groq import groq_request, _handle_worker_error, _tpm_state, _tpm_lock
from wisemock.core.chunking import (
    chunk_text,
    _strip_markdown_fences,
    _parse_json_lenient,
)
from wisemock.core.input_loading import load_input_paths
from wisemock.prompts import GENERATE_EXAM_PROMPT


# Tuning knobs for chunk-size adaptation. Heuristic — not calibrated with
# data. Documents under SMALL_DOC_CHAR_THRESHOLD use larger chunks so the
# generator makes fewer API calls; larger docs use smaller chunks to keep
# each call's input + output budget tight under Groq's free-tier TPM.
SMALL_DOC_CHAR_THRESHOLD = 50_000
LARGE_CHUNK_CHARS = 12_000
SMALL_CHUNK_CHARS = 6_000


class DocumentLoadWorker(QThread):
    progress = pyqtSignal(int, str)
    finished_ok = pyqtSignal(dict)
    finished_err = pyqtSignal(str)

    def __init__(self, paths):
        super().__init__()
        self.paths = list(paths or [])

    def run(self):
        try:
            result = load_input_paths(
                self.paths,
                progress=lambda percent, message: self.progress.emit(percent, message),
            )
            self.finished_ok.emit(result)
        except Exception as error:
            self.finished_err.emit(str(error))


def _is_well_formed_question(q):
    """Reject questions the LLM generated with broken schema before the
    student ever sees them. Returns True for keepers.

    - mc: needs `options` (list, ≥2) and `correct_answer` (str letter or list).
    - open: needs `title`; suggested_answer optional but recommended.
    - fill_blank: needs `template` with at least one {N} placeholder,
      `blanks` matching the number of placeholders, and `correct_answers`
      with valid indices into each blank's options. 8b-instant tends to
      produce fill_blanks where the blank is in the wrong place or
      `correct_answers` is missing entirely — those become unanswerable
      questions in the UI.
    """
    if not isinstance(q, dict):
        return False
    qtype = q.get("type")
    if not q.get("title"):
        return False
    if qtype == "mc":
        opts = q.get("options")
        if not isinstance(opts, list) or len(opts) < 2:
            return False
        if not q.get("correct_answer"):
            return False
        return True
    if qtype == "open":
        return True
    if qtype == "fill_blank":
        template = q.get("template")
        if not isinstance(template, str) or "{0}" not in template:
            return False
        blanks = q.get("blanks")
        if not isinstance(blanks, list) or not blanks:
            return False
        # Count placeholders {0}, {1}, ... in template; must match blanks length.
        placeholder_indices = sorted(int(m) for m in re.findall(r"\{(\d+)\}", template))
        if placeholder_indices != list(range(len(blanks))):
            return False
        answers = q.get("correct_answers")
        if not isinstance(answers, list) or len(answers) != len(blanks):
            return False
        for i, idx in enumerate(answers):
            if not isinstance(idx, int):
                return False
            opts_i = blanks[i] if isinstance(blanks[i], list) else None
            if not opts_i or not (0 <= idx < len(opts_i)):
                return False
        return True
    return False


def _question_signature(q):
    """Normalized identity of a question, for cross-chunk dedup. Two chunks
    covering overlapping material often regenerate the same question; without
    this they both end up in the exam (different ids, identical content)."""
    def norm(text):
        s = re.sub(r"\{\d+\}", " ", str(text or "")).lower()
        s = re.sub(r"[^a-z0-9\s]", " ", s)
        return " ".join(s.split())

    if not isinstance(q, dict):
        return None
    title = norm(q.get("title"))
    qtype = q.get("type")
    if qtype == "mc":
        opts = sorted(norm(o) for o in q.get("options", []))
        return f"mc||{title}||{'|'.join(opts)}"
    if qtype == "fill_blank":
        return f"fb||{title}||{norm(q.get('template'))}"
    return f"{qtype}||{title}||{norm(q.get('context'))[:200]}"


class AICheckWorker(QThread):
    result_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, api_key: str, question: str, suggested: str, student: str):
        super().__init__()
        self.api_key, self.question, self.suggested, self.student = api_key, question, suggested, student

    def run(self):
        # No Python pre-filter. The AI grader reads every answer and decides.
        # A fixed code-side rule list would be something students could probe
        # and game ("which exact strings get auto-zeroed?"); a semantic judge
        # is harder to deceive. The prompt below tells the model to give 0
        # for empty / gibberish / off-topic content.
        has_ref = bool((self.suggested or "").strip())
        if has_ref:
            body = (
                f"Question: {self.question}\n"
                f"Reference answer: {self.suggested}\n"
                f"Student answer: {self.student or '(no answer)'}\n\n"
                f"Compare the student's answer to the reference and grade it."
            )
        else:
            body = (
                f"Question: {self.question}\n"
                f"Student answer: {self.student or '(no answer)'}\n\n"
                f"No reference answer is available. Grade the student's answer "
                f"based on relevance to the question, factual correctness and "
                f"clarity."
            )
        # The model is the only judge — it must catch garbage itself, since
        # there is no Python pre-filter anymore. The rules below make the
        # zero cases explicit so a student cannot pass off "(no answer)",
        # random characters, or a copy of the question as a real answer.
        prompt = (
            "You are grading one exam answer. READ the question and the "
            "student's answer carefully before scoring. Use the Portuguese "
            "20-point scale (0 = wrong/none, 10 = pass threshold, 20 = perfect).\n\n"
            "SCORING RULES (apply in order):\n"
            "- Empty, '(no answer)', random characters, repeated letters, "
            "keyboard mash, or text in no real language → 0.\n"
            "- A restatement of the question, or filler that does not actually "
            "answer it ('I don't know', 'not sure', a single unrelated word) → 0.\n"
            "- Off-topic, or addresses a different question → 0.\n"
            "- On-topic but no reasoning / definition / evidence → at most 4.\n"
            "- Otherwise grade on correctness, completeness and clarity. Be "
            "strict; do NOT give credit for effort or length alone.\n\n"
            f"{body}\n\n"
            "Respond in exactly this format, nothing else:\n"
            "Score: X/20\n"
            "Feedback: [one short sentence]"
        )
        try:
            # quality_no_low: grading NEVER degrades to the weak 8B. If all
            # good models are saturated, groq_request raises and we surface
            # it via error_occurred (the existing "AI check failed" path) —
            # an unreliable grade is worse than "temporarily unavailable".
            meta = {}
            text = groq_request(self.api_key, [{"role": "user", "content": prompt}],
                                max_tokens=200, timeout=30,
                                routing_mode="quality_no_low", meta=meta)
            print(f"[AICheckWorker] model={meta.get('model')}", file=sys.stderr)
            self.result_ready.emit(text)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            try:
                err_msg = json.loads(err_body).get("error", {}).get("message", err_body)
            except Exception:
                err_msg = err_body
            self.error_occurred.emit(f"API error {e.code}: {err_msg}")
        except Exception as e:
            self.error_occurred.emit(str(e))


class ExamGeneratorWorker(QThread):
    progress = pyqtSignal(str)
    finished_ok = pyqtSignal(dict)
    finished_err = pyqtSignal(str)

    def __init__(self, api_key: str, text: str, difficulty,
                 size: str, q_types: list, source_name: str,
                 custom_question_count=None, chunk_sleep: float = 5.0):
        super().__init__()
        self.api_key, self.text = api_key, text
        # Difficulty can be:
        #   - int 1-10 (new slider) → mapped to "N/10 (label)"
        #   - str "easy"/"medium"/"hard" (legacy)
        # We normalize to a descriptive string the LLM can reason about.
        self.difficulty_level = self._difficulty_number(difficulty)
        self.difficulty = self._normalize_difficulty(difficulty)
        self.size = size
        self.custom_question_count = custom_question_count
        self.q_types, self.source_name = q_types, source_name
        # Static sleep between chunks, used ONLY when groq_request's TPM-header
        # cache is still cold (rare — only if the first call didn't return
        # ratelimit headers). In normal flow we trust _wait_for_budget in
        # groq.py which paces calls using x-ratelimit-remaining-tokens. The
        # old 40s default was redundant safety that cost ~4 minutes on a
        # 7-chunk job.
        self.chunk_sleep = max(0.0, float(chunk_sleep))

    @staticmethod
    def _difficulty_number(value) -> int:
        try:
            n = int(value)
            return max(1, min(10, n))
        except (TypeError, ValueError):
            pass
        label = str(value or "").strip().lower()
        if label in {"very easy", "easy"}:
            return 2
        if label in {"hard", "challenging"}:
            return 8
        if label in {"expert", "very hard"}:
            return 10
        return 5

    @staticmethod
    def _normalize_difficulty(value) -> str:
        """Accept int 1-10 OR legacy strings; return a descriptive label."""
        # Try int first (covers '7' strings from form inputs too).
        try:
            n = int(value)
            if 1 <= n <= 10:
                if n <= 2:
                    label = "Very easy"
                elif n <= 4:
                    label = "Easy"
                elif n <= 6:
                    label = "Moderate"
                elif n <= 8:
                    label = "Challenging"
                else:
                    label = "Expert"
                return f"{n}/10 ({label})"
        except (TypeError, ValueError):
            pass
        # Legacy strings — pass through, lower-cased.
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
        return "moderate"

    @staticmethod
    def _difficulty_guidance(level: int) -> str:
        level = max(1, min(10, int(level or 5)))
        if level <= 2:
            return (
                "- Very easy: test direct recognition of named terms, definitions, "
                "and explicitly stated facts.\n"
                "- Keep stems short and answerable from one sentence in the source.\n"
                "- MC distractors should be clearly wrong, not subtle."
            )
        if level <= 4:
            return (
                "- Easy: test basic comprehension and simple one-step application.\n"
                "- Prefer questions that ask what a concept means or where it applies.\n"
                "- MC distractors may be plausible, but avoid fine distinctions."
            )
        if level <= 6:
            return (
                "- Moderate: mix comprehension with application across related ideas.\n"
                "- Ask for causes, consequences, comparisons, or calculations directly "
                "supported by the material.\n"
                "- MC distractors should reflect common misunderstandings."
            )
        if level <= 8:
            return (
                "- Challenging: require synthesis across multiple parts of the material.\n"
                "- Avoid pure definition questions unless the definition is used in a scenario.\n"
                "- MC distractors should be close but distinguishable by one important condition."
            )
        return (
            "- Expert: require multi-step reasoning, edge cases, trade-offs, or applying "
            "a concept to a new scenario grounded in the source.\n"
            "- Do not ask direct recall or simple definition questions.\n"
            "- MC distractors should be sophisticated, but exactly one answer set must "
            "be defensible from the material."
        )

    @staticmethod
    def _temperature_for_difficulty(level: int) -> float:
        level = max(1, min(10, int(level or 5)))
        if level <= 2:
            return 0.25
        if level <= 6:
            return 0.35
        if level <= 8:
            return 0.45
        return 0.5

    def _target_questions(self) -> int:
        if self.size == "custom":
            try:
                return max(1, min(200, int(self.custom_question_count)))
            except (TypeError, ValueError):
                return 20
        return {"small": 10, "medium": 20, "large": 30}.get(self.size, 20)

    @staticmethod
    def _cap_and_reid_questions(questions, target_questions: int):
        capped = list(questions or [])[:max(0, int(target_questions))]
        for index, question in enumerate(capped, 1):
            question["id"] = f"q{index}"
        return capped

    @staticmethod
    def _max_tokens_for_request(n_questions: int) -> int:
        # Keep output budget close to the requested count. This prevents a
        # "generate 1" call from having enough completion room to return a
        # monster batch if the model ignores the prompt.
        return max(700, min(2200, int(n_questions) * 450 + 250))

    @staticmethod
    def _type_schedule(q_types, target_questions: int):
        allowed = [qtype for qtype in (q_types or ["mc", "open", "fill_blank"])
                   if qtype in {"mc", "open", "fill_blank"}]
        if not allowed:
            allowed = ["mc", "open", "fill_blank"]
        return [allowed[index % len(allowed)] for index in range(max(0, int(target_questions)))]

    @staticmethod
    def _type_plan_text(type_slice) -> str:
        counts = Counter(type_slice or [])
        if not counts:
            return "none"
        order = ["mc", "open", "fill_blank"]
        return ", ".join(f"{qtype}={counts[qtype]}" for qtype in order if counts.get(qtype))

    @staticmethod
    def _select_chunks_for_budget(chunks, target_questions: int):
        """Sample large documents so exam size remains a total budget.

        The old generator processed every chunk with a minimum of two
        questions. A 60-chunk multi-file upload therefore produced a huge exam
        even when the user chose "Small". Here "Small (~10 Q)" means roughly
        ten questions total, so we sample at most one chunk per requested
        question across the full material.
        """
        if len(chunks) <= target_questions:
            return [(index + 1, chunk) for index, chunk in enumerate(chunks)]
        if target_questions <= 1:
            return [(1, chunks[0])]
        last = len(chunks) - 1
        selected = []
        seen = set()
        for i in range(target_questions):
            source_index = round(i * last / (target_questions - 1))
            if source_index in seen:
                continue
            seen.add(source_index)
            selected.append((source_index + 1, chunks[source_index]))
        return selected

    @staticmethod
    def _adaptive_chunk_size(total_chars: int) -> int:
        """Pick a chunk size that minimises API calls without busting the
        per-request TPM ceiling (~6000 on free tier). Thresholds are the
        module-level constants SMALL_DOC_CHAR_THRESHOLD / LARGE_CHUNK_CHARS /
        SMALL_CHUNK_CHARS — adjust there, not here.
        """
        if total_chars < SMALL_DOC_CHAR_THRESHOLD:
            return LARGE_CHUNK_CHARS
        return SMALL_CHUNK_CHARS

    def run(self):
        try:
            # Chunk size is adaptive (see _adaptive_chunk_size) — fewer chunks
            # for medium docs, smaller chunks for big docs. With max_tokens=1500
            # output, every per-call budget stays under the 6000 TPM ceiling.
            chunk_size = self._adaptive_chunk_size(len(self.text))
            chunks = chunk_text(self.text, max_chars=chunk_size)
            n_chunks = len(chunks)
            target_questions = self._target_questions()
            selected_chunks = self._select_chunks_for_budget(chunks, target_questions)
            self.progress.emit(
                f"Material split into {n_chunks} part(s) — sampling "
                f"{len(selected_chunks)} for ~{target_questions} questions…"
            )
            type_schedule = self._type_schedule(self.q_types, target_questions)
            # Large docs prioritise the highest-TPM model (Scout, 30K) to
            # avoid 413s; smaller docs prioritise quality.
            routing_mode = ("tpm" if len(self.text) >= SMALL_DOC_CHAR_THRESHOLD
                            else "quality")
            warned_low_quality = False
            all_questions = []
            seen_signatures = set()
            for selected_index, (source_part, chunk) in enumerate(selected_chunks, 1):
                if selected_index > 1:
                    # The model waterfall handles pacing (it switches models
                    # instead of waiting). This static sleep only triggers in
                    # the cold-start edge: no TPM headers recorded for ANY
                    # model yet (e.g. first call failed before headers).
                    with _tpm_lock:
                        cache_cold = not _tpm_state
                    if cache_cold and self.chunk_sleep > 0:
                        time.sleep(self.chunk_sleep)
                remaining = target_questions - len(all_questions)
                if remaining <= 0:
                    break
                chunks_left = len(selected_chunks) - selected_index + 1
                per_chunk = max(1, min(remaining, (remaining + chunks_left - 1) // chunks_left))
                type_slice = type_schedule[len(all_questions):len(all_questions) + per_chunk]
                request_types = list(dict.fromkeys(type_slice))
                q_types_str = ", ".join(request_types)
                type_plan = self._type_plan_text(type_slice)
                self.progress.emit(
                    f"Processing selected part {selected_index}/{len(selected_chunks)} "
                    f"(source part {source_part}/{n_chunks}, {type_plan})…"
                )
                prompt = GENERATE_EXAM_PROMPT.format(
                    n_questions=per_chunk, difficulty=self.difficulty,
                    difficulty_guidance=self._difficulty_guidance(self.difficulty_level),
                    q_types=q_types_str, type_plan=type_plan, material=chunk,
                )
                meta = {}
                raw = _strip_markdown_fences(
                    groq_request(
                        self.api_key,
                        [{"role": "user", "content": prompt}],
                        max_tokens=self._max_tokens_for_request(per_chunk),
                        # Low temperature: factual MCQ generation needs the
                        # model to copy numbers and facts literally rather
                        # than reinterpret them. The default 0.7 produced
                        # wrong `correct_answer` on overlapping ranges.
                        temperature=self._temperature_for_difficulty(self.difficulty_level),
                        routing_mode=routing_mode,
                        meta=meta,
                    )
                )
                print(f"[ExamGeneratorWorker] chunk {source_part}/{n_chunks} "
                      f"model={meta.get('model')} "
                      f"low_q={meta.get('low_quality_fallback')}", file=sys.stderr)
                if meta.get("low_quality_fallback") and not warned_low_quality:
                    warned_low_quality = True
                    self.progress.emit(
                        "⚠ Generated with backup model — please review answers carefully."
                    )
                try:
                    questions = _parse_json_lenient(raw)
                except json.JSONDecodeError:
                    # Log the head of the raw response so we can diagnose
                    # what the model returned next time without breaking UX.
                    print(
                        f"[ExamGeneratorWorker] JSON parse failed on chunk {source_part}/{n_chunks}. "
                        f"First 500 chars of raw response:\n{raw[:500]}",
                        file=sys.stderr,
                    )
                    # Skip this chunk rather than aborting the whole exam —
                    # other chunks may still produce valid questions.
                    continue
                if isinstance(questions, dict):
                    questions = questions.get("questions", [])
                # Safety nets: (1) drop any question whose type wasn't
                # requested; (2) drop questions with broken schema (especially
                # fill_blank where the LLM frequently omits correct_answers
                # or puts the blank in the wrong place).
                allowed = set(request_types)
                requested_counts = Counter(type_slice)
                accepted_counts = Counter()
                for q in questions:
                    if not isinstance(q, dict):
                        continue
                    qtype = q.get("type")
                    if qtype not in allowed:
                        continue
                    if accepted_counts[qtype] >= requested_counts[qtype]:
                        continue
                    if not _is_well_formed_question(q):
                        print(
                            f"[ExamGeneratorWorker] dropping malformed "
                            f"{q.get('type', '?')} question on chunk {source_part}/{n_chunks}: "
                            f"{str(q)[:200]}",
                            file=sys.stderr,
                        )
                        continue
                    sig = _question_signature(q)
                    if sig in seen_signatures:
                        print(
                            f"[ExamGeneratorWorker] dropping duplicate question "
                            f"on chunk {source_part}/{n_chunks}: {str(q.get('title',''))[:120]}",
                            file=sys.stderr,
                        )
                        continue
                    seen_signatures.add(sig)
                    q["id"] = f"q{len(all_questions) + 1}"
                    all_questions.append(q)
                    accepted_counts[qtype] += 1
                    if len(all_questions) >= target_questions:
                        break
            if not all_questions:
                self.finished_err.emit("AI returned no questions. Try again.")
                return
            all_questions = self._cap_and_reid_questions(all_questions, target_questions)
            exam = {"title": f"Mock — {self.source_name}", "questions": all_questions}
            self.progress.emit(f"Done! Generated {len(all_questions)} questions.")
            self.finished_ok.emit(exam)
        except Exception as e:
            _handle_worker_error(self.finished_err, e)


class FullReviewWorker(QThread):
    result_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, api_key: str, prompt: str):
        super().__init__()
        self.api_key, self.prompt = api_key, prompt

    def run(self):
        try:
            meta = {}
            text = groq_request(self.api_key, [{"role": "user", "content": self.prompt}],
                                max_tokens=1500, temperature=0.6,
                                routing_mode="quality", meta=meta)
            print(f"[FullReviewWorker] model={meta.get('model')} "
                  f"low_q={meta.get('low_quality_fallback')}", file=sys.stderr)
            self.result_ready.emit(text)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            try:
                err_msg = json.loads(err_body).get("error", {}).get("message", err_body)
            except Exception:
                err_msg = err_body
            self.error_occurred.emit(f"API error {e.code}: {err_msg}")
        except Exception as e:
            self.error_occurred.emit(str(e))
