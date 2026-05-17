import unittest
from pathlib import Path

from wisemock.core.exam_io import _exam_file_payload


ROOT = Path(__file__).resolve().parents[1]


class ExamImportCleanupTests(unittest.TestCase):
    def test_removed_document_exam_symbols_are_absent_from_runtime_sources(self):
        files = [
            ROOT / "wisemock" / "runtime" / "bridge.py",
            ROOT / "wisemock" / "workers.py",
            ROOT / "wisemock" / "assets" / "wisemock_frontend.html",
            ROOT / "wisemock" / "pages" / "setup.py",
            ROOT / "wisemock" / "prompts.py",
            ROOT / "wiseflow.py",
        ]
        forbidden = [
            "Ready-" + "made",
            "Exam" + "Parser" + "Worker",
            "PARSE_" + "EXAM_PROMPT",
            "READY_" + "EXAM_BLOCK_PROMPT",
            "parse" + "Exam",
            "choose" + "DocumentIntent",
            "parser" + "Panel",
            "show_" + "parse",
            "parser_" + "busy",
            "parser_" + "status",
            "pending_" + "choice",
        ]
        for path in files:
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                self.assertNotIn(token, text, f"{token} leaked into {path}")

    def test_exam_export_drops_legacy_parser_metadata(self):
        payload = _exam_file_payload({
            "title": "Legacy import",
            "parse_" + "meta": {"parser": "old"},
            "parse_" + "warnings": ["legacy warning"],
            "questions": [
                {
                    "id": "q1",
                    "type": "open",
                    "title": "Explain it.",
                    "suggested_answer": "A model answer.",
                    "student_answer": "runtime state",
                }
            ],
        })
        self.assertNotIn("parse_" + "meta", payload)
        self.assertNotIn("parse_" + "warnings", payload)
        self.assertNotIn("student_answer", payload["questions"][0])


if __name__ == "__main__":
    unittest.main()
