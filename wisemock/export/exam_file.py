"""Save-dialog wrapper around `_exam_file_payload` from core.exam_io."""
import json
import re
from pathlib import Path

from PyQt5.QtWidgets import QFileDialog, QMessageBox

from wisemock.core.exam_io import _exam_file_payload


def export_exam_file_dialog(parent, exam_data: dict, default_stem: str = "exam") -> str:
    if not exam_data or not (exam_data.get("questions") or exam_data.get("sections")):
        QMessageBox.warning(parent, "Nothing to export", "No parsed exam is available.")
        return ""
    safe_stem = re.sub(r"[^\w\-. ]+", "_", default_stem).strip() or "exam"
    path, _ = QFileDialog.getSaveFileName(
        parent, "Export exam file", f"{safe_stem}.exam.json",
        "WiseMock exam files (*.exam.json);;JSON files (*.json)",
    )
    if not path:
        return ""
    payload = _exam_file_payload(exam_data)
    try:
        with Path(path).open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except OSError as e:
        QMessageBox.warning(parent, "Export failed", str(e))
        return ""
    QMessageBox.information(parent, "Exported", f"Exam file saved to:\n{path}")
    return path
