import unittest

from wisemock.runtime.payloads import _build_full_review_prompt


class AIStudyReportPromptTests(unittest.TestCase):
    def test_full_review_prompt_labels_score_as_auto_graded(self):
        questions = [
            {"id": "q1", "type": "mc", "title": "MC", "correct_answer": "A"},
            {"id": "q2", "type": "open", "title": "Open", "suggested_answer": "Explain."},
        ]
        answers = {
            "q1": {"selected_letter": "A"},
            "q2": {"text": "Some answer"},
        }
        results = {"q1": "correct", "q2": "open"}

        prompt = _build_full_review_prompt("Demo", questions, answers, results)

        self.assertIn("Auto-graded score (MC/fill-in only): 1/1 (100%)", prompt)
        self.assertIn("Open-ended questions not included in that percentage: 1", prompt)
        self.assertIn('call this an "auto-graded score"', prompt)


if __name__ == "__main__":
    unittest.main()
