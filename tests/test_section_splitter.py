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
            '<p>one two three four</p>'
            '<p>five six seven eight</p>'
            '<p>nine ten eleven twelve</p>'
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

        sections_split, split_parts = split_long_sections(
            str(opf_path),
            word_threshold=50000,
            byte_threshold=40,
            hard_byte_limit=1024 * 1024,
        )

        self.assertEqual(sections_split, 1)
        self.assertEqual(split_parts, 3)
        self.assertTrue((opf_dir / 'chapter__ci_section_002.xhtml').exists())
        self.assertTrue((opf_dir / 'chapter__ci_section_003.xhtml').exists())


if __name__ == '__main__':
    unittest.main()
