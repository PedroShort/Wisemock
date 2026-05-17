import unittest

from wisemock.core.grading import compute_results
from wisemock.runtime.payloads import _compute_score_summary, _exam_payload_from_session


class AutoGradedScoreTests(unittest.TestCase):
    def test_open_questions_are_not_counted_as_auto_graded(self):
        questions = [
            {"id": "mc1", "type": "mc", "correct_answer": "A"},
            {"id": "mc2", "type": "mc", "correct_answer": "B"},
            {"id": "mc3", "type": "mc", "correct_answer": "C"},
            {"id": "mc4", "type": "mc", "correct_answer": "D"},
            {
                "id": "fb1",
                "type": "fill_blank",
                "blanks": [["x", "y"]],
                "correct_answers": [0],
            },
            {
                "id": "fb2",
                "type": "fill_blank",
                "blanks": [["x", "y"]],
                "correct_answers": [0],
            },
            {
                "id": "fb3",
                "type": "fill_blank",
                "blanks": [["x", "y"]],
                "correct_answers": [0],
            },
            {"id": "open1", "type": "open"},
            {"id": "open2", "type": "open"},
            {"id": "open3", "type": "open"},
        ]
        answers = {
            "mc1": {"selected_letter": "A"},
            "mc2": {"selected_letter": "B"},
            "mc3": {"selected_letter": "C"},
            "mc4": {"selected_letter": "D"},
            "fb1": {"selected_texts": ["x"]},
            "fb2": {"selected_texts": ["x"]},
            "fb3": {"selected_texts": ["x"]},
            "open1": {"text": "Essay answer"},
        }

        results = compute_results(questions, answers)
        score = _compute_score_summary(results)

        self.assertEqual(results["open1"], "open")
        self.assertEqual(results["open2"], "open")
        self.assertEqual(results["open3"], "open")
        self.assertEqual(score, {"correct": 7, "total": 7, "pct": 100})

    def test_unknown_unanswered_questions_are_not_auto_graded(self):
        results = compute_results([{"id": "q1", "type": "unknown"}], {})

        self.assertEqual(results["q1"], "unknown")
        self.assertEqual(_compute_score_summary(results)["total"], 0)

    def test_exam_banner_explains_open_questions_are_excluded(self):
        questions = [
            {"id": "mc1", "type": "mc", "correct_answer": "A", "title": "MC"},
            {"id": "open1", "type": "open", "title": "Open"},
        ]
        session = {
            "config": {"exam_title": "Demo", "api_key": ""},
            "questions": questions,
            "sections": [{"id": "s1", "name": "Section", "questions": questions}],
            "answers": {"mc1": {"selected_letter": "A"}},
            "results": {"mc1": "correct", "open1": "open"},
            "remaining_seconds": 0,
            "is_paused": False,
            "time_up": False,
            "is_submitted": True,
        }

        payload = _exam_payload_from_session(session)

        self.assertEqual(
            payload["score_banner"],
            "Score: 1/1 auto-graded questions correct - 1 open-ended not included",
        )


if __name__ == "__main__":
    unittest.main()
