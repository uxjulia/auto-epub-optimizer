import importlib.util
from pathlib import Path
import unittest


OPTIMIZE_PATH = Path(__file__).resolve().parents[1] / 'cli' / 'optimize.py'
SPEC = importlib.util.spec_from_file_location('optimize', OPTIMIZE_PATH)
optimize = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(optimize)


class CoverColorOptionTests(unittest.TestCase):
    def test_cover_color_is_disabled_by_default(self):
        parser = optimize.build_parser()
        args = parser.parse_args(['book.epub'])
        optimize.normalize_legacy_args(parser, args)

        self.assertFalse(args.preserve_cover_color)
        self.assertFalse(optimize.build_options(args).preserve_cover_color)

    def test_preserve_cover_color_flag_enables_color_covers(self):
        parser = optimize.build_parser()
        args = parser.parse_args([
            '--preserve-cover-color', 'book.epub',
        ])
        optimize.normalize_legacy_args(parser, args)

        self.assertTrue(args.preserve_cover_color)
        self.assertTrue(optimize.build_options(args).preserve_cover_color)


if __name__ == '__main__':
    unittest.main()
