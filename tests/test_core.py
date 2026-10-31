import unittest
import xml.etree.ElementTree as ET

import _support  # noqa: F401  (adds plugin/ to sys.path)

import core


class LanguageTests(unittest.TestCase):

    def test_normalize_language(self):
        self.assertEqual(core.normalize_language('ko'), 'kor')
        self.assertEqual(core.normalize_language('ko-KR'), 'kor')
        self.assertEqual(core.normalize_language('kor'), 'kor')
        self.assertEqual(core.normalize_language('en-US'), 'eng')
        self.assertEqual(core.normalize_language('zh_Hant'), 'zho')
        self.assertEqual(core.normalize_language(''), '')

    def test_unknown_languages_are_empty(self):
        for value in ('und', 'zxx', 'mul', 'unknown', 'n/a', '--'):
            self.assertEqual(core.normalize_language(value), '', value)

    def test_normalize_language_with_several_languages(self):
        self.assertEqual(core.normalize_language('eng,fra'), 'eng')
        self.assertEqual(core.normalize_language('kor,eng'), 'kor')

    def test_detect_korean(self):
        text = '그녀는 아무 말도 하지 않았다. ' * 20 + 'He said nothing. '
        self.assertEqual(core.detect_language(text), 'kor')

    def test_detect_english(self):
        text = 'The quick brown fox jumps over the lazy dog. ' * 20
        self.assertEqual(core.detect_language(text), 'eng')

    def test_empty_text_uses_fallback(self):
        self.assertEqual(core.detect_language('', 'kor'), 'kor')
        self.assertEqual(core.detect_language(''), 'eng')

    def test_script_overrides_wrong_metadata(self):
        korean = core.text_profile('그녀는 아무 말도 하지 않았다. ' * 20)
        self.assertEqual(core.choose_language('eng', korean), 'kor')
        english = core.text_profile('The quick brown fox. ' * 20)
        self.assertEqual(core.choose_language('kor', english), 'eng')

    def test_hanja_does_not_override_korean_metadata(self):
        profile = core.text_profile('漢字 ' * 20 + '한국어 ')
        self.assertEqual(core.choose_language('kor', profile), 'kor')


