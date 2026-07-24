import json
import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


PIPELINE_DIR = Path(__file__).resolve().parents[1] / 'cli' / 'epubkit_pipeline'
sys.path.insert(0, str(PIPELINE_DIR))

from epub_structure import (  # noqa: E402
    collapse_reader_empty_spine_items,
    SECTION_SPLIT_BYTE_THRESHOLD,
    SECTION_SPLIT_HARD_BYTE_LIMIT,
    SECTION_SPLIT_WORD_THRESHOLD,
    split_long_sections,
    write_crossink_location_manifest,
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
        (opf_dir / 'cover.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding='utf-8')
        opf_path.write_text(
            textwrap.dedent(
                """
                <?xml version="1.0" encoding="utf-8"?>
                <package xmlns="http://www.idpf.org/2007/opf" version="3.0">
                  <manifest>
                    <item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>
                    <item id="cover" href="cover.svg" media-type="image/svg+xml"/>
                  </manifest>
                  <spine>
                    <itemref idref="chapter"/>
                    <itemref idref="cover"/>
                  </spine>
                </package>
                """
            ).strip(),
            encoding='utf-8',
        )

        source_spine_map = {}
        sections_split, split_parts = split_long_sections(str(opf_path), source_spine_map=source_spine_map)

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
        write_crossink_location_manifest(str(self.tmpdir), str(opf_path), source_spine_map=source_spine_map)
        manifest = json.loads(
            (self.tmpdir / 'META-INF' / 'x-locations.json').read_text(encoding='utf-8')
        )
        self.assertEqual(manifest['sourceSpineMap']['spineCount'], 2)
        self.assertEqual([entry['sourceSpineIndex'] for entry in manifest['sourceSpineMap']['spine']], [0, 0, 1])
        self.assertEqual(manifest['sourceSpineMap']['spine'][1]['containerDepth'], 1)

    def test_collapses_kindles_decorative_empty_spine_stub_and_rewrites_ncx(self):
        opf_dir = self.tmpdir / 'OEBPS'
        text_dir = opf_dir / 'text'
        text_dir.mkdir(parents=True)
        opf_path = opf_dir / 'content.opf'
        (text_dir / 'chapter_split_000.xhtml').write_text(
            '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Chapter 1</title></head>'
            '<body id="chapter-1"><div data-AmznRemoved-M8="true"><img src="old.gif"/></div></body></html>',
            encoding='utf-8',
        )
        (text_dir / 'chapter_split_001.xhtml').write_text(
            '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Chapter 1</title></head>'
            '<body id="chapter-1"><h1>Chapter 1</h1><p>Readable chapter text.</p></body></html>',
            encoding='utf-8',
        )
        (opf_dir / 'toc.ncx').write_text(
            '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/"><navMap><navPoint>'
            '<content src="text/chapter_split_000.xhtml#chapter-1"/></navPoint></navMap></ncx>',
            encoding='utf-8',
        )
        opf_path.write_text(
            '<package xmlns="http://www.idpf.org/2007/opf" version="2.0"><manifest>'
            '<item id="stub" href="text/chapter_split_000.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="chapter" href="text/chapter_split_001.xhtml" media-type="application/xhtml+xml"/>'
            '</manifest><spine><itemref idref="stub"/><itemref idref="chapter"/></spine></package>',
            encoding='utf-8',
        )

        self.assertEqual(collapse_reader_empty_spine_items(str(opf_path)), 1)
        self.assertNotIn('<itemref idref="stub"', opf_path.read_text(encoding='utf-8'))
        self.assertIn('text/chapter_split_001.xhtml#chapter-1', (opf_dir / 'toc.ncx').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
