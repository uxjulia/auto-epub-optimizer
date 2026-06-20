import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PIPELINE_DIR = PROJECT_ROOT / 'cli' / 'epubkit_pipeline'
sys.path.insert(0, str(PIPELINE_DIR))

from html_cleaner import normalize_whitespace  # noqa: E402
from metadata_handler import format_filename  # noqa: E402
from text_cleaner import TextCleanOptions, clean_text_content  # noqa: E402


class WhitespacePreservationTests(unittest.TestCase):
    def test_normalize_whitespace_keeps_space_only_leaf_elements(self):
        xhtml = (
            b'<html xmlns="http://www.w3.org/1999/xhtml">'
            b'<body><div>          </div><div></div><div></div></body></html>'
        )

        cleaned, removed = normalize_whitespace(xhtml)

        self.assertIn(b'<div>          </div>', cleaned)
        self.assertEqual(removed, 1)

    def test_clean_text_content_keeps_space_only_span_text(self):
        xhtml = (
            b'<html xmlns="http://www.w3.org/1999/xhtml">'
            b'<body><p><span class="black">          </span></p></body></html>'
        )

        cleaned, report = clean_text_content(xhtml, TextCleanOptions())

        self.assertIn(b'<span class="black">          </span>', cleaned)
        self.assertEqual(report.double_spaces_fixed, 0)

    def test_clean_text_content_still_collapses_regular_extra_spaces(self):
        xhtml = (
            b'<html xmlns="http://www.w3.org/1999/xhtml">'
            b'<body><p>Hello     world</p></body></html>'
        )

        cleaned, report = clean_text_content(xhtml, TextCleanOptions())

        self.assertIn(b'Hello world', cleaned)
        self.assertGreater(report.double_spaces_fixed, 0)

    def test_clean_text_content_keeps_curly_quotes_and_dashes_by_default(self):
        xhtml = (
            '<html xmlns="http://www.w3.org/1999/xhtml">'
            '<body><p>“Hello”—she said–quietly…</p></body></html>'
        ).encode('utf-8')

        cleaned, report = clean_text_content(xhtml, TextCleanOptions())

        self.assertIn('“Hello”—she said–quietly...', cleaned.decode('utf-8'))
        self.assertEqual(report.smart_quotes_normalized, 0)
        self.assertEqual(report.dashes_normalized, 0)
        self.assertEqual(report.ellipses_normalized, 1)

    def test_clean_text_content_can_normalize_quotes_and_dashes_separately(self):
        xhtml = (
            '<html xmlns="http://www.w3.org/1999/xhtml">'
            '<body><p>“Hello”—she said–quietly…</p></body></html>'
        ).encode('utf-8')

        cleaned, report = clean_text_content(
            xhtml,
            TextCleanOptions(normalize_quotes=True, normalize_dashes=True),
        )

        self.assertIn('"Hello"--she said-quietly...', cleaned.decode('utf-8'))
        self.assertEqual(report.smart_quotes_normalized, 2)
        self.assertEqual(report.dashes_normalized, 2)
        self.assertEqual(report.ellipses_normalized, 1)

    def test_format_filename_defaults_to_author_then_title(self):
        self.assertEqual(
            format_filename("My Book", "Jane Doe"),
            "Jane Doe - My Book.epub",
        )

    def test_format_filename_can_put_title_first(self):
        self.assertEqual(
            format_filename("My Book", "Jane Doe", "title-author"),
            "My Book - Jane Doe.epub",
        )

    def test_format_filename_can_use_title_only(self):
        self.assertEqual(
            format_filename("My Book", "Jane Doe", "title"),
            "My Book.epub",
        )


if __name__ == '__main__':
    unittest.main()
