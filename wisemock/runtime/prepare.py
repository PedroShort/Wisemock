"""Prepare runtime exam state from saved exam_data + setup config."""
import copy
import json
import random
from datetime import datetime
from pathlib import Path

from wisemock.runtime.payloads import (
    _build_answer_key_from_questions,
    _clean_option_text,
    _compute_score_summary,
)


def _coerce_correct_answer(raw):
    """Normalize `correct_answer` into either str (single) or list[str] (multi).

    Accepts:
      - "C"                              → "C"
      - "A, C" / "A,C" / "A and C"       → ["A", "C"]
      - ["A", "C"]                       → ["A", "C"]
      - ["C"]                            → "C"  (collapse 1-elem list to scalar)
    """
    if isinstance(raw, list):
        letters = [str(item).strip().upper() for item in raw if str(item).strip()]
        return letters[0] if len(letters) == 1 else letters
    if isinstance(raw, str):
        # Defensive split: AI sometimes responds "A, C" as a string.
        import re as _re
        parts = [p.strip().upper() for p in _re.split(r"[,;/]| and ", raw) if p.strip()]
        if len(parts) > 1:
            return parts
        return raw.strip().upper()
    return raw


def _correct_letters_list(correct):
    """Always return list of upper letters (1+ entries) from a `correct_answer` field."""
    if isinstance(correct, list):
        return [str(c).strip().upper() for c in correct if str(c).strip()]
    if isinstance(correct, str) and correct.strip():
        return [correct.strip().upper()]
    return []


def _prepare_mc_question(question, shuffle_options):
    prepared = copy.deepcopy(question)
    options = [_clean_option_text(option) for option in prepared.get("options", [])]
    prepared["correct_answer"] = _coerce_correct_answer(prepared.get("correct_answer", ""))
    if shuffle_options and options:
        # Resolve correct letter(s) → text(s) before shuffling, then re-letter after.
        correct_letters = _correct_letters_list(prepared.get("correct_answer"))
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
            prepared["correct_answer"] = new_letters[0] if len(new_letters) == 1 else new_letters
    prepared["options"] = options
    return prepared


def _normalize_ctx(ctx):
    return (ctx or "").strip().lower()


def _context_counts(exam_data):
    """Count, across the entire exam, how many questions reference each context
    string. Used to gate rendering: a context shown to the student only makes
    sense when ≥2 questions share it. A unique context is almost always the
    source passage leaking the answer."""
    counts = {}
    all_qs = []
    if exam_data.get("sections"):
        for section in exam_data.get("sections", []):
            for question in section.get("questions", []):
                if isinstance(question, dict):
                    all_qs.append(question)
    else:
        all_qs = exam_data.get("questions", []) or []
    for question in all_qs:
        ctx = _normalize_ctx(question.get("context"))
        if ctx:
            counts[ctx] = counts.get(ctx, 0) + 1
    return counts


def _context_leaks_answer(question):
    """Last-resort safety net: even if ≥2 questions share a context, if the
    context literally contains an MC's correct-option text, the context is
    leaking the answer for that question and should be hidden.
    """
    if question.get("type") != "mc":
        return False
    ctx = (question.get("context") or "").lower()
    if not ctx:
        return False
    correct = question.get("correct_answer")
    correct_letters = correct if isinstance(correct, list) else [correct]
    options = question.get("options", [])
    for letter in correct_letters:
        if not isinstance(letter, str) or not letter.strip():
            continue
        idx = ord(letter.strip().upper()) - ord("A")
        if 0 <= idx < len(options):
            opt_text = str(options[idx]).strip().lower()
            # 3-char floor avoids false positives on single-token options like
            # "A" or "0" that would match almost any prose.
            if len(opt_text) >= 3 and opt_text in ctx:
                return True
    return False


