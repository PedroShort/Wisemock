"""Persistence layer for exam history (read/write `~/.wiseflow/history.json`)."""
import json
from datetime import datetime

from wisemock.config import HISTORY_DIR, HISTORY_FILE


def load_history() -> list:
    if not HISTORY_FILE.exists():
        return []
    try:
        with HISTORY_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def save_history(records: list) -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    with HISTORY_FILE.open("w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)


def add_history_entry(title: str, correct: int, total: int,
                      time_spent: int, time_available: int,
                      questions: list = None, answers: dict = None,
                      results: dict = None, sections: list = None) -> int:
    """Append a completed-exam record and return its 0-based history_id."""
    records = load_history()
    entry = {
        "date": datetime.now().isoformat(),
        "title": title,
        "correct": correct,
        "total": total,
        "score_pct": round(correct / total * 100, 1) if total > 0 else 0,
        "time_spent_seconds": time_spent,
        "time_available_seconds": time_available,
    }
    if questions is not None:
        entry["questions"] = questions
    if answers is not None:
        entry["answers"] = answers
    if results is not None:
        entry["results"] = results
    if sections is not None:
        # Lightweight: only `name` + `question_ids` per section. The full
        # question objects already live in `entry["questions"]`.
        entry["sections"] = sections
    records.append(entry)
    save_history(records)
    return len(records) - 1


def format_seconds(total_seconds: int) -> str:
    total_seconds = max(0, int(total_seconds))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
