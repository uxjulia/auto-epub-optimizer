import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PIPELINE_DIR = PROJECT_ROOT / 'cli' / 'epubkit_pipeline'
sys.path.insert(0, str(PIPELINE_DIR))

from epub_processor import ProcessingOptions, process_epub  # noqa: E402


class SectionSplitterTests(unittest.TestCase):
    def test_process_epub_splits_long_spine_item_and_rewrites_moved_anchor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / 'input.epub'
            output_path = root / 'output.epub'
            self._write_fixture(input_path)

            report = process_epub(
                str(input_path),
                str(output_path),
                ProcessingOptions(
                    remove_fonts=False,
                    remove_unused_css=False,
                    generate_missing_cover=False,
                    clean_metadata=False,
                    text_cleanup=False,
                    split_long_sections=True,
                    section_split_word_threshold=500,
                ),
            )

            self.assertTrue(report.success, report.error)
            self.assertEqual(report.sections_split, 1)
            self.assertGreaterEqual(report.synthetic_sections_added, 1)

            with zipfile.ZipFile(output_path) as zf:
                names = set(zf.namelist())
                self.assertIn('OEBPS/chapter.xhtml', names)
                split_names = sorted(name for name in names if name.startswith('OEBPS/chapter__ci_section_'))
                self.assertTrue(split_names)

                opf = ET.fromstring(zf.read('OEBPS/content.opf'))
                ns = {'opf': 'http://www.idpf.org/2007/opf'}
                id_to_href = {
                    item.attrib['id']: item.attrib['href']
                    for item in opf.findall('.//opf:item', ns)
                    if 'id' in item.attrib and 'href' in item.attrib
                }
                spine_hrefs = [
                    id_to_href[itemref.attrib['idref']]
                    for itemref in opf.findall('.//opf:itemref', ns)
                ]
                self.assertEqual(spine_hrefs[0], 'chapter.xhtml')
                self.assertIn('chapter__ci_section_2.xhtml', spine_hrefs)

                first_part = zf.read('OEBPS/chapter.xhtml').decode('utf-8')
                self.assertIn('href="chapter__ci_section_', first_part)
                self.assertIn('#late-anchor"', first_part)

                ncx = zf.read('OEBPS/toc.ncx').decode('utf-8')
                self.assertIn('chapter.xhtml', ncx)
                self.assertNotIn('chapter__ci_section_2.xhtml', ncx)

    def _write_fixture(self, path: Path):
        paragraphs = [
            '<p><a href="#late-anchor">Jump late</a> Start.</p>',
            *[f'<p>{"word " * 80}{i}</p>' for i in range(16)],
            '<p id="late-anchor">Late target.</p>',
        ]
        chapter = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<html xmlns="http://www.w3.org/1999/xhtml">'
            '<head><title>Long Chapter</title></head>'
            f'<body>{"".join(paragraphs)}</body></html>'
        )
        opf = '''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="BookId" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="BookId">fixture</dc:identifier>
    <dc:title>Fixture</dc:title>
  </metadata>
  <manifest>
    <item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
  </manifest>
  <spine toc="ncx">
    <itemref idref="chapter"/>
  </spine>
</package>'''
        ncx = '''<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="fixture"/></head>
  <docTitle><text>Fixture</text></docTitle>
  <navMap>
    <navPoint id="navPoint-1" playOrder="1">
      <navLabel><text>Long Chapter</text></navLabel>
      <content src="chapter.xhtml"/>
    </navPoint>
  </navMap>
</ncx>'''
        container = '''<?xml version="1.0" encoding="utf-8"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>'''

        with zipfile.ZipFile(path, 'w') as zf:
            zf.writestr('mimetype', 'application/epub+zip', compress_type=zipfile.ZIP_STORED)
            zf.writestr('META-INF/container.xml', container)
            zf.writestr('OEBPS/content.opf', opf)
            zf.writestr('OEBPS/toc.ncx', ncx)
            zf.writestr('OEBPS/chapter.xhtml', chapter)


if __name__ == '__main__':
    unittest.main()
