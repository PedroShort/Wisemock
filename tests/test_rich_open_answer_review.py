import re
import unittest
from pathlib import Path

from wisemock.runtime.payloads import _review_payload
from wisemock.runtime.prepare import _normalized_answers_from_frontend


FRONTEND_HTML = (
    Path(__file__).resolve().parents[1]
    / "wisemock"
    / "assets"
    / "wisemock_frontend.html"
)


class RichOpenAnswerReviewTests(unittest.TestCase):
    def test_review_payload_keeps_sanitized_html_answer_field(self):
        payload = _review_payload(
            "Demo",
            [{"id": "q1", "type": "open", "title": "Explain", "suggested_answer": "A"}],
            {"q1": {"text": "x\ny", "html": "<ol><li>x</li><li>y</li></ol>"}},
            {"q1": "open"},
        )

        entry = payload["entries"][0]
        self.assertEqual(entry["student_text"], "x\ny")
        self.assertEqual(entry["student_html"], "<ol><li>x</li><li>y</li></ol>")

    def test_submit_normalization_preserves_rich_open_answer_html(self):
        normalized = _normalized_answers_from_frontend(
            {"q1": {"text": "bold and underlined", "html": "<strong>bold</strong> and <u>underlined</u>"}},
            [{"id": "q1", "type": "open"}],
        )

        self.assertEqual(
            normalized["q1"],
            {"text": "bold and underlined", "html": "<strong>bold</strong> and <u>underlined</u>"},
        )

    def test_frontend_saves_and_renders_rich_open_answer_html(self):
        source = FRONTEND_HTML.read_text(encoding="utf-8")

        self.assertIn("function sanitizeRichAnswerHtml", source)
        self.assertIn('"OL", "UL", "LI"', source)
        self.assertIn("const html = sanitizeRichAnswerHtml(node.innerHTML || \"\")", source)
        self.assertIn("setDraftAnswer(qid, { text, html })", source)
        self.assertIn("entry.student_html", source)
        self.assertIn("review-rich-answer", source)

        render_open = re.search(
            r"function renderOpenQuestion\(question, submitted\) \{(?P<body>.*?)\n    function renderQuestion",
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(render_open)
        self.assertIn("answer.html ? sanitizeRichAnswerHtml(answer.html)", render_open.group("body"))


if __name__ == "__main__":
    unittest.main()
