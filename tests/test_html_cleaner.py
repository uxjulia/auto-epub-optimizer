import sys
import unittest
from pathlib import Path


PIPELINE_DIR = Path(__file__).resolve().parents[1] / 'cli' / 'epubkit_pipeline'
sys.path.insert(0, str(PIPELINE_DIR))

from html_cleaner import remove_oceanofpdf_containers, strip_unnecessary_attributes  # noqa: E402


class HtmlCleanerTests(unittest.TestCase):
    def test_removes_outermost_oceanofpdf_wrapper(self):
        xhtml = (
            '<html xmlns="http://www.w3.org/1999/xhtml"><body><p>Chapter text</p>'
            '<div style="text-align: center"><p><a href="https://oceanofpdf.com">'
            '<i>OceanofPDF.com</i></a></p></div></body></html>'
        ).encode('utf-8')

        cleaned, removed = remove_oceanofpdf_containers(xhtml)
        result = cleaned.decode('utf-8')

        self.assertEqual(removed, 1)
        self.assertIn('Chapter text', result)
        self.assertNotIn('OceanofPDF', result)
        self.assertNotIn('text-align: center', result)

    def test_removes_nearest_block_for_oceanofpdf_url_with_custom_link_text(self):
        xhtml = (
            '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
            '<p><a href="https://www.oceanofpdf.com/books">Download here</a></p>'
            '<p>Keep this chapter text.</p></body></html>'
        ).encode('utf-8')

        cleaned, removed = remove_oceanofpdf_containers(xhtml)
        result = cleaned.decode('utf-8')

        self.assertEqual(removed, 1)
        self.assertNotIn('Download here', result)
        self.assertIn('Keep this chapter text.', result)

    def test_does_not_remove_oceanofpdf_words_inside_chapter_text(self):
        xhtml = (
            '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
            '<p>The ocean of PDF files was only a metaphor.</p></body></html>'
        ).encode('utf-8')

        cleaned, removed = remove_oceanofpdf_containers(xhtml)

        self.assertEqual(removed, 0)
        self.assertIn(b'The ocean of PDF files was only a metaphor.', cleaned)

    def test_removes_footer_without_removing_image_only_cover_page(self):
        xhtml = (
            '<html xmlns="http://www.w3.org/1999/xhtml"><body><div id="Cover">'
            '<img alt="Book cover" src="../images/cover.jpg"/></div>'
            '<div><p><a href="https://oceanofpdf.com"><i>OceanofPDF.com</i></a></p></div>'
            '</body></html>'
        ).encode('utf-8')

        cleaned, removed = remove_oceanofpdf_containers(xhtml)

        self.assertEqual(removed, 1)
        self.assertIn(b'<img', cleaned)
        self.assertIn(b'../images/cover.jpg', cleaned)
        self.assertNotIn(b'OceanofPDF', cleaned)

    def test_keeps_cover_image_wrapped_in_oceanofpdf_link(self):
        xhtml = (
            '<html xmlns="http://www.w3.org/1999/xhtml"><body><div>'
            '<a href="https://oceanofpdf.com"><img src="cover.jpg"/></a>'
            '</div></body></html>'
        ).encode('utf-8')

        cleaned, removed = remove_oceanofpdf_containers(xhtml)

        self.assertEqual(removed, 0)
        self.assertIn(b'<img', cleaned)
        self.assertIn(b'cover.jpg', cleaned)

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
