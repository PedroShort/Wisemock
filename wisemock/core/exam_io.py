"""Reading exam JSON files and shaping in-memory exam dicts.

No Qt deps — all UI-side dialogs around export/import live in `wisemock.export`.
"""
import json
from pathlib import Path


_QUESTION_DROP_FIELDS = {
    "student_answer",
    "student_answer_html",
    "answered",
    "result",
}


def _clean_question(question: dict) -> dict:
    """Return an exam-safe question definition without runtime/submission state."""
    return {
        key: value
        for key, value in question.items()
        if key not in _QUESTION_DROP_FIELDS and not key.startswith("_")
    }


def _clean_questions(questions) -> list:
    return [_clean_question(q) for q in questions if isinstance(q, dict)]


def _question_ids_from_section(section: dict) -> list:
    ids = section.get("question_ids")
    if isinstance(ids, list) and ids:
        return [str(qid) for qid in ids if str(qid).strip()]
    ids = []
    for item in section.get("questions", []) or []:
        if isinstance(item, str) and item.strip():
            ids.append(item.strip())
        elif isinstance(item, dict) and item.get("id"):
            ids.append(str(item["id"]))
    return ids


def _question_lookup(questions: list) -> dict:
    return {
        question.get("id"): question
        for question in questions
        if isinstance(question, dict) and question.get("id")
    }


def _sections_with_resolved_questions(sections, questions: list) -> list:
    lookup = _question_lookup(questions)
    resolved_sections = []
    for section in sections or []:
        if not isinstance(section, dict):
            continue
        section_payload = {
            key: value
            for key, value in section.items()
            if key not in {"questions", "question_ids"} and not key.startswith("_")
        }
        section_questions = _clean_questions(section.get("questions", []))
        if not section_questions:
            section_questions = [
                _clean_question(lookup[qid])
                for qid in _question_ids_from_section(section)
                if qid in lookup
            ]
        section_payload["questions"] = section_questions
        resolved_sections.append(section_payload)
    return resolved_sections


def normalize_exam_data(data: dict) -> dict:
    """Normalize supported exam JSON shapes into a loadable WiseMock exam.

    WiseMock files normally include a top-level `questions` list. Some history
    exports store sections as lightweight `question_ids`; this resolves those
    IDs back to full question objects when the top-level questions are present.
    """
    if not isinstance(data, dict):
        return data

    exam = dict(data)
    sections = exam.get("sections") if isinstance(exam.get("sections"), list) else []
    questions = _clean_questions(exam.get("questions", []))

    if not questions and sections:
        seen = set()
        for section in sections:
            raw_questions = section.get("questions", []) if isinstance(section, dict) else []
            for question in _clean_questions(raw_questions):
                qid = question.get("id")
                if qid and qid in seen:
                    continue
                if qid:
                    seen.add(qid)
                questions.append(question)

    exam["questions"] = questions
    if sections:
        exam["sections"] = _sections_with_resolved_questions(sections, questions)
    return exam


def _exam_file_payload(exam_data: dict) -> dict:
    """Strip in-flight student state, keep correct/suggested answers.

    The result is what we serialize as a `.exam.json` file — self-contained
    enough to re-import as a WiseMock exam.
    """
    exam_data = normalize_exam_data(exam_data or {})
    payload = {"title": exam_data.get("title", "Exam")}
    questions = _clean_questions(exam_data.get("questions", []))
    if questions:
        payload["questions"] = questions
    if exam_data.get("sections"):
        payload["sections"] = _sections_with_resolved_questions(
            exam_data["sections"],
            questions,
        )
    return payload


def load_questions_from_json(file_path: str) -> dict:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Questions file not found: {file_path}")
    with path.open("r", encoding="utf-8") as f:
        return normalize_exam_data(json.load(f))
