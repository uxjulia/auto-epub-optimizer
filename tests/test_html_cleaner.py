import sys
import unittest
from pathlib import Path


PIPELINE_DIR = Path(__file__).resolve().parents[1] / 'cli' / 'epubkit_pipeline'
sys.path.insert(0, str(PIPELINE_DIR))

from html_cleaner import strip_unnecessary_attributes  # noqa: E402


class HtmlCleanerTests(unittest.TestCase):
    def test_pagebreak_keeps_crossink_page_label_attributes(self):
        xhtml = (
            '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
            '<body><span aria-label="3" data-extra="x" epub:type="pagebreak" id="pg_3" '
            'role="doc-pagebreak" tabindex="0"/></body></html>'
        ).encode('utf-8')

        cleaned, removed = strip_unnecessary_attributes(xhtml)
        result = cleaned.decode('utf-8')

        self.assertEqual(removed, 2)
        self.assertIn('aria-label="3"', result)
        self.assertIn('epub:type="pagebreak"', result)
        self.assertIn('role="doc-pagebreak"', result)
        self.assertIn('id="pg_3"', result)
        self.assertNotIn('data-extra', result)
        self.assertNotIn('tabindex', result)

    def test_role_only_pagebreak_keeps_label_and_role(self):
        xhtml = (
            '<html xmlns="http://www.w3.org/1999/xhtml">'
            '<body><span aria-label="iv" id="pg_iv" role="doc-pagebreak"/></body></html>'
        ).encode('utf-8')

        cleaned, removed = strip_unnecessary_attributes(xhtml)
        result = cleaned.decode('utf-8')

        self.assertEqual(removed, 0)
        self.assertIn('aria-label="iv"', result)
        self.assertIn('role="doc-pagebreak"', result)

    def test_non_pagebreak_aria_and_role_are_still_stripped(self):
        xhtml = (
            '<html xmlns="http://www.w3.org/1999/xhtml">'
            '<body><span aria-label="decorative" id="note" role="note">Text</span></body></html>'
        ).encode('utf-8')

        cleaned, removed = strip_unnecessary_attributes(xhtml)
        result = cleaned.decode('utf-8')

        self.assertEqual(removed, 2)
        self.assertIn('id="note"', result)
        self.assertNotIn('aria-label', result)
        self.assertNotIn('role="note"', result)


if __name__ == '__main__':
    unittest.main()
