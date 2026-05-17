"""Pure data-shaping functions that produce JSON payloads for the JS frontend.

Everything here is deterministic and side-effect-free. The Bridge calls these,
serializes the result with `_json_dumps`, and emits to QtWebChannel.
"""
import html
import json
import re
from datetime import datetime

from wisemock.core.history import format_seconds, load_history
from wisemock.core.markdown import autofence_code
from wisemock.prompts import FULL_REVIEW_PROMPT


def _md(value):
    """Run autofence on any text destined for the JS frontend's renderInline.

    Safe for empty / non-string inputs.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        return value
    return autofence_code(value)


def _json_dumps(payload):
    return json.dumps(payload, ensure_ascii=False)


def _clean_option_text(text):
    return re.sub(r'^[A-Ha-h]\s*[\.\)\-]\s*', '', str(text)).strip() or str(text)


def _count_question_types(questions):
    counts = {}
    for question in questions:
        q_type = question.get("type", "?")
        counts[q_type] = counts.get(q_type, 0) + 1
    return counts


def _questions_summary_text(questions):
    counts = _count_question_types(questions)
    parts = [f"{count} {kind}" for kind, count in counts.items()]
    total = len(questions)
    return f"{total} question{'s' if total != 1 else ''} ({', '.join(parts)})"


def _history_total_time_label(total_seconds):
    if total_seconds >= 3600:
        return f"{total_seconds / 3600:.1f}h"
    minutes = total_seconds // 60
    return f"{minutes}m"


def _format_history_date(date_value):
    try:
        return datetime.fromisoformat(date_value).strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return "—"


def _format_chart_date(date_value):
    """Short label for chart axes: '21 Mar' or '21 Mar 25' when year differs from current."""
    try:
        dt = datetime.fromisoformat(date_value)
        current_year = datetime.now().year
        if dt.year == current_year:
            return dt.strftime("%-d %b")
        return dt.strftime("%-d %b %y")
    except (ValueError, TypeError):
        return "—"


def _compute_score_summary(results):
    # Count every auto-gradable question (MC + fill_blank), including unanswered ones.
    # Unanswered counts as incorrect for the score, but is still part of the denominator
    # so the user sees their score against the full exam, not just the questions they answered.
    auto_graded = [result for result in results.values() if result in ("correct", "incorrect", "unanswered")]
    correct = sum(1 for result in auto_graded if result == "correct")
    total = len(auto_graded)
    pct = round(correct / total * 100) if total > 0 else 0
    return {"correct": correct, "total": total, "pct": pct}


def _build_answer_key_from_questions(questions):
    key = {}
    for question in questions:
        q_id = question.get("id")
        q_type = question.get("type")
        entry = {}
        if q_type == "mc" and "correct_answer" in question:
            entry["correct_answer"] = question["correct_answer"]
        if q_type == "open" and "suggested_answer" in question:
            entry["suggested_answer"] = question["suggested_answer"]
        if q_type == "fill_blank" and "correct_answers" in question:
            blanks = question.get("blanks", [])
            indices = question["correct_answers"]
            entry["correct_answers_indices"] = indices
            entry["correct_answers_texts"] = [
                blanks[i][idx] if i < len(blanks) and idx < len(blanks[i])
                else "(answer key missing)"
                for i, idx in enumerate(indices)
            ]
        if entry:
            key[q_id] = entry
    return key


def _serialize_answers_for_history(answers):
    serializable = {}
    for qid, answer in (answers or {}).items():
        if answer is None:
            serializable[qid] = None
        elif isinstance(answer, dict):
            serializable[qid] = answer
        else:
            serializable[qid] = {"text": str(answer)}
    return serializable


def _build_history_charts(records):
    """Pre-compute chart-ready data for the Performance tab.

    `records` arrives oldest-first (storage order). We render charts in
    that order so the line "moves forward in time" left-to-right.

    Returns two structures:
      - progression: every attempt, chronological. Drives the line chart.
      - best_per_exam: aggregated by title (best + avg + attempts).
        ONLY populated when at least one title has been attempted more
        than once — otherwise the chart would just duplicate the records
        table and add no insight.
    """
    if not records:
        return {"progression": [], "best_per_exam": []}

    progression = []
    for idx, record in enumerate(records, 1):
        progression.append({
            "x": idx,
            "score": round(record.get("score_pct", 0), 1),
            "date_display": _format_history_date(record.get("date")),
            "date_short": _format_chart_date(record.get("date")),
            "title": record.get("title", "Exam"),
        })

    by_title = {}
    for record in records:
        title = record.get("title", "Exam")
        score = record.get("score_pct", 0)
        entry = by_title.setdefault(title, {
            "title": title, "best": score, "_total": 0.0, "attempts": 0,
        })
        entry["attempts"] += 1
        entry["_total"] += score
        if score > entry["best"]:
            entry["best"] = score

    has_repeats = any(entry["attempts"] >= 2 for entry in by_title.values())
    if not has_repeats:
        best_per_exam = []
    else:
        # Sort by attempts desc (most studied first), then best score desc as tiebreaker.
        # No hard cap — all exams are shown so nothing gets silently dropped.
        best_per_exam = sorted(
            by_title.values(),
            key=lambda e: (e["attempts"], e["best"]),
            reverse=True,
        )
        for entry in best_per_exam:
            entry["avg"] = round(entry["_total"] / entry["attempts"], 1)
            entry["best"] = round(entry["best"], 1)
            entry.pop("_total", None)

    return {"progression": progression, "best_per_exam": best_per_exam}


def _history_payload():
    records = load_history()
    scores = [record.get("score_pct", 0) for record in records]
    total_time = sum(record.get("time_spent_seconds", 0) for record in records)
    payload_records = []
    for idx in reversed(range(len(records))):
        record = records[idx]
        payload_records.append({
            "history_id": str(idx),
            "date_iso": record.get("date", ""),
            "date_display": _format_history_date(record.get("date")),
            "title": record.get("title", "Exam"),
            "score_pct": f"{round(record.get('score_pct', 0))}%",
            "correct": record.get("correct", 0),
            "total": record.get("total", 0),
            "questions_text": f"{record.get('correct', 0)}/{record.get('total', 0)}",
            "time_spent_seconds": record.get("time_spent_seconds", 0),
            "time_display": format_seconds(record.get("time_spent_seconds", 0)),
            "review_available": bool(record.get("questions")),
        })
    return {
        "stats": {
            "total_exams": len(records),
            "average_score": f"{sum(scores) / len(scores):.0f}%" if scores else "—",
            "best_score": f"{max(scores):.0f}%" if scores else "—",
            "total_time": _history_total_time_label(total_time),
        },
        "records": payload_records,
        "charts": _build_history_charts(records),
    }


def _build_review_entry(question, number, answer, result):
    entry = {
        "id": question.get("id", ""),
        "title": _md(f"Q{number}. {question.get('title', '')}"),
        "result": result,
    }
    if question.get("type") == "mc":
        selected_letters = []
        if isinstance(answer, dict):
            if "selected_letters" in answer:
                selected_letters = [letter.upper() for letter in answer.get("selected_letters", [])]
            elif answer.get("selected_letter"):
                selected_letters = [answer.get("selected_letter", "").upper()]
        # `correct_answer` may be str (single) or list[str] (multi)
        raw_correct = question.get("correct_answer", "")
        if isinstance(raw_correct, list):
            correct_letters_set = {str(c).strip().upper() for c in raw_correct if str(c).strip()}
        else:
            correct_letters_set = {str(raw_correct).strip().upper()} if str(raw_correct).strip() else set()
        options = []
        for index, option in enumerate(question.get("options", [])):
            letter = chr(ord("A") + index)
            correct = letter in correct_letters_set
            selected = letter in selected_letters
            prefix = "  "
            state = ""
            if correct and selected:
                prefix, state = "✓", "correct"
            elif selected and not correct:
                prefix, state = "✗", "wrong"
            elif correct and not selected:
                prefix, state = "→", "correct"
            options.append({
                "letter": letter,
                "text": _md(_clean_option_text(option)),
                "prefix": prefix,
                "state": state,
            })
        entry["options"] = options
    elif question.get("type") == "open":
        if isinstance(answer, dict):
            entry["student_text"] = _md(answer.get("text", "") or answer.get("value", ""))
            entry["student_html"] = answer.get("html", "")
        elif isinstance(answer, str):
            entry["student_text"] = _md(answer)
        else:
            entry["student_text"] = ""
        entry["suggested_answer"] = _md(question.get("suggested_answer", ""))
    elif question.get("type") == "fill_blank":
        selected_texts = answer.get("selected_texts", []) if isinstance(answer, dict) else []
        source_blanks = question.get("blanks", [])
        correct_indices = question.get("correct_answers", [])
        blanks = []
        # Always iterate over ALL blanks so the answer key is visible even
        # when the student left the question unanswered.
        for blank_index in range(len(source_blanks)):
            correct_index = correct_indices[blank_index] if blank_index < len(correct_indices) else -1
            correct_text = (
                source_blanks[blank_index][correct_index]
                if 0 <= correct_index < len(source_blanks[blank_index])
                else "(answer key missing)"
            )
            selected_text = (
                selected_texts[blank_index]
                if blank_index < len(selected_texts)
                else None
            )
            blanks.append({
                "index": blank_index + 1,
                "selected_text": selected_text,   # None → rendered as "(blank)" in JS
                "correct_text": correct_text,
                "is_correct": selected_text is not None and selected_text == correct_text,
            })
        entry["blanks"] = blanks
    return entry


def _review_payload(title, questions, answers, results,
                    exportable_history_id=None, only_incorrect=False, sections=None):
    """Build the review-modal payload.

    If `sections` is provided (list of {name, question_ids}), entries are
    grouped by section just like the exam screen. Otherwise a flat
    `entries` list is returned for backward compat (old history records).
    """
    score = _compute_score_summary(results)

    # Build entries indexed by question id; preserve the global question
    # number from the order in `questions` so the "Q1, Q2, ..." labels
    # stay aligned with what the student saw in the exam.
    entries_by_id = {}
    flat_entries = []
    for number, question in enumerate(questions, 1):
        q_id = question.get("id", "")
        result = results.get(q_id, "unknown")
        answer = (answers or {}).get(q_id)
        if only_incorrect and result != "incorrect":
            entries_by_id[q_id] = None
            continue
        entry = _build_review_entry(question, number, answer, result)
        entries_by_id[q_id] = entry
        flat_entries.append(entry)

    grouped_sections = []
    if sections:
        for section in sections:
            section_entries = []
            for q_id in section.get("question_ids", []):
                entry = entries_by_id.get(q_id)
                if entry is None:
                    continue
                section_entries.append(entry)
            if not section_entries and only_incorrect:
                continue
            grouped_sections.append({
                "name": section.get("name", ""),
                "entries": section_entries,
            })

    meta = (
        f"<strong>{html.escape(title)}</strong>"
        f"<span class='pipe'>|</span><span>Score: {score['pct']}%</span>"
        f"<span class='pipe'>|</span><span>{score['correct']}/{score['total']} correct</span>"
    )
    return {
        "title": f"Review — {title}" if not only_incorrect else "Review Mistakes",
        "meta": meta,
        "entries": flat_entries,           # fallback path (no sections)
        "sections": grouped_sections,      # preferred path when available
        "empty_message": "No detailed review available." if not only_incorrect else "No mistakes to review.",
        "exportable_history_id": exportable_history_id,
    }


def _build_full_review_prompt(title, questions, answers, results):
    answer_key = _build_answer_key_from_questions(questions)
    lines = []
    for q_id, result in results.items():
        question = next((item for item in questions if item.get("id") == q_id), {})
        answer = (answers or {}).get(q_id, {})
        ak = answer_key.get(q_id, {})
        line = f"- Question: {question.get('title', '?')}\n  Type: {question.get('type', '?')}\n  Result: {result}\n"
        if isinstance(answer, dict):
            if "selected_letter" in answer:
                line += f"  Student answered: {answer['selected_letter']} — {answer.get('selected_text', '')}\n"
            elif "selected_letters" in answer:
                line += f"  Student answered: {', '.join(answer.get('selected_letters', []))}\n"
            elif "text" in answer or "value" in answer:
                line += f"  Student answered: {answer.get('text', '') or answer.get('value', '')}\n"
            elif "selected_texts" in answer:
                line += f"  Student answered: {', '.join([text or '(blank)' for text in answer['selected_texts']])}\n"
        if "correct_answer" in ak:
            line += f"  Correct answer: {ak['correct_answer']}\n"
        elif "suggested_answer" in ak:
            line += f"  Suggested answer: {ak['suggested_answer']}\n"
        elif "correct_answers_texts" in ak:
            line += f"  Correct answers: {', '.join(ak['correct_answers_texts'])}\n"
        lines.append(line)
    score = _compute_score_summary(results)
    open_count = sum(1 for question in questions if question.get("type") == "open")
    return FULL_REVIEW_PROMPT.format(
        title=title,
        correct=score["correct"],
        total=score["total"],
        pct=score["pct"],
        open_count=open_count,
        details="\n".join(lines),
    )


def _report_to_html(report):
    escaped = html.escape(report)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = escaped.replace("\n- ", "<br>&bull; ").replace("\n", "<br>")
    return f"<div style='font-size:13px; line-height:1.7; color:#1a1a1a;'>{escaped}</div>"


def _section_summary(name, section_questions, instructions):
    if instructions and instructions.strip():
        return instructions.strip()
    count = len(section_questions)
    if all(question.get("type") == "mc" for question in section_questions):
        return f"{count} questions · Single correct answer · No negative marking"
    if all(question.get("type") == "open" for question in section_questions):
        return f"{count} open-ended questions · Show your reasoning clearly"
    if all(question.get("type") == "fill_blank" for question in section_questions):
        return f"{count} fill-in-the-blank questions · Complete each placeholder"
    return f"{count} questions · Mixed section"


def _norm_words(text):
    """Lowercase word tokens, placeholders and punctuation stripped."""
    s = re.sub(r"\{\d+\}", " ", text or "").lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return [w for w in s.split() if w]


def _clean_fill_blank_title(title, template):
    """For fill_blank, the templated sentence (with the dropdown) is rendered
    right below the title. The LLM often echoes that whole sentence into the
    title too, so the student sees it twice. If the title just repeats the
    template, collapse it to a short instruction; otherwise keep the title
    but render any leftover {0}/{1} as a plain blank."""
    tmpl_words = _norm_words(template)
    if tmpl_words:
        title_words = _norm_words(title)
        title_set = set(title_words)
        overlap = sum(1 for w in tmpl_words if w in title_set) / len(tmpl_words)
        if overlap >= 0.6 or " ".join(tmpl_words) in " ".join(title_words):
            return "Complete the sentence:"
    return re.sub(r"\{\d+\}", "_____", title or "")


def _question_payload(question, answers, results, locked):
    q_id = question.get("id")
    _title_src = question.get("_display_title", question.get("title", ""))
    if question.get("type") == "fill_blank":
        _title_src = _clean_fill_blank_title(_title_src, question.get("template", ""))
    payload = {
        "id": q_id,
        "type": question.get("type"),
        "title": _md(_title_src),
        "number_label": question.get("_number_label", ""),
        "context": _md(question.get("context", "")),
        "show_context": question.get("_show_context", False),
        "locked": locked,
        "result": results.get(q_id, "") if results else "",
    }
    if question.get("type") == "mc":
        payload["options"] = [
            {"letter": chr(ord("A") + index), "text": _md(option)}
            for index, option in enumerate(question.get("options", []))
        ]
        # `correct_answer` is str (single) OR list[str] (multi). Surface both
        # the multi flag and the per-letter index list so the frontend can
        # render single-radio vs multi-checkbox per question.
        correct = question.get("correct_answer", "A")
        correct_letters = correct if isinstance(correct, list) else [correct]
        correct_letters = [str(c).strip().upper() for c in correct_letters if str(c).strip()]
        correct_indices = [ord(letter) - ord("A") for letter in correct_letters if letter]
        payload["multi_answer"] = len(correct_letters) >= 2
        payload["correct_index"] = correct_indices[0] if correct_indices else 0
        payload["correct_indices"] = correct_indices
    elif question.get("type") == "open":
        payload["placeholder"] = question.get("placeholder", "Write your answer here...")
        payload["suggested_answer"] = _md(question.get("suggested_answer", ""))
        payload["max_words"] = question.get("max_words", 200)
    elif question.get("type") == "fill_blank":
        payload["template"] = question.get("template", "")
        payload["blanks"] = question.get("blanks", [])
        if results:
            raw_answer = answers.get(q_id)
            answer = raw_answer if isinstance(raw_answer, dict) else {}
            selected_texts = answer.get("selected_texts", [])
            source_blanks = question.get("blanks", [])
            correct_indices = question.get("correct_answers", [])
            blank_results = []
            # Build a result entry for EVERY blank, even when the student left
            # the question unanswered. This way the on-exam review shows the
            # correct answer next to each blank instead of nothing.
            for blank_index in range(len(source_blanks)):
                correct_index = correct_indices[blank_index] if blank_index < len(correct_indices) else -1
                options = source_blanks[blank_index]
                # If the LLM produced this question without valid
                # correct_answers, surface that explicitly rather than a
                # cryptic "?" — and treat the answer as un-gradable so the
                # student isn't marked wrong for the model's omission.
                answer_known = bool(options) and 0 <= correct_index < len(options)
                correct_text = options[correct_index] if answer_known else "(answer key missing)"
                selected_text = selected_texts[blank_index] if blank_index < len(selected_texts) else None
                blank_results.append({
                    "is_correct": (
                        answer_known
                        and selected_text is not None
                        and selected_text == correct_text
                    ),
                    "correct_text": correct_text,
                    "selected_text": selected_text,
                })
            payload["blank_results"] = blank_results
    return payload


def _exam_payload_from_session(session):
    answers = session.get("answers", {})
    results = session.get("results", {})
    locked = bool(session.get("time_up")) and not session.get("is_submitted")
    score = _compute_score_summary(results) if results else None
    open_count = sum(1 for question in session.get("questions", []) if question.get("type") == "open")
    score_banner = ""
    if score and score["total"]:
        score_banner = f"Score: {score['correct']}/{score['total']} auto-graded questions correct"
        if open_count:
            score_banner += f" - {open_count} open-ended not included"
    sections = []
    for section in session.get("sections", []):
        section_questions = section.get("questions", [])
        sections.append({
            "id": section.get("id"),
            "name": section.get("name"),
            "summary": _section_summary(section.get("name"), section_questions, section.get("instructions", "")),
            "questions": [_question_payload(question, answers, results, locked) for question in section_questions],
        })
    return {
        "exam_title": session["config"].get("exam_title", "Exam"),
        "remaining_seconds": session.get("remaining_seconds", 0),
        "remaining_display": format_seconds(session.get("remaining_seconds", 0)),
        "is_paused": session.get("is_paused", False),
        "time_up": session.get("time_up", False),
        "is_submitted": session.get("is_submitted", False),
        "intro_blocks": session.get("intro_blocks", []),
        "sections": sections,
        "answers": answers,
        "results": results,
        "score_banner": score_banner,
        "time_up_banner": "Time is over. The exam is locked. You can only click Submit."
        if session.get("time_up") and not session.get("is_submitted") else "",
        "can_review_mistakes": any(result == "incorrect" for result in results.values()) if results else False,
        "can_ai_report": bool(session["config"].get("api_key")) and bool(results),
        "has_api_key": bool(session["config"].get("api_key")),
        "existing_config_flags": {},
    }
