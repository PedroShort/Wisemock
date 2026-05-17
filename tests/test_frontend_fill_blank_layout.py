import re
import unittest
from pathlib import Path


FRONTEND_HTML = (
    Path(__file__).resolve().parents[1]
    / "wisemock"
    / "assets"
    / "wisemock_frontend.html"
)


def _css_block(source, selector):
    match = re.search(rf"{re.escape(selector)}\s*\{{(?P<body>.*?)\n\s*\}}", source, re.DOTALL)
    if not match:
        raise AssertionError(f"Missing CSS block for {selector}")
    return match.group("body")


class FrontendFillBlankLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = FRONTEND_HTML.read_text(encoding="utf-8")

    def test_fill_blank_line_uses_inline_text_flow_not_flex_wrapping(self):
        line_css = _css_block(self.source, ".fill-template-line")
        self.assertIn("display: block", line_css)
        self.assertNotIn("display: flex", line_css)
        self.assertNotIn("flex-wrap", line_css)

        text_css = _css_block(self.source, ".fill-template-text")
        self.assertIn("display: inline", text_css)

        select_css = _css_block(self.source, ".fill-select")
        self.assertIn("display: inline-block", select_css)
        self.assertIn("vertical-align: middle", select_css)

    def test_fill_select_is_rendered_directly_inside_sentence(self):
        render_function = re.search(
            r"function renderFillBlank\(question, submitted\) \{(?P<body>.*?)\n    function renderOpenQuestion",
            self.source,
            re.DOTALL,
        )
        self.assertIsNotNone(render_function)
        body = render_function.group("body")
        self.assertIn('<select class="fill-select"', body)
        self.assertNotRegex(body, r"<span>\s*<select class=\"fill-select\"")


if __name__ == "__main__":
    unittest.main()