def _should_show_context(question, previous_context, counts):
    """Show context iff: it exists, differs from the previous question's
    context (to avoid duplicate display), is shared by >=2 questions in the
    exam, and does not leak the answer for this question.

    Imported JSON can explicitly mark case/table context as required. That
    allows a one-question numerical setup to remain visible without weakening
    the answer-leak check.
    """
    ctx = question.get("context")
    if not ctx:
        return False
    if _normalize_ctx(ctx) == _normalize_ctx(previous_context):
        return False
    if question.get("context_required") or question.get("context_scope") in {"section", "case"}:
        return not _context_leaks_answer(question)
    if counts.get(_normalize_ctx(ctx), 0) < 2:
        return False
    if _context_leaks_answer(question):
        return False
    return True


def _resolve_section_questions(section, lookup):
    resolved = []
    for item in section.get("questions", []):
        if isinstance(item, dict):
            resolved.append(copy.deepcopy(item))
        elif item in lookup:
            resolved.append(copy.deepcopy(lookup[item]))
    return resolved


def _prepare_runtime_exam(config, exam_data):
    lookup = {question.get("id"): question for question in copy.deepcopy(exam_data.get("questions", []))}
    show_numbers = True  # always-on; was previously a removed setup toggle
    shuffle_questions = config.get("shuffle_questions", False)
    shuffle_options = config.get("shuffle_options", False)
    runtime_questions = []
    runtime_sections = []
    global_number = 0
    # Pre-count shared contexts across the whole exam; gate display on ≥2.
    ctx_counts = _context_counts(exam_data)

    def prepare_question(question):
        if question.get("type") == "mc":
            return _prepare_mc_question(question, shuffle_options)
        return copy.deepcopy(question)

    if exam_data.get("sections"):
        for section_index, section in enumerate(copy.deepcopy(exam_data.get("sections", [])), 1):
            section_questions = _resolve_section_questions(section, lookup)
            if shuffle_questions:
                random.shuffle(section_questions)
            prepared_questions = []
            previous_context = None
            for question in section_questions:
                prepared = prepare_question(question)
                global_number += 1
                prepared["_number"] = global_number
                prepared["_number_label"] = f"Q{global_number}" if show_numbers else ""
                prepared["_display_title"] = prepared.get("title", "")
                prepared["_show_context"] = _should_show_context(prepared, previous_context, ctx_counts)
                previous_context = prepared.get("context") if prepared.get("context") else previous_context
                runtime_questions.append(prepared)
                prepared_questions.append(prepared)
            runtime_sections.append({
                "id": f"section-{section_index}",
                "name": section.get("name", f"Section {section_index}"),
                "instructions": section.get("instructions", ""),
                "questions": prepared_questions,
            })
    else:
        grouped = {"mc": [], "fill_blank": [], "open": []}
        flat_questions = [prepare_question(question) for question in copy.deepcopy(exam_data.get("questions", []))]
        if shuffle_questions:
            random.shuffle(flat_questions)
        for question in flat_questions:
            grouped.setdefault(question.get("type", "open"), []).append(question)
        derived_sections = [
            ("Section I — Multiple Choice", grouped.get("mc", [])),
            ("Section II — Fill in the Blank", grouped.get("fill_blank", [])),
            ("Section III — Essay Questions", grouped.get("open", [])),
        ]
        for section_index, (name, section_questions) in enumerate(derived_sections, 1):
            if not section_questions:
                continue
            prepared_questions = []
            previous_context = None
            for question in section_questions:
                global_number += 1
                question["_number"] = global_number
                question["_number_label"] = f"Q{global_number}" if show_numbers else ""
                question["_display_title"] = question.get("title", "")
                question["_show_context"] = _should_show_context(question, previous_context, ctx_counts)
                previous_context = question.get("context") if question.get("context") else previous_context
                runtime_questions.append(question)
                prepared_questions.append(question)
            runtime_sections.append({
                "id": f"section-{section_index}",
                "name": name,
                "instructions": "",
                "questions": prepared_questions,
            })
    return runtime_questions, runtime_sections