class CountingTests(unittest.TestCase):

    def test_visible_chars_ignores_whitespace_and_controls(self):
        self.assertEqual(core.count_visible_chars('a b\nc\t\u200b'), 3)
        self.assertEqual(core.count_visible_chars('한 글'), 2)

    def test_visible_chars_ignores_format_characters(self):
        # Zero width joiner and soft hyphen are format characters
        self.assertEqual(core.count_visible_chars('a\u200db\u00adc'), 3)

    def test_visible_chars_handles_a_large_text(self):
        text = ('lorem ipsum dolor sit amet ' * 10000)
        self.assertEqual(core.count_visible_chars(text), 22 * 10000)

    def test_text_profile_splits_scripts(self):
        profile = core.text_profile('한글 abc 123!')
        self.assertEqual(profile['chars'], 9)
        self.assertEqual(profile['hangul'], 2)
        self.assertEqual(profile['latin'], 3)
        self.assertEqual(profile['neutral'], 4)

    def test_normalize_page_label(self):
        self.assertEqual(core.normalize_page_label('page_012'), '12')
        self.assertEqual(core.normalize_page_label('Page 7'), '7')
        self.assertEqual(core.normalize_page_label('p. 42'), '42')
        self.assertEqual(core.normalize_page_label('page_v'), 'v')
        self.assertEqual(core.normalize_page_label('pagebreak'), 'break')
        self.assertEqual(core.normalize_page_label(''), '')

    def test_roman_to_int(self):
        self.assertEqual(core.roman_to_int('i'), 1)
        self.assertEqual(core.roman_to_int('iv'), 4)
        self.assertEqual(core.roman_to_int('xii'), 12)
        self.assertEqual(core.roman_to_int('xix'), 19)
        self.assertEqual(core.roman_to_int('abc'), 0)
        self.assertEqual(core.roman_to_int(''), 0)

    def test_label_page_number(self):
        self.assertEqual(core.label_page_number('page_12'), (12, 0))
        self.assertEqual(core.label_page_number('page_xii'), (0, 12))
        self.assertEqual(core.label_page_number('navpoint-28'), (0, 0))

    def test_fragment_page_number(self):
        self.assertEqual(core._fragment_page_number('p42'), 42)
        self.assertEqual(core._fragment_page_number('page_12'), 12)
        self.assertEqual(core._fragment_page_number('42'), 42)
        self.assertEqual(core._fragment_page_number('GBS.0003.05'), 0)
        self.assertEqual(core._fragment_page_number(''), 0)

    def test_pagebreak_label_prefers_a_numeric_attribute(self):
        marker = ET.fromstring(
            '<span xmlns:epub="http://www.idpf.org/2007/ops" epub:type="pagebreak" '
            'aria-label="chapter start" title="12" id="page_12"/>')
        self.assertEqual(core._pagebreak_label(marker), '12')

    def test_pagebreak_label_uses_the_element_text(self):
        marker = ET.fromstring(
            '<span xmlns:epub="http://www.idpf.org/2007/ops" '
            'epub:type="pagebreak">42</span>')
        self.assertEqual(core._pagebreak_label(marker), '42')

    def test_pagebreak_count_uses_the_highest_page_number(self):
        # Two markers per page (start and end) still count one page each.
        labels = [(str(i), True) for i in range(1, 13)]
        self.assertEqual(core._pagebreak_count(labels, core.DEFAULT_SETTINGS), 12)

    def test_pagebreak_count_ignores_generic_labels(self):
        labels = [('calibre_pb_0', False)]
        self.assertEqual(core._pagebreak_count(labels, core.DEFAULT_SETTINGS), 0)

    def test_pagebreak_count_ignores_unlabelled_markers(self):
        self.assertEqual(core._pagebreak_count([], core.DEFAULT_SETTINGS), 0)

    def test_pagebreak_count_rejects_sparse_class_only_markers(self):
        labels = [(str(i), False) for i in range(1, 316, 35)]
        self.assertEqual(core._pagebreak_count(labels, core.DEFAULT_SETTINGS), 0)

    def test_pagebreak_count_trusts_sparse_epub_markers(self):
        labels = [(str(i), True) for i in range(1, 317, 35)]
        self.assertEqual(core._pagebreak_count(labels, core.DEFAULT_SETTINGS), 316)

    def test_pagebreak_count_detects_chapter_restarts(self):
        labels = []
        for _chapter in range(4):
            labels.extend((str(i), True) for i in range(1, 21))
        self.assertEqual(core._pagebreak_count(labels, core.DEFAULT_SETTINGS), 80)

    def test_pagebreak_count_adds_roman_front_matter(self):
        labels = [(str(i), True) for i in range(1, 11)]
        labels.extend((roman, True) for roman in ('i', 'ii', 'iii', 'iv', 'v'))
        self.assertEqual(core._pagebreak_count(labels, core.DEFAULT_SETTINGS), 15)

    def test_estimate_korean(self):
        # 75,872 characters at 300 chars/page = 253 pages
        pages, source = core.estimate_pages(75872, 'kor', core.DEFAULT_SETTINGS)
        self.assertEqual(pages, 253)
        self.assertEqual(source, 'estimate-kor')

    def test_estimate_english(self):
        pages, source = core.estimate_pages(750000, 'eng', core.DEFAULT_SETTINGS)
        self.assertEqual(pages, 500)
        self.assertEqual(source, 'estimate-eng')

    def test_estimate_cjk(self):
        pages, source = core.estimate_pages(1400, 'jpn', core.DEFAULT_SETTINGS)
        self.assertEqual(pages, 2)
        self.assertEqual(source, 'estimate-cjk')

    def test_mixed_script_estimate_uses_each_language_value(self):
        profile = core._empty_profile()
        profile.update(chars=121000, hangul=78000, latin=42000, neutral=1000)
        settings = dict(core.DEFAULT_SETTINGS)
        settings['chars_per_page_korean'] = 390
        pages, _source, _calibrated = core.estimate_from_profile(
            profile, 'kor', settings)
        # 78,650 / 390 + 42,350 / 1500 = 229.9 -> 230
        self.assertEqual(pages, 230)

    def test_settings_merge(self):
        settings = core.settings_from_prefs({'chars_per_page_korean': '400'})
        self.assertEqual(settings['chars_per_page_korean'], 400)
        self.assertEqual(settings['chars_per_page_english'], 1500)
        self.assertTrue(settings['prefer_print_pages'])
        self.assertTrue(settings['include_front_matter'])
        self.assertTrue(settings['calibrate_estimates'])

    def test_settings_invalid_value_falls_back(self):
        settings = core.settings_from_prefs({'chars_per_page_korean': 'nope'})
        self.assertEqual(settings['chars_per_page_korean'], 300)


