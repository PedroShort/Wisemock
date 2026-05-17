import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wisemock.core.input_loading import dedupe_paths, load_input_paths
from wisemock.workers import ExamGeneratorWorker


class InputLoadingTests(unittest.TestCase):
    def test_dedupe_paths_preserves_order(self):
        self.assertEqual(dedupe_paths(["/tmp/a.pdf", "/tmp/b.pdf", "/tmp/a.pdf"]), [
            "/tmp/a.pdf",
            "/tmp/b.pdf",
        ])

    def test_json_exam_loads_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "exam.json"
            path.write_text(json.dumps({"questions": [{"title": "Q", "type": "open"}]}))
            result = load_input_paths([str(path)])
        self.assertEqual(result["kind"], "json_exam")
        self.assertEqual(result["label"], "exam.json")

    def test_json_mixed_with_docs_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            json_path = Path(tmp) / "exam.json"
            pdf_path = Path(tmp) / "notes.pdf"
            json_path.write_text("{}")
            pdf_path.write_text("fake pdf body")
            with self.assertRaisesRegex(ValueError, "JSON exam files must be loaded alone"):
                load_input_paths([str(json_path), str(pdf_path)])

    def test_multi_document_combines_sources_and_reports_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "a.pdf"
            second = Path(tmp) / "b.docx"
            first.write_text("fake")
            second.write_text("fake")
            progress = []

            def fake_extract(path, progress=None):
                if progress:
                    progress(50, f"Halfway {Path(path).name}")
                    progress(100, f"Done {Path(path).name}")
                return f"Extracted content from {Path(path).name} " * 4

            with patch("wisemock.core.input_loading.extract_text_from_file", fake_extract):
                result = load_input_paths([str(first), str(second)], progress=lambda p, m: progress.append((p, m)))

        self.assertEqual(result["kind"], "multi_study_document")
        self.assertIn("--- SOURCE FILE 1: a.pdf ---", result["text"])
        self.assertIn("--- SOURCE FILE 2: b.docx ---", result["text"])
        self.assertEqual(progress[-1][0], 100)

    def test_generator_samples_large_documents_by_total_question_budget(self):
        chunks = [f"chunk {i}" for i in range(60)]
        selected = ExamGeneratorWorker._select_chunks_for_budget(chunks, 6)
        self.assertEqual(len(selected), 6)
        self.assertEqual(selected[0], (1, "chunk 0"))
        self.assertEqual(selected[-1], (60, "chunk 59"))

    def test_generator_samples_medium_and_large_by_total_question_budget(self):
        chunks = [f"chunk {i}" for i in range(60)]
        self.assertEqual(len(ExamGeneratorWorker._select_chunks_for_budget(chunks, 12)), 12)
        self.assertEqual(len(ExamGeneratorWorker._select_chunks_for_budget(chunks, 20)), 20)

    def test_generator_hard_caps_extra_model_output_and_reids(self):
        questions = [{"id": f"old{i}", "title": f"Q{i}"} for i in range(119)]
        capped = ExamGeneratorWorker._cap_and_reid_questions(questions, 12)
        self.assertEqual(len(capped), 12)
        self.assertEqual([q["id"] for q in capped], [f"q{i}" for i in range(1, 13)])

    def test_generator_limits_completion_budget_per_request(self):
        self.assertEqual(ExamGeneratorWorker._max_tokens_for_request(1), 700)
        self.assertLess(ExamGeneratorWorker._max_tokens_for_request(1), 2200)
        self.assertEqual(ExamGeneratorWorker._max_tokens_for_request(20), 2200)

    def test_generator_distributes_question_types_evenly(self):
        schedule = ExamGeneratorWorker._type_schedule(["mc", "open", "fill_blank"], 12)
        self.assertEqual(schedule.count("mc"), 4)
        self.assertEqual(schedule.count("open"), 4)
        self.assertEqual(schedule.count("fill_blank"), 4)

    def test_generator_type_schedule_respects_selected_types(self):
        schedule = ExamGeneratorWorker._type_schedule(["mc", "open"], 7)
        self.assertEqual(schedule, ["mc", "open", "mc", "open", "mc", "open", "mc"])
        self.assertEqual(ExamGeneratorWorker._type_plan_text(["mc", "open", "mc"]), "mc=2, open=1")

    def test_generator_difficulty_guidance_changes_by_slider_level(self):
        easy = ExamGeneratorWorker._difficulty_guidance(1)
        hard = ExamGeneratorWorker._difficulty_guidance(10)

        self.assertIn("direct recognition", easy)
        self.assertIn("multi-step reasoning", hard)
        self.assertGreater(
            ExamGeneratorWorker._temperature_for_difficulty(10),
            ExamGeneratorWorker._temperature_for_difficulty(1),
        )


if __name__ == "__main__":
    unittest.main()
