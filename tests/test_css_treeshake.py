import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


PIPELINE_DIR = Path(__file__).resolve().parents[1] / 'cli' / 'epubkit_pipeline'
sys.path.insert(0, str(PIPELINE_DIR))

from epub_processor import _tree_shake_css  # noqa: E402
from html_cleaner import remove_unused_css  # noqa: E402


class CssTreeShakeTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix='css_treeshake_test_'))
        (self.tmpdir / 'OEBPS' / 'Text').mkdir(parents=True)
        (self.tmpdir / 'OEBPS' / 'Styles').mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_compound_selectors_require_class_or_id_match(self):
        css = textwrap.dedent(
            """
            p { margin: 0; }
            p.used { text-indent: 1em; }
            p.unused { color: red; }
            #missing { color: blue; }
            [type="toc"] { display: block; }
            """
        )

        cleaned, removed = remove_unused_css(css, {'used'}, set(), {'p'})

        self.assertEqual(removed, 2)
        self.assertIn('p.used', cleaned)
        self.assertIn('p {', cleaned)
        self.assertIn('[type="toc"]', cleaned)
        self.assertNotIn('p.unused', cleaned)
        self.assertNotIn('#missing', cleaned)

    def test_tree_shake_removes_dead_rules_and_empty_stylesheets(self):
        opf_path = self.tmpdir / 'OEBPS' / 'content.opf'
        chapter_path = self.tmpdir / 'OEBPS' / 'Text' / 'chapter.xhtml'
        live_css = self.tmpdir / 'OEBPS' / 'Styles' / 'live.css'
        dead_css = self.tmpdir / 'OEBPS' / 'Styles' / 'dead.css'
        orphan_css = self.tmpdir / 'OEBPS' / 'Styles' / 'orphan.css'

        opf_path.write_text(
            textwrap.dedent(
                """
                <?xml version="1.0" encoding="utf-8"?>
                <package xmlns="http://www.idpf.org/2007/opf" version="3.0">
                  <manifest>
                    <item id="chapter" href="Text/chapter.xhtml" media-type="application/xhtml+xml"/>
                    <item id="live" href="Styles/live.css" media-type="text/css"/>
                    <item id="dead" href="Styles/dead.css" media-type="text/css"/>
                    <item id="orphan" href="Styles/orphan.css" media-type="text/css"/>
                  </manifest>
                  <spine>
                    <itemref idref="chapter"/>
                  </spine>
                </package>
                """
            ).strip(),
            encoding='utf-8',
        )
        chapter_path.write_text(
            textwrap.dedent(
                """
                <html xmlns="http://www.w3.org/1999/xhtml">
                  <head>
                    <link rel="stylesheet" type="text/css" href="../Styles/live.css"/>
                    <link rel="stylesheet" type="text/css" href="../Styles/dead.css"/>
                  </head>
                  <body>
                    <p class="used">Hello</p>
                  </body>
                </html>
                """
            ).strip(),
            encoding='utf-8',
        )
        live_css.write_text(
            'p { margin: 0; } p.used { text-indent: 1em; } p.unused { color: red; }',
            encoding='utf-8',
        )
        dead_css.write_text('.missing { color: red; }', encoding='utf-8')
        orphan_css.write_text('p { color: blue; }', encoding='utf-8')

        rules_removed, files_removed = _tree_shake_css(
            {
                'xhtml': [str(chapter_path)],
                'css': [str(live_css), str(dead_css), str(orphan_css)],
            },
            str(opf_path),
        )

        self.assertEqual(rules_removed, 2)
        self.assertEqual(files_removed, 2)
        self.assertTrue(live_css.exists())
        self.assertFalse(dead_css.exists())
        self.assertFalse(orphan_css.exists())

        chapter = chapter_path.read_text(encoding='utf-8')
        self.assertIn('../Styles/live.css', chapter)
        self.assertNotIn('../Styles/dead.css', chapter)

        opf = opf_path.read_text(encoding='utf-8')
        self.assertIn('Styles/live.css', opf)
        self.assertNotIn('Styles/dead.css', opf)
        self.assertNotIn('Styles/orphan.css', opf)


if __name__ == '__main__':
    unittest.main()