class EmbeddedPaginationTests(unittest.TestCase):

    def values(self, arabic, roman=()):
        return {'arabic': {n: ('doc', '') for n in arabic},
                'roman': {n: ('doc', '') for n in roman},
                'entries': len(arabic) + len(roman)}

    def test_page_values_use_the_highest_page_number(self):
        data = self.values(range(10, 400, 10))
        self.assertEqual(core._page_count_from_values(data, core.DEFAULT_SETTINGS), 390)

    def test_page_values_add_roman_front_matter(self):
        data = self.values(range(1, 301), range(1, 29))
        self.assertEqual(core._page_count_from_values(data, core.DEFAULT_SETTINGS), 328)

    def test_front_matter_can_be_disabled(self):
        settings = dict(core.DEFAULT_SETTINGS)
        settings['include_front_matter'] = False
        data = self.values(range(1, 301), range(1, 29))
        self.assertEqual(core._page_count_from_values(data, settings), 300)

    def test_page_values_without_roman_front_matter(self):
        data = self.values(range(18, 433))
        self.assertEqual(core._page_count_from_values(data, core.DEFAULT_SETTINGS), 432)

    def test_front_matter_is_added_even_when_arabic_list_starts_late(self):
        # A page map can omit the first arabic pages, but the roman front
        # matter is still real.
        data = self.values(range(3, 125), range(1, 56))
        self.assertEqual(core._page_count_from_values(data, core.DEFAULT_SETTINGS), 179)

    def test_page_values_respect_the_minimum(self):
        data = self.values({1, 2})
        self.assertEqual(core._page_count_from_values(data, core.DEFAULT_SETTINGS), 0)

    def test_sparse_page_values_are_trusted(self):
        data = self.values(range(10, 400, 10))
        self.assertEqual(core._page_count_from_values(data, core.DEFAULT_SETTINGS), 390)


class CalibrationTests(unittest.TestCase):

    def make_power_pairs(self, count=40):
        pairs = []
        for index in range(count):
            chars = 50000 + index * 25000
            cpp = 1500.0 * (chars / 300000.0) ** 0.4
            pairs.append((chars, chars / cpp))
        return pairs

    def test_fit_power_law(self):
        models = core.fit_calibration({'eng': self.make_power_pairs()})
        self.assertIn('eng', models)
        model = models['eng']
        self.assertEqual(model['kind'], 'power')
        self.assertAlmostEqual(model['b'], 0.4, places=3)
        self.assertEqual(model['n'], 40)
        self.assertLess(model['mape'], 0.01)

    def test_small_sample_uses_median_cpp(self):
        pairs = [(100000 + i * 10000, (100000 + i * 10000) / 1000.0)
                 for i in range(10)]
        models = core.fit_calibration({'kor': pairs})
        self.assertEqual(models['kor']['kind'], 'median')
        self.assertAlmostEqual(models['kor']['cpp'], 1000.0, delta=1)

    def test_calibration_samples_only_use_embedded_pagination(self):
        results = {
            1: {'source': 'print-page-list', 'pages': 300, 'chars': 300000,
                'language': 'eng'},
            2: {'source': 'print-pagebreak', 'pages': 200, 'chars': 200000,
                'language': 'eng'},
            3: {'source': 'estimate-eng', 'pages': 100, 'chars': 100000,
                'language': 'eng'},
            4: {'source': 'print-page-map-adobe', 'pages': 150, 'chars': 150000,
                'language': 'kor'},
        }
        samples = core.calibration_samples(results)
        self.assertEqual(samples, {'eng': [(300000, 300)],
                                   'kor': [(150000, 150)]})

    def test_too_few_samples_are_ignored(self):
        self.assertEqual(core.fit_calibration({'kor': [(100000, 300)] * 5}), {})

    def test_normalize_calibration_rejects_invalid_models(self):
        models = core.normalize_calibration({
            'eng': {'kind': 'power', 'a': 2.0, 'b': 0.4},
            'bad': {'kind': 'power', 'a': 2.0, 'b': 5.0},
            'bad2': {'kind': 'median', 'cpp': 1},
        })
        self.assertIn('eng', models)
        self.assertNotIn('bad', models)
        self.assertNotIn('bad2', models)

    def test_recalibrate_estimates(self):
        results = {
            1: {'source': 'estimate-eng', 'language': 'eng', 'chars': 100000,
                'latin': 100000, 'hangul': 0, 'cjk': 0, 'other': 0,
                'neutral': 0, 'pages': 67},
            2: {'source': 'print-page-list', 'language': 'eng', 'chars': 100000,
                'pages': 300},
        }
        models = {'eng': {'kind': 'median', 'cpp': 1000.0}}
        changed = core.recalibrate_results(results, models, core.DEFAULT_SETTINGS)
        self.assertEqual(changed, 1)
        self.assertEqual(results[1]['pages'], 100)
        self.assertTrue(results[1]['calibrated'])
        self.assertEqual(results[2]['pages'], 300)
        self.assertNotIn('calibrated', results[2])

    def test_calibration_summary(self):
        summary = core.calibration_summary({
            'eng': {'kind': 'power', 'n': 273, 'mape': 0.117},
            'kor': {'kind': 'median', 'n': 10, 'mape': 0.1},
        })
        self.assertIn('English: 273 books', summary)
        self.assertIn('Korean: 10 books', summary)


if __name__ == '__main__':
    unittest.main()
