import unittest

from wisemock.workers import ExamGeneratorWorker


class ExamGenerationSizeTests(unittest.TestCase):
    def _worker(self, size, custom=None):
        return ExamGeneratorWorker(
            api_key="test",
            text="study material",
            difficulty=5,
            size=size,
            q_types=["mc", "open", "fill_blank"],
            source_name="source",
            custom_question_count=custom,
        )

    def test_presets_are_total_exam_budgets(self):
        self.assertEqual(self._worker("small")._target_questions(), 10)
        self.assertEqual(self._worker("medium")._target_questions(), 20)
        self.assertEqual(self._worker("large")._target_questions(), 30)

    def test_custom_question_count_is_clamped(self):
        self.assertEqual(self._worker("custom", 24)._target_questions(), 24)
        self.assertEqual(self._worker("custom", 119)._target_questions(), 119)
        self.assertEqual(self._worker("custom", 0)._target_questions(), 1)
        self.assertEqual(self._worker("custom", 999)._target_questions(), 200)


if __name__ == "__main__":
    unittest.main()
