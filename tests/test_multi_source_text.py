import unittest

from wisemock.core.extract import combine_source_texts


class MultiSourceTextTests(unittest.TestCase):
    def test_combines_sources_with_stable_headers(self):
        combined = combine_source_texts([
            ("/tmp/notes_a.pdf", "Alpha content"),
            ("/tmp/slides_b.docx", "Beta content\n"),
        ])
        self.assertIn("--- SOURCE FILE 1: notes_a.pdf ---", combined)
        self.assertIn("--- SOURCE FILE 2: slides_b.docx ---", combined)
        self.assertLess(combined.index("Alpha content"), combined.index("Beta content"))


if __name__ == "__main__":
    unittest.main()
