"""Pure grading logic: maps student answers to result strings."""


def _correct_letter_set(correct):
    """Normalize a question's `correct_answer` (str OR list[str]) into a set
    of upper-cased letters. Set semantics make single- and multi-answer MCs
    grade through the same path."""
    if isinstance(correct, list):
        return {str(c).strip().upper() for c in correct if str(c).strip()}
    if correct is None:
        return set()
    return {str(correct).strip().upper()}


def compute_results(questions, answers):
    """Returns {q_id: 'correct' | 'incorrect' | 'open' | 'unanswered' | 'unknown'}"""
    results = {}
    for q in questions:
        q_id = q.get("id", "")
        q_type = q.get("type", "")
        answer = (answers or {}).get(q_id)
        if q_type == "open":
            results[q_id] = "open"
        elif q_type == "mc" and "correct_answer" in q:
            if answer is None:
                results[q_id] = "unanswered"
                continue
            if isinstance(answer, dict):
                correct_set = _correct_letter_set(q["correct_answer"])
                if "selected_letters" in answer:
                    sels = {s.upper() for s in answer.get("selected_letters", []) if s}
                else:
                    sel = answer.get("selected_letter", "")
                    sels = {sel.upper()} if sel else set()
                results[q_id] = "correct" if sels and sels == correct_set else "incorrect"
            else:
                results[q_id] = "unanswered"
        elif q_type == "fill_blank" and "correct_answers" in q:
            if answer is None:
                results[q_id] = "unanswered"
                continue
            if isinstance(answer, dict):
                student_texts = answer.get("selected_texts", [])
                blanks = q.get("blanks", [])
                correct_indices = q["correct_answers"]
                all_ok = all(
                    i < len(blanks) and ci < len(blanks[i]) and
                    i < len(student_texts) and student_texts[i] == blanks[i][ci]
                    for i, ci in enumerate(correct_indices)
                )
                results[q_id] = "correct" if all_ok else "incorrect"
            else:
                results[q_id] = "unanswered"
        else:
            results[q_id] = "unknown"
    return results