def _normalized_answers_from_frontend(raw_answers, questions):
    """Per-question multi-answer detection: a question is multi-answer iff its
    `correct_answer` is a list with ≥2 letters. The runtime no longer needs a
    global `allow_multiple` flag.
    """
    normalized = {}
    for question in questions:
        q_id = question.get("id")
        raw = (raw_answers or {}).get(q_id)
        q_type = question.get("type")
        if raw is None:
            normalized[q_id] = None
            continue
        if q_type == "mc":
            is_multi = isinstance(question.get("correct_answer"), list) and len(question["correct_answer"]) >= 2
            if isinstance(raw, list):
                raw = {"selected_indices": raw}
            if not isinstance(raw, dict):
                raw = {"selected_index": raw}
            if is_multi or "selected_indices" in raw:
                indices = []
                for value in raw.get("selected_indices", []):
                    if value is None or value == "":
                        continue
                    indices.append(int(value))
                indices = sorted(set(indices))
                if not indices:
                    normalized[q_id] = None
                else:
                    letters = [chr(ord("A") + idx) for idx in indices]
                    texts = [question.get("options", [])[idx] for idx in indices if 0 <= idx < len(question.get("options", []))]
                    normalized[q_id] = {
                        "selected_indices": indices,
                        "selected_letters": letters,
                        "selected_texts": texts,
                    }
            else:
                idx = raw.get("selected_index")
                if idx is None or idx == "":
                    normalized[q_id] = None
                else:
                    idx = int(idx)
                    normalized[q_id] = {
                        "selected_index": idx,
                        "selected_letter": chr(ord("A") + idx),
                        "selected_text": question.get("options", [])[idx] if 0 <= idx < len(question.get("options", [])) else "",
                    }
        elif q_type == "open":
            html = ""
            if isinstance(raw, dict):
                text = raw.get("text", "") or raw.get("value", "")
                html = raw.get("html", "") or ""
            else:
                text = str(raw)
            text = text.strip()
            html = html.strip()
            if not text:
                normalized[q_id] = None
            else:
                answer = {"text": text}
                if html:
                    answer["html"] = html
                normalized[q_id] = answer
        elif q_type == "fill_blank":
            if not isinstance(raw, dict):
                raw = {"selected_indices": raw if isinstance(raw, list) else []}
            indices = list(raw.get("selected_indices", []))
            texts = []
            for blank_index, blank_options in enumerate(question.get("blanks", [])):
                selected = indices[blank_index] if blank_index < len(indices) else None
                if selected is None or selected == "":
                    texts.append(None)
                else:
                    selected = int(selected)
                    indices[blank_index] = selected
                    texts.append(blank_options[selected] if 0 <= selected < len(blank_options) else None)
            normalized[q_id] = None if all(text is None for text in texts) else {
                "selected_indices": indices,
                "selected_texts": texts,
            }
        else:
            normalized[q_id] = raw
    return normalized


def _export_submission_json(config, questions, answers, results, remaining_seconds, time_up):
    answer_key = _build_answer_key_from_questions(questions)
    questions_summary = []
    for question in questions:
        q_id = question.get("id")
        entry = {
            "id": q_id,
            "type": question.get("type"),
            "title": question.get("title", ""),
            "student_answer": answers.get(q_id),
            "result": results.get(q_id, "unknown"),
        }
        if q_id in answer_key:
            entry["answer_key"] = answer_key[q_id]
        questions_summary.append(entry)

    score = _compute_score_summary(results)
    payload = {
        "exam_title": config.get("exam_title", "Exam"),
        "student_name": config.get("student_name", ""),
        "exam_duration_seconds": config.get("exam_duration_seconds", 0),
        "submitted_at": datetime.now().isoformat(),
        "time_remaining_seconds": remaining_seconds,
        "time_expired": time_up,
        "score_auto_graded": f"{score['correct']}/{score['total']}" if score["total"] else "n/a",
        "questions": questions_summary,
    }
    with Path(config["export_file"]).open("w", encoding="utf-8") as file_obj:
        json.dump(payload, file_obj, indent=4, ensure_ascii=False)
