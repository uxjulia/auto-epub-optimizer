import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


PIPELINE_DIR = Path(__file__).resolve().parents[1] / 'cli' / 'epubkit_pipeline'
sys.path.insert(0, str(PIPELINE_DIR))

from epub_structure import (  # noqa: E402
    SECTION_SPLIT_BYTE_THRESHOLD,
    SECTION_SPLIT_HARD_BYTE_LIMIT,
    SECTION_SPLIT_WORD_THRESHOLD,
    split_long_sections,
)


class SectionSplitterTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix='auto_epub_split_test_'))

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_default_limits_prioritize_uncompressed_section_size(self):
        self.assertEqual(SECTION_SPLIT_WORD_THRESHOLD, 8000)
        self.assertEqual(SECTION_SPLIT_BYTE_THRESHOLD, 32768)
        self.assertEqual(SECTION_SPLIT_HARD_BYTE_LIMIT, 49152)

    def test_large_spine_section_is_split_by_uncompressed_size(self):
        opf_dir = self.tmpdir / 'OEBPS'
        opf_dir.mkdir()
        opf_path = opf_dir / 'content.opf'
        (opf_dir / 'chapter.xhtml').write_text(
            '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
            '<div class="chapter">'
            f'<p>{"a" * 12000}</p>'
            f'<div class="table"><table><tr><td>{"b" * 12000}</td></tr></table></div>'
            f'<p>{"c" * 12000}</p>'
            '</div>'
            '</body></html>',
            encoding='utf-8',
        )
        opf_path.write_text(
            textwrap.dedent(
                """
                <?xml version="1.0" encoding="utf-8"?>
                <package xmlns="http://www.idpf.org/2007/opf" version="3.0">
                  <manifest>
                    <item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>
                  </manifest>
                  <spine>
                    <itemref idref="chapter"/>
                  </spine>
                </package>
                """
            ).strip(),
            encoding='utf-8',
        )

        sections_split, split_parts = split_long_sections(str(opf_path))

        self.assertEqual(sections_split, 1)
        self.assertEqual(split_parts, 2)
        self.assertTrue((opf_dir / 'chapter__ci_section_002.xhtml').exists())
        self.assertFalse((opf_dir / 'chapter__ci_section_003.xhtml').exists())
        for name in ('chapter.xhtml', 'chapter__ci_section_002.xhtml'):
            part_path = opf_dir / name
            self.assertIn('class="chapter"', part_path.read_text(encoding='utf-8'))
            self.assertLessEqual(part_path.stat().st_size, 32768)
        self.assertIn('<table>', (opf_dir / 'chapter.xhtml').read_text(encoding='utf-8'))
        self.assertNotIn('<table>', (opf_dir / 'chapter__ci_section_002.xhtml').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
