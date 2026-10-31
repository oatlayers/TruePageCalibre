"""Tests that need a working Calibre installation.

Run them with the Python that ships with Calibre, for example::

    "C:\\Program Files\\Calibre2\\calibre-debug.exe" -e run_tests.py

They are skipped automatically when Calibre cannot be imported, so the plain
unit tests still work with any Python 3.
"""

import math
import os
import shutil
import sys
import tempfile
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TESTS_DIR)

import _support  # noqa: E402,F401  (adds plugin/ to sys.path)

import core  # noqa: E402

try:
    from calibre.ebooks.oeb.polish.container import get_container  # noqa: F401
    HAVE_CALIBRE = True
except Exception:  # pragma: no cover - depends on the environment
    HAVE_CALIBRE = False


@unittest.skipUnless(HAVE_CALIBRE, 'Calibre is not importable')
class EpubCountingTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from epub_fixtures import build_fixtures
        cls.directory = tempfile.mkdtemp(prefix='apc-fixtures-')
        build_fixtures(cls.directory)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.directory, ignore_errors=True)

    def count(self, name, **kwargs):
        path = os.path.join(self.directory, name)
        return core.count_epub(path, '', core.DEFAULT_SETTINGS)

    def test_plain_book_is_estimated(self):
        result = self.count('plain.epub')
        self.assertEqual(result['source'], 'estimate-eng')
        self.assertEqual(result['language'], 'eng')
        self.assertEqual(result['pages'], 23)

    def test_korean_book_uses_korean_estimate(self):
        result = self.count('korean.epub')
        self.assertEqual(result['source'], 'estimate-kor')
        self.assertEqual(result['language'], 'kor')
        self.assertEqual(result['pages'], 80)

    def test_nav_page_list_is_used(self):
        result = self.count('pagelist.epub')
        self.assertEqual(result['source'], 'print-page-list')
        self.assertEqual(result['pages'], 30)

    def test_ncx_page_map_is_used(self):
        result = self.count('ncx_pagemap.epub')
        self.assertEqual(result['source'], 'print-page-map')
        self.assertEqual(result['pages'], 40)

    def test_pagebreak_markers_are_used(self):
        result = self.count('pagebreak.epub')
        self.assertEqual(result['source'], 'print-pagebreak')
        self.assertEqual(result['pages'], 30)

    def test_calibre_anchors_are_ignored(self):
        result = self.count('calibre_pb.epub')
        self.assertTrue(result['source'].startswith('estimate-'))

    def test_fixed_layout_book_has_one_page_per_spine_item(self):
        for name in ('fixed.epub', 'fixed_rendition.epub'):
            result = self.count(name)
            self.assertEqual(result['source'], 'fixed-layout', name)
            self.assertEqual(result['pages'], 2, name)

    def test_short_page_list_is_not_trusted(self):
        result = self.count('truncated_pagelist.epub')
        self.assertTrue(result['source'].startswith('estimate-'))
        self.assertEqual(result['pages'], 230)

    def test_sparse_page_list_uses_the_highest_page_number(self):
        result = self.count('sparse_pagelist.epub')
        self.assertEqual(result['source'], 'print-page-list')
        self.assertEqual(result['pages'], 390)

    def test_print_pagination_can_be_disabled(self):
        settings = dict(core.DEFAULT_SETTINGS)
        settings['prefer_print_pages'] = False
        path = os.path.join(self.directory, 'pagelist.epub')
        result = core.count_epub(path, '', settings)
        self.assertTrue(result['source'].startswith('estimate-'))

    def test_adobe_page_map_is_used(self):
        result = self.count('pagemap.epub')
        self.assertEqual(result['source'], 'print-page-map-adobe')
        self.assertEqual(result['pages'], 25)

    def test_adobe_map_wins_when_it_agrees_with_pagebreaks(self):
        result = self.count('pagemap_agree.epub')
        self.assertEqual(result['source'], 'print-page-map-adobe')
        self.assertEqual(result['pages'], 32)

    def test_pagebreaks_win_over_a_different_editions_adobe_map(self):
        result = self.count('pagemap_conflict.epub')
        self.assertEqual(result['source'], 'print-pagebreak')
        self.assertEqual(result['pages'], 30)

    def test_nav_fragment_labels_are_used(self):
        # The link text is "navpoint-20"; the page number is in the fragment.
        result = self.count('navfrag.epub')
        self.assertEqual(result['source'], 'print-page-list')
        self.assertEqual(result['pages'], 20)

    def test_roman_front_matter_is_included(self):
        result = self.count('roman.epub')
        self.assertEqual(result['source'], 'print-page-list')
        self.assertEqual(result['pages'], 24)
        settings = dict(core.DEFAULT_SETTINGS)
        settings['include_front_matter'] = False
        path = os.path.join(self.directory, 'roman.epub')
        self.assertEqual(core.count_epub(path, '', settings)['pages'], 20)

    def test_ruby_annotations_are_not_counted(self):
        ruby = self.count('ruby.epub')
        plain = self.count('no_ruby.epub')
        self.assertEqual(ruby['chars'], plain['chars'])

    def test_mixed_language_uses_per_script_estimate(self):
        result = self.count('mixed.epub')
        self.assertEqual(result['language'], 'kor')
        self.assertEqual(result['source'], 'estimate-kor')
        flat = int(math.ceil(result['chars'] / 300.0))
        self.assertLess(result['pages'], flat)

    def test_unknown_language_tag_is_detected_from_text(self):
        result = self.count('und_language.epub')
        self.assertEqual(result['language'], 'kor')
        self.assertEqual(result['source'], 'estimate-kor')

    def test_calibration_is_applied_to_estimates(self):
        settings = dict(core.DEFAULT_SETTINGS)
        settings['calibration'] = {
            'eng': {'kind': 'median', 'cpp': 750.0, 'n': 10, 'mape': 0.1},
        }
        path = os.path.join(self.directory, 'plain.epub')
        calibrated = core.count_epub(path, '', settings)
        flat = core.count_epub(path, '', core.DEFAULT_SETTINGS)
        self.assertTrue(calibrated['calibrated'])
        self.assertGreater(calibrated['pages'], flat['pages'] * 1.5)

    def test_calibration_can_be_disabled(self):
        settings = dict(core.DEFAULT_SETTINGS)
        settings['calibration'] = {
            'eng': {'kind': 'median', 'cpp': 750.0, 'n': 10, 'mape': 0.1},
        }
        settings['calibrate_estimates'] = False
        path = os.path.join(self.directory, 'plain.epub')
        result = core.count_epub(path, '', settings)
        self.assertFalse(result['calibrated'])

    def test_calibration_does_not_change_embedded_counts(self):
        settings = dict(core.DEFAULT_SETTINGS)
        settings['calibration'] = {
            'eng': {'kind': 'median', 'cpp': 750.0, 'n': 10, 'mape': 0.1},
        }
        path = os.path.join(self.directory, 'pagelist.epub')
        result = core.count_epub(path, '', settings)
        self.assertEqual(result['source'], 'print-page-list')
        self.assertEqual(result['pages'], 30)


if __name__ == '__main__':
    unittest.main()
