"""Page-counting core logic.

This module deliberately has no Qt imports so it can be unit-tested without a
running Calibre GUI. Calibre-specific imports happen inside the counting
functions.
"""

import json
import math
import re
import unicodedata


# ISO-639-1/2/3 and BCP-47 aliases we care about. Calibre normally stores
# three-letter codes (kor, eng, jpn, zho) but EPUB dc:language often uses
# two-letter codes (ko, en, ja, zh).
LANGUAGE_ALIASES = {
    'ko': 'kor', 'kor': 'kor', 'ko-kr': 'kor', 'korean': 'kor',
    'en': 'eng', 'eng': 'eng', 'en-us': 'eng', 'en-gb': 'eng', 'english': 'eng',
    'ja': 'jpn', 'jpn': 'jpn', 'japanese': 'jpn',
    'zh': 'zho', 'zho': 'zho', 'chi': 'zho', 'chinese': 'zho',
    'fr': 'fra', 'fra': 'fra', 'fre': 'fra',
    'de': 'deu', 'deu': 'deu', 'ger': 'deu',
    'es': 'spa', 'spa': 'spa',
    'it': 'ita', 'ita': 'ita',
    'ru': 'rus', 'rus': 'rus',
    'pt': 'por', 'por': 'por',
    'id': 'ind', 'ind': 'ind',
}

CJK_LANGUAGES = {'jpn', 'zho', 'cjk'}

# Values Calibre/EPUB metadata uses when no real language is known. Treating
# these as unknown is important: a book tagged "und" would otherwise be
# counted with chars_per_page_other and never get script detection.
UNKNOWN_LANGUAGES = {'', 'und', 'zxx', 'mul', 'unknown', 'none', 'n/a', '--'}

DEFAULT_SETTINGS = {
    'prefer_print_pages': True,
    'include_front_matter': True,
    'calibrate_estimates': True,
    'min_page_list_entries': 10,
    'chars_per_page_korean': 300,
    'chars_per_page_cjk': 700,
    'chars_per_page_english': 1500,
    'chars_per_page_other': 1500,
    'calibration': {},
}

# Only the beginning of a book is examined when the language has to be
# guessed from the text. This is much faster than scanning a whole book and
# just as reliable, since the script of a book does not change halfway
# through it.
LANGUAGE_SAMPLE_SIZE = 100000

# Calibration: books whose page count came from real embedded print
# pagination are used to fit a per-language estimate. A tiny sample is not
# trustworthy, and a flat median is safer than a power law for small samples.
CALIBRATION_MIN_SAMPLES = 8
CALIBRATION_POWER_MIN_SAMPLES = 30
CALIBRATION_REFERENCE_CHARS = 300000.0
EMBEDDED_CALIBRATION_SOURCES = (
    'print-page-list',
    'print-page-map',
    'print-page-map-adobe',
)


def settings_from_prefs(prefs):
    """Return a complete settings dict from a JSONConfig-like mapping."""
    settings = dict(DEFAULT_SETTINGS)
    for key in DEFAULT_SETTINGS:
        try:
            value = prefs[key]
        except Exception:
            continue
        if value is not None:
            settings[key] = value
    for key in ('min_page_list_entries', 'chars_per_page_korean',
                'chars_per_page_cjk', 'chars_per_page_english',
                'chars_per_page_other'):
        try:
            settings[key] = int(settings[key])
        except (TypeError, ValueError):
            settings[key] = DEFAULT_SETTINGS[key]
    for key in ('prefer_print_pages', 'include_front_matter',
                'calibrate_estimates'):
        settings[key] = bool(settings[key])
    settings['calibration'] = normalize_calibration(settings.get('calibration'))
    return settings


def normalize_language(value):
    """Normalize a language tag to a simple code (kor/eng/jpn/zho/...)."""
    if not value:
        return ''
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ''
    code = str(value).strip().lower().replace('_', '-')
    # Some libraries store several languages in a single field.
    if ',' in code:
        code = code.split(',', 1)[0].strip()
    if code in UNKNOWN_LANGUAGES:
        return ''
    if code in LANGUAGE_ALIASES:
        return LANGUAGE_ALIASES[code]
    base = code.split('-')[0]
    if base in UNKNOWN_LANGUAGES:
        return ''
    return LANGUAGE_ALIASES.get(base, base)


def _empty_profile():
    return {
        'chars': 0, 'hangul': 0, 'cjk': 0, 'latin': 0,
        'other': 0, 'neutral': 0, 'images': 0,
    }


def _add_profile(total, part):
    for key in total:
        total[key] += part.get(key, 0)


def _is_hangul(code):
    return (0xAC00 <= code <= 0xD7A3
            or 0x1100 <= code <= 0x11FF
            or 0x3130 <= code <= 0x318F
            or 0xA960 <= code <= 0xA97F
            or 0xD7B0 <= code <= 0xD7FF)


def _is_cjk(code):
    return (0x4E00 <= code <= 0x9FFF
            or 0x3400 <= code <= 0x4DBF
            or 0x3040 <= code <= 0x30FF
            or 0xF900 <= code <= 0xFAFF
            or 0x20000 <= code <= 0x2FA1F)


class _InvisibleCharFilter(dict):
    """Mapping for :meth:`str.translate` that drops invisible characters.

    A character is dropped when its Unicode general category starts with
    ``C``, that is control, format, surrogate, private use and unassigned
    code points. The mapping caches its decisions so that the (slow)
    category lookup happens only once per distinct character.
    """

    def __missing__(self, code):
        ch = chr(code)
        if unicodedata.category(ch).startswith('C'):
            self[code] = None
            return None
        self[code] = code
        return code


INVISIBLE_CHARS = _InvisibleCharFilter()


def count_visible_chars(text):
    """Count non-whitespace, non-control characters in *text*."""
    text = unicodedata.normalize('NFC', text)
    text = text.translate(INVISIBLE_CHARS)
    # split()/join() removes every kind of whitespace in one C level pass.
    return len(''.join(text.split()))


def text_profile(text):
    """Count visible characters by script.

    ``neutral`` covers digits, punctuation and symbols. The estimator spreads
    those over the scripts in proportion to the letters, which keeps the
    total character count unchanged and makes mixed-script books work.
    """
    text = unicodedata.normalize('NFC', text)
    text = text.translate(INVISIBLE_CHARS)
    visible = ''.join(text.split())
    profile = _empty_profile()
    profile['chars'] = len(visible)
    for ch in visible:
        code = ord(ch)
        if _is_hangul(code):
            profile['hangul'] += 1
        elif _is_cjk(code):
            profile['cjk'] += 1
        elif ch.isalpha():
            profile['latin'] += 1
        elif ch.isdigit() or unicodedata.category(ch)[0] in ('P', 'S'):
            profile['neutral'] += 1
        else:
            profile['other'] += 1
    return profile


def script_profile(text):
    """Count Hangul, CJK and Latin letters in *text*."""
    profile = text_profile(text)
    return profile['hangul'], profile['cjk'], profile['latin']


def detect_language_from_profile(profile, fallback=''):
    """Detect the dominant script from a text profile."""
    hangul = profile.get('hangul', 0)
    cjk = profile.get('cjk', 0)
    latin = profile.get('latin', 0)
    other = profile.get('other', 0)
    total = hangul + cjk + latin + other
    if total == 0:
        return normalize_language(fallback) or 'eng'
    if hangul / total >= 0.20:
        return 'kor'
    if cjk / total >= 0.20:
        return 'cjk'
    if other / total >= 0.50:
        return 'other'
    return 'eng'


def detect_language(text, fallback=''):
    """Detect the dominant script of *text*.

    Language metadata is preferred when present; this is only a fallback for
    books with missing or useless metadata.
    """
    profile = text_profile(text[:LANGUAGE_SAMPLE_SIZE])
    return detect_language_from_profile(profile, fallback)


def choose_language(metadata, profile):
    """Pick the language to use, letting a strong script mismatch override.

    Metadata is normally right, but mixed libraries often contain a Korean
    book tagged ``eng`` or an English book tagged ``kor``. A book whose text
    is clearly Hangul must not be counted with 1500 English characters per
    page.
    """
    language = normalize_language(metadata)
    letters = (profile.get('hangul', 0) + profile.get('cjk', 0)
               + profile.get('latin', 0) + profile.get('other', 0))
    if letters == 0:
        return language or 'eng'

    hangul = profile['hangul'] / letters
    cjk = profile['cjk'] / letters
    latin = profile['latin'] / letters
    other = profile['other'] / letters

    if language == 'kor':
        # A Korean book can contain Hanja and English quotations. Only let
        # Latin text override the metadata when it is overwhelming.
        return 'eng' if latin >= 0.80 else 'kor'
    if language in CJK_LANGUAGES:
        return 'eng' if latin >= 0.80 else language
    if language and language != 'eng':
        if hangul >= 0.20:
            return 'kor'
        if cjk >= 0.20:
            return 'cjk'
        return language

    # No language, or English: trust the script when it clearly disagrees.
    if hangul >= 0.20:
        return 'kor'
    if cjk >= 0.20:
        return 'cjk'
    if other >= 0.50:
        return 'other'
    return language or 'eng'


def chars_per_page_for(language, settings):
    if language == 'kor':
        return int(settings['chars_per_page_korean'])
    if language in CJK_LANGUAGES:
        return int(settings['chars_per_page_cjk'])
    if language == 'eng':
        return int(settings['chars_per_page_english'])
    return int(settings['chars_per_page_other'])


def _cpp_for_script(script, language, settings):
    if script == 'hangul':
        return int(settings['chars_per_page_korean'])
    if script == 'cjk':
        return int(settings['chars_per_page_cjk'])
    if script == 'latin':
        # Latin quotations inside a Korean/Chinese/Japanese book are normally
        # English (or another European language) and should not use the
        # Korean characters-per-page value.
        if language in ('eng', 'kor', 'cjk', 'jpn', 'zho'):
            return int(settings['chars_per_page_english'])
        return int(settings['chars_per_page_other'])
    return int(settings['chars_per_page_other'])


def _primary_script(language):
    if language == 'kor':
        return 'hangul'
    if language in CJK_LANGUAGES:
        return 'cjk'
    if language == 'other':
        return 'other'
    return 'latin'


def _estimate_source(language):
    if language == 'kor':
        return 'estimate-kor'
    if language in CJK_LANGUAGES:
        return 'estimate-cjk'
    if language == 'eng':
        return 'estimate-eng'
    return 'estimate-other'


def _model_pages(model, chars):
    """Return the calibrated page count (float) for *chars*."""
    if chars <= 0:
        return 0.0
    if model.get('kind') == 'power':
        cpp = math.exp(model['a'] + model['b'] * math.log(float(chars)))
    else:
        cpp = float(model.get('cpp', 0))
    return chars / max(1.0, cpp)


def estimate_from_profile(profile, language, settings=None, calibration=None):
    """Return (pages, source, calibrated) for a text profile."""
    settings = settings_from_prefs(settings or {})
    profile = {key: int(profile.get(key) or 0) for key in _empty_profile()}
    chars = profile['chars']
    if chars <= 0:
        return 1, _estimate_source(language), False

    letters = (profile['hangul'] + profile['cjk']
               + profile['latin'] + profile['other'])
    cpp = {script: _cpp_for_script(script, language, settings)
           for script in ('hangul', 'cjk', 'latin', 'other')}

    if letters == 0:
        # Punctuation/digits only: use the language's flat value.
        base_pages = chars / float(max(1, chars_per_page_for(language, settings)))
        effective = {'hangul': 0, 'cjk': 0, 'latin': 0, 'other': 0}
    else:
        neutral = profile['neutral']
        effective = {}
        for script in ('hangul', 'cjk', 'latin', 'other'):
            share = profile[script] / float(letters)
            effective[script] = profile[script] + neutral * share
        base_pages = sum(effective[script] / float(max(1, cpp[script]))
                         for script in effective)

    calibrated = False
    model = (calibration or {}).get(language)
    if model:
        primary = _primary_script(language)
        base_primary = effective.get(primary, 0) / float(max(1, cpp[primary]))
        if base_primary > 0:
            model_pages = _model_pages(model, chars)
            if model_pages > 0:
                base_pages *= model_pages / base_primary
                calibrated = True

    pages = max(1, int(math.ceil(base_pages)))
    return pages, _estimate_source(language), calibrated


def estimate_pages(char_count, language, settings):
    """Return (pages, source) for a character count and language.

    Kept as the simple public entry point used by older tests and callers.
    Mixed-script books should use :func:`estimate_from_profile` instead.
    """
    profile = _empty_profile()
    profile['chars'] = max(0, int(char_count))
    script = { 'kor': 'hangul', 'jpn': 'cjk', 'zho': 'cjk',
               'cjk': 'cjk', 'eng': 'latin' }.get(language, 'other')
    profile[script] = profile['chars']
    pages, source, _calibrated = estimate_from_profile(
        profile, language, settings, None)
    return pages, source


# ---------------------------------------------------------------------------
# Embedded print pagination
# ---------------------------------------------------------------------------

PAGEBREAK_NS = {'epub': 'http://www.idpf.org/2007/ops'}
PAGEBREAK_XPATH = (
    '//*[contains(@epub:type, "pagebreak")'
    ' or @type="pagebreak"'
    ' or @role="doc-pagebreak"'
    ' or contains(@class, "pagebreak")]'
)

PAGE_LABEL_RE = re.compile(r'^(?:\d+|[ivxlcdm]+)$', re.IGNORECASE)
PAGE_PREFIX_RE = re.compile(r'^(?:pg|page|p)[\s._:#-]*', re.IGNORECASE)
FRAG_NUMBER_RE = re.compile(r'^(?:(?:pg|page|p)[\s._:#-]*)?(\d+)$', re.IGNORECASE)
ROMAN_RE = re.compile(r'^[ivxlcdm]+$', re.IGNORECASE)


def normalize_page_label(value):
    """Turn a pagebreak id/title such as page_12 or 'Page 12' into '12'."""
    if value is None:
        return ''
    label = unicodedata.normalize('NFC', str(value)).strip().lower()
    label = label.replace('\u00a0', ' ')
    label = PAGE_PREFIX_RE.sub('', label).strip(' ._:#-')
    if label.isdigit():
        return str(int(label))
    return label


def roman_to_int(value):
    """Convert a roman numeral to an integer, returning 0 when invalid."""
    if not value:
        return 0
    value = str(value).strip().lower()
    if not ROMAN_RE.match(value) or len(value) > 12:
        return 0
    numbers = {'i': 1, 'v': 5, 'x': 10, 'l': 50,
               'c': 100, 'd': 500, 'm': 1000}
    total = 0
    previous = 0
    for ch in reversed(value):
        number = numbers[ch]
        if number < previous:
            total -= number
        else:
            total += number
            previous = number
    return total


def label_page_number(value):
    """Return (arabic, roman) for a page label; 0 means not a number."""
    label = normalize_page_label(value)
    if not label:
        return 0, 0
    if label.isdigit():
        return int(label), 0
    roman = roman_to_int(label)
    if roman:
        return 0, roman
    return 0, 0


def _fragment_page_number(fragment):
    """Extract a page number from an anchor fragment such as #p42.

    Only fragments that clearly encode a page number are accepted. Google
    Books style fragments such as ``GBS.0003.05`` must not be read as page 5.
    """
    if not fragment:
        return 0
    match = FRAG_NUMBER_RE.match(fragment.strip())
    if match:
        return int(match.group(1))
    return 0


def _pagebreak_label(marker):
    """Return the page number carried by a pagebreak marker.

    A marker can carry its page number in ``aria-label``, ``title`` or ``id``.
    The first attribute that yields a plain number wins, because publishers
    often add a descriptive ``aria-label`` next to a numeric ``title`` or
    ``id``.
    """
    fallback = ''
    for attr in ('aria-label', 'title', 'id'):
        try:
            value = marker.get(attr)
        except Exception:
            value = None
        if not value:
            continue
        label = normalize_page_label(value)
        if not label:
            continue
        if label.isdigit():
            return label
        if not fallback:
            fallback = label
    try:
        text = ''.join(marker.itertext()).strip()
    except Exception:
        text = ''
    label = normalize_page_label(text)
    if label.isdigit():
        return label
    return fallback or label


def _is_strict_pagebreak(marker):
    """True for EPUB/ARIA pagebreak markers rather than class-only anchors."""
    try:
        items = marker.attrib.items()
    except Exception:
        return False
    for key, value in items:
        local = key.rsplit('}', 1)[-1].lower()
        if local in ('type', 'role') and 'pagebreak' in str(value).lower():
            return True
    return False


def _pagebreak_count(labels, settings):
    """Return a trusted embedded page count from pagebreak markers.

    *labels* is a list of ``(label, strict)`` in reading order. Only numeric
    labels are trusted, and unlabelled markers are ignored: adding them to a
    set of numbered pages would overstate a book with a chapter-start anchor
    on every page.
    """
    if not labels:
        return 0
    minimum = int(settings['min_page_list_entries'])
    numeric = []
    roman = []
    strict_count = 0
    for label, strict in labels:
        arabic, numeral = label_page_number(label)
        if arabic:
            numeric.append(arabic)
        elif numeral:
            roman.append(numeral)
        if strict:
            strict_count += 1

    if numeric:
        unique = sorted(set(numeric))
        maximum = unique[-1]
        if maximum < minimum:
            return 0
        span = maximum - unique[0] + 1
        coverage = len(unique) / float(span) if span > 0 else 0.0
        strict_ratio = strict_count / float(len(labels))
        # A dense class-only marker set is fine. A sparse one is only trusted
        # when the elements really declare themselves as EPUB pagebreaks.
        if strict_ratio < 0.5 and coverage < 0.5:
            return 0
        restarts = sum(1 for first, second in zip(numeric, numeric[1:])
                       if second < first - 5)
        pages = len(numeric) if restarts > 2 else maximum
        if (settings['include_front_matter'] and unique[0] <= 1 and roman):
            pages += min(max(roman), 200)
        return pages
    if roman:
        maximum = max(roman)
        if maximum >= minimum:
            return maximum
    return 0


def _element_type(element):
    parts = []
    try:
        items = element.attrib.items()
    except Exception:
        return ''
    for key, value in items:
        local = key.rsplit('}', 1)[-1].lower()
        if local in ('type', 'role'):
            parts.append(str(value).lower())
    return ' '.join(parts)


def _add_page_number(arabic, roman, number, numeral, target, frag):
    if number:
        arabic.setdefault(number, (target, frag))
    elif numeral:
        roman.setdefault(numeral, (target, frag))


def _nav_page_list(container):
    """Read the EPUB 3 nav page-list.

    Calibre's TOC parser does not always extract the page number from a nav
    page-list (some publishers put it in the link text, others in the href).
    Reading the nav directly is more reliable.
    """
    arabic = {}
    roman = {}
    entries = 0
    try:
        nav_names = list(container.manifest_items_with_property('nav'))
    except Exception:
        nav_names = []
    for nav_name in nav_names:
        try:
            root = container.parsed(nav_name)
        except Exception:
            continue
        try:
            navs = root.xpath('//*[local-name()="nav"]')
        except Exception:
            navs = ()
        for nav in navs:
            nav_type = _element_type(nav)
            if 'page-list' not in nav_type and 'doc-pagelist' not in nav_type:
                continue
            try:
                anchors = nav.xpath('.//*[local-name()="a"]')
            except Exception:
                anchors = ()
            for anchor in anchors:
                entries += 1
                label = ''.join(anchor.itertext()).strip()
                href = anchor.get('href') or ''
                fragment = href.partition('#')[2]
                target = nav_name
                if href:
                    try:
                        target = container.href_to_name(href, nav_name)
                    except Exception:
                        target = nav_name
                number, numeral = label_page_number(label)
                if not number and not numeral:
                    number = _fragment_page_number(fragment)
                if not number and not numeral:
                    parent = anchor.getparent()
                    while (parent is not None
                           and not str(parent.tag).lower().endswith('li')):
                        parent = parent.getparent()
                    if parent is not None:
                        number, numeral = label_page_number(parent.get('id'))
                _add_page_number(arabic, roman, number, numeral,
                                 target, fragment)
    if entries:
        return {'arabic': arabic, 'roman': roman, 'entries': entries}
    return {}


def _ncx_page_list(container):
    """Read the NCX pageList/pageMap page numbers."""
    arabic = {}
    roman = {}
    entries = 0
    try:
        ncx_names = container.manifest_type_map.get(
            'application/x-dtbncx+xml', ()) or ()
    except Exception:
        return {}
    for ncx_name in ncx_names:
        try:
            root = container.parsed(ncx_name)
        except Exception:
            continue
        try:
            targets = root.xpath('//*[local-name()="pageTarget"]')
        except Exception:
            continue
        for target in targets:
            entries += 1
            value = target.get('value')
            number, numeral = label_page_number(value)
            content_name = ncx_name
            if not number and not numeral:
                try:
                    contents = target.xpath(
                        './/*[local-name()="content"]')
                except Exception:
                    contents = ()
                for content in contents:
                    src = content.get('src') or ''
                    fragment = src.partition('#')[2]
                    try:
                        content_name = container.href_to_name(
                            src, ncx_name)
                    except Exception:
                        content_name = ncx_name
                    number = _fragment_page_number(fragment)
                    if number:
                        break
            _add_page_number(arabic, roman, number, numeral,
                             content_name, '')
    if entries:
        return {'arabic': arabic, 'roman': roman, 'entries': entries}
    return {}


def _adobe_page_map(container):
    """Read an Adobe page-map.xml, used by many EPUB 2 books."""
    names = []
    try:
        names = list(container.manifest_type_map.get(
            'application/oebps-page-map+xml', ()) or ())
    except Exception:
        names = []
    if not names:
        # Some broken books do not declare the media type.
        for name in getattr(container, 'name_path_map', {}) or {}:
            base = name.rsplit('/', 1)[-1].lower()
            if base in ('page-map.xml', '_page_map_.xml'):
                names.append(name)
    arabic = {}
    roman = {}
    entries = 0
    for name in names:
        try:
            root = container.parsed(name)
        except Exception:
            continue
        tag = root.tag.rsplit('}', 1)[-1].lower() if isinstance(root.tag, str) else ''
        if tag != 'page-map':
            continue
        try:
            pages = root.xpath('//*[local-name()="page"]')
        except Exception:
            continue
        for page in pages:
            entries += 1
            number, numeral = label_page_number(page.get('name'))
            _add_page_number(arabic, roman, number, numeral, name, '')
    if entries:
        return {'arabic': arabic, 'roman': roman, 'entries': entries}
    return {}


def _page_count_from_values(data, settings):
    """Return the print page count described by page-list/page-map values."""
    if not data:
        return 0
    arabic = data.get('arabic') or {}
    roman = data.get('roman') or {}
    minimum = int(settings['min_page_list_entries'])
    if len(arabic) < minimum and len(roman) < minimum:
        return 0
    if not arabic:
        return min(max(roman), 200) if roman else 0
    pages = max(arabic)
    if (settings['include_front_matter'] and roman
            and max(roman) <= min(pages, 200)):
        # Roman-numbered front matter normally starts at i and precedes the
        # arabic body, so the last roman page is the number of front-matter
        # pages. Cap it to avoid nonsense from a corrupt file.
        pages += max(roman)
    return pages


def _embedded_page_count(container, settings):
    """Return (source, pages, arabic_max) for the best embedded pagination."""
    candidates = []
    nav = _nav_page_list(container)
    if nav:
        candidates.append((0, 'print-page-list', nav))
    ncx = _ncx_page_list(container)
    if ncx:
        candidates.append((1, 'print-page-map', ncx))
    adobe = _adobe_page_map(container)
    if adobe:
        candidates.append((2, 'print-page-map-adobe', adobe))

    usable = []
    for priority, source, data in candidates:
        pages = _page_count_from_values(data, settings)
        if pages:
            arabic_max = max(data.get('arabic') or {0})
            usable.append((priority, source, pages, arabic_max))
    if not usable:
        return None

    maximum = max(pages for _priority, _source, pages, _arabic in usable)
    # Prefer the standard EPUB page-list/page-map. Fall back to a lower
    # priority source only when the preferred one is clearly partial (for
    # example a nav page-list that stops after the first chapter while an
    # Adobe page map describes the whole book).
    for _priority, source, pages, arabic_max in sorted(usable):
        if pages >= maximum * 0.5:
            return source, pages, arabic_max
    _priority, source, pages, arabic_max = max(
        usable, key=lambda item: item[2])
    return source, pages, arabic_max


def _spine_names(container):
    """Yield (name, linear) from Calibre's container across versions."""
    for item in container.spine_names:
        if isinstance(item, (tuple, list)):
            if len(item) >= 2:
                yield item[0], bool(item[1])
            else:
                yield item[0], True
        else:
            yield item, True


def _is_fixed_layout(container):
    """Return True when *container* holds a fixed-layout (pre-paginated) book."""
    try:
        from calibre.ebooks.oeb.polish.utils import fixed_layout_data
    except Exception:
        fixed_layout_data = None
    if fixed_layout_data is not None:
        try:
            if fixed_layout_data(container):
                return True
        except Exception:
            pass
    # The value of rendition:layout is the text of the element, not an
    # attribute, so it cannot be read with an @content XPath expression.
    try:
        values = container.opf_xpath(
            '//opf:metadata/opf:meta[@property="rendition:layout"]/text()')
    except Exception:
        values = ()
    for value in values or ():
        if str(value).strip().lower() == 'pre-paginated':
            return True
    book_type = str(getattr(container, 'book_type', '') or '').lower()
    return book_type in ('fixedlayout', 'fixed-layout')


def _extract_text(container, spine):
    """Return (text profile, pagebreak labels) for the spine.

    The profile is accumulated per document, so a whole-book string is never
    built. Ruby annotations are removed: counting both the base text and its
    furigana would inflate Japanese books by 20-100%.
    """
    profile = _empty_profile()
    labels = []
    for name in spine:
        try:
            root = container.parsed(name)
        except Exception:
            continue
        try:
            markers = root.xpath(PAGEBREAK_XPATH, namespaces=PAGEBREAK_NS)
        except Exception:
            markers = ()
        for marker in markers:
            label = _pagebreak_label(marker)
            if label:
                labels.append((label, _is_strict_pagebreak(marker)))
        try:
            profile['images'] += len(root.xpath(
                '//*[local-name()="img" or local-name()="svg"]'))
        except Exception:
            pass
        try:
            for bad in root.xpath(
                '//*[local-name()="script" or local-name()="style"'
                ' or local-name()="head" or local-name()="svg"'
                ' or local-name()="rt" or local-name()="rp"]'
            ):
                parent = bad.getparent()
                if parent is not None:
                    parent.remove(bad)
        except Exception:
            pass
        try:
            text = ' '.join(root.itertext())
        except Exception:
            continue
        _add_profile(profile, text_profile(text))
    return profile, labels


def _open_epub(path):
    from calibre.ebooks.oeb.polish.container import get_container
    return get_container(path, tweak_mode=False)


def count_epub(path, language_hint='', settings=None):
    """Count pages in an EPUB.

    Priority:
      1. fixed-layout: one page per spine item
      2. embedded print pagination (EPUB page-list / NCX page-map /
         Adobe page-map / pagebreak)
      3. language-aware character estimate, optionally calibrated from the
         library's own embedded pagination
    """
    settings = settings_from_prefs(settings or {})
    container = _open_epub(path)
    all_spine = [name for name, _linear in _spine_names(container)]
    spine = [name for name, linear in _spine_names(container) if linear]
    if not spine:
        spine = list(all_spine)
    language = normalize_language(
        getattr(container.mi, 'language', '') or language_hint)

    if _is_fixed_layout(container):
        return {
            'pages': max(1, len(all_spine)),
            'source': 'fixed-layout',
            'language': language,
            'chars': 0,
            'hangul': 0,
            'cjk': 0,
            'latin': 0,
            'other': 0,
            'neutral': 0,
            'images': 0,
            'calibrated': False,
        }

    # Read the page lists before _extract_text mutates the parsed trees.
    embedded = None
    if settings['prefer_print_pages']:
        embedded = _embedded_page_count(container, settings)
    profile, pagebreak_labels = _extract_text(container, spine)
    language = choose_language(language, profile)
    calibration = normalize_calibration(settings.get('calibration'))
    if not settings['calibrate_estimates']:
        calibration = {}
    estimated, estimate_source, calibrated = estimate_from_profile(
        profile, language, settings, calibration)

    if settings['prefer_print_pages']:
        pagebreak_pages = _pagebreak_count(pagebreak_labels, settings)
        options = []
        if embedded and pagebreak_pages:
            embedded_source, embedded_pages, embedded_arabic = embedded
            prefer_pagebreak = False
            if embedded_source == 'print-page-map-adobe':
                # An Adobe page map is sometimes inherited from a different
                # printing (a large-print edition, for example). When the
                # pagebreak markers in this EPUB disagree with the map's
                # arabic body, the markers describe the book in hand more
                # closely. If the markers match the arabic body, the map is
                # the same edition and its roman front matter is valuable.
                near_body = abs(pagebreak_pages - embedded_arabic) <= max(
                    3, int(embedded_arabic * 0.05))
                if not near_body:
                    largest = max(embedded_pages, pagebreak_pages)
                    if abs(embedded_pages - pagebreak_pages) / float(largest) > 0.2:
                        prefer_pagebreak = True
            elif pagebreak_pages > embedded_pages * 1.25:
                # A partial page-list can stop after the first chapters while
                # the pagebreak markers continue through the whole book.
                prefer_pagebreak = True
            if prefer_pagebreak:
                options = [('print-pagebreak', pagebreak_pages), embedded[:2]]
            else:
                options = [embedded[:2], ('print-pagebreak', pagebreak_pages)]
        elif embedded:
            options = [embedded[:2]]
        elif pagebreak_pages:
            options = [('print-pagebreak', pagebreak_pages)]
        # A short page list is usually a fragment rather than the pagination
        # of the whole book. The old 10% floor was loose enough to accept a
        # 40-page list for a 300-page book; 20% is still generous but much
        # safer.
        floor = max(int(settings['min_page_list_entries']),
                    int(estimated * 0.2))
        for source, pages in options:
            if pages >= floor:
                return {
                    'pages': pages,
                    'source': source,
                    'language': language,
                    'chars': profile['chars'],
                    'hangul': profile['hangul'],
                    'cjk': profile['cjk'],
                    'latin': profile['latin'],
                    'other': profile['other'],
                    'neutral': profile['neutral'],
                    'images': profile['images'],
                    'calibrated': False,
                    'estimate': estimated,
                }

    # A reflowable EPUB that is only images (a comic or picture book) has
    # almost no text to count. One page per image is a better answer than
    # one page for the whole book.
    if profile['chars'] < 500 and profile['images'] >= 5:
        return {
            'pages': max(1, profile['images']),
            'source': 'image-pages',
            'language': language,
            'chars': profile['chars'],
            'hangul': profile['hangul'],
            'cjk': profile['cjk'],
            'latin': profile['latin'],
            'other': profile['other'],
            'neutral': profile['neutral'],
            'images': profile['images'],
            'calibrated': False,
            'estimate': estimated,
        }

    return {
        'pages': estimated,
        'source': estimate_source,
        'language': language,
        'chars': profile['chars'],
        'hangul': profile['hangul'],
        'cjk': profile['cjk'],
        'latin': profile['latin'],
        'other': profile['other'],
        'neutral': profile['neutral'],
        'images': profile['images'],
        'calibrated': calibrated,
        'estimate': estimated,
    }


def count_pdf(path, _settings=None):
    """Return the real page count of a PDF."""
    try:
        from calibre.utils.podofo import get_page_count
        pages = int(get_page_count(path))
    except Exception:
        from calibre.library.page_count import count_pages
        pages = int(count_pages(path))
    if pages < 1:
        raise ValueError('PDF has no readable pages')
    return {
        'pages': pages,
        'source': 'pdf',
        'language': '',
        'chars': 0,
        'hangul': 0,
        'cjk': 0,
        'latin': 0,
        'other': 0,
        'neutral': 0,
        'images': 0,
        'calibrated': False,
    }


def count_other(path, fmt, _settings=None):
    """Fallback for formats other than EPUB/PDF."""
    from calibre.library.page_count import count_pages
    pages = int(count_pages(path))
    if pages < 1:
        raise ValueError('Calibre could not count pages in %s' % fmt)
    return {
        'pages': pages,
        'source': 'calibre-%s' % str(fmt).lower(),
        'language': '',
        'chars': 0,
        'hangul': 0,
        'cjk': 0,
        'latin': 0,
        'other': 0,
        'neutral': 0,
        'images': 0,
        'calibrated': False,
    }


def count_task(task, settings=None):
    """Count one task.

    A task has book_id, title, language, formats and paths. Formats are tried
    in order, so an EPUB failure can fall back to a PDF.
    """
    settings = settings_from_prefs(settings or {})
    errors = []
    formats = task.get('formats') or []
    paths = task.get('paths') or []
    for fmt, path in zip(formats, paths):
        fmt = str(fmt).upper()
        try:
            if fmt == 'EPUB':
                result = count_epub(path, task.get('language') or '', settings)
            elif fmt == 'PDF':
                result = count_pdf(path, settings)
            else:
                result = count_other(path, fmt, settings)
            result['book_id'] = task.get('book_id')
            result['format'] = fmt
            return result
        except Exception as err:
            errors.append('%s: %s' % (fmt, err))
    return {
        'book_id': task.get('book_id'),
        'error': '; '.join(errors) or 'No readable EPUB/PDF format',
    }


# ---------------------------------------------------------------------------
# Library calibration
# ---------------------------------------------------------------------------

def _median(values):
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _linear_fit(xs, ys):
    count = len(xs)
    if count < 3:
        return None
    sx = sum(xs)
    sy = sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys))
    denominator = count * sxx - sx * sx
    if abs(denominator) < 1e-12:
        return None
    slope = (count * sxy - sx * sy) / denominator
    intercept = (sy - slope * sx) / count
    return intercept, slope


def _fit_power(pairs, reference=CALIBRATION_REFERENCE_CHARS):
    """Fit log(cpp) = a + b*log(chars), rejecting implausible fits."""
    pairs = [(float(chars), float(pages)) for chars, pages in pairs
             if chars > 0 and pages > 0]
    if len(pairs) < CALIBRATION_POWER_MIN_SAMPLES:
        return None
    xs = [math.log(chars) for chars, _pages in pairs]
    ys = [math.log(chars / pages) for chars, pages in pairs]
    fit = _linear_fit(xs, ys)
    if fit is None:
        return None
    a, b = fit
    for _iteration in range(2):
        residuals = [y - (a + b * x) for x, y in zip(xs, ys)]
        centre = _median(residuals)
        mad = _median([abs(value - centre) for value in residuals])
        if mad <= 1e-9:
            break
        keep = [index for index, value in enumerate(residuals)
                if abs(value - centre) <= 3.0 * mad]
        if len(keep) < max(6, len(pairs) // 2):
            break
        refit = _linear_fit([xs[index] for index in keep],
                            [ys[index] for index in keep])
        if refit is None:
            break
        a, b = refit
    if not (0.0 <= b <= 0.8):
        return None
    cpp_at_reference = math.exp(a + b * math.log(reference))
    if not (200.0 <= cpp_at_reference <= 6000.0):
        return None
    return {'kind': 'power', 'a': a, 'b': b}


def _fit_median(pairs):
    """Fit a flat characters-per-page value from a small sample."""
    values = [float(chars) / float(pages) for chars, pages in pairs
              if chars > 0 and pages > 0]
    if len(values) < CALIBRATION_MIN_SAMPLES:
        return None
    cpp = _median(values)
    if not (50.0 <= cpp <= 10000.0):
        return None
    return {'kind': 'median', 'cpp': cpp}


def _model_mape(model, pairs):
    errors = []
    for chars, pages in pairs:
        predicted = _model_pages(model, chars)
        if predicted > 0 and pages > 0:
            errors.append(abs(predicted / pages - 1.0))
    return _median(errors)


def calibration_samples(results):
    """Collect (chars, pages) samples from books with embedded pagination."""
    samples = {}
    for item in (results or {}).values():
        if not isinstance(item, dict):
            continue
        if item.get('source') not in EMBEDDED_CALIBRATION_SOURCES:
            continue
        try:
            pages = int(item.get('pages') or 0)
            chars = int(item.get('chars') or 0)
        except (TypeError, ValueError):
            continue
        language = item.get('language') or ''
        if pages < 5 or chars < 5000 or not language:
            continue
        samples.setdefault(language, []).append((chars, pages))
    return samples


def fit_calibration(samples):
    """Fit a calibration model per language.

    *samples* is the dict returned by :func:`calibration_samples`. Languages
    with too few samples are omitted, so the configured characters-per-page
    values remain in use for them.
    """
    models = {}
    for language, pairs in (samples or {}).items():
        if not pairs:
            continue
        model = None
        if len(pairs) >= CALIBRATION_POWER_MIN_SAMPLES:
            model = _fit_power(pairs)
            if model is not None:
                model_mape = _model_mape(model, pairs)
                if model_mape > 0.25:
                    # A power fit this bad is worse than a robust flat value.
                    model = None
        if model is None and len(pairs) >= CALIBRATION_MIN_SAMPLES:
            model = _fit_median(pairs)
        if model is None:
            continue
        model['n'] = len(pairs)
        model['mape'] = _model_mape(model, pairs)
        models[language] = model
    return models


def normalize_calibration(value):
    """Validate a calibration mapping loaded from preferences."""
    if not value:
        return {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return {}
    if not isinstance(value, dict):
        return {}
    models = {}
    for language, model in value.items():
        if not isinstance(model, dict):
            continue
        try:
            kind = model.get('kind')
            if kind == 'power':
                a = float(model['a'])
                b = float(model['b'])
                if not (0.0 <= b <= 0.8):
                    continue
                reference = math.exp(a + b * math.log(CALIBRATION_REFERENCE_CHARS))
                if not (200.0 <= reference <= 6000.0):
                    continue
                models[language] = {
                    'kind': 'power', 'a': a, 'b': b,
                    'n': int(model.get('n') or 0),
                    'mape': float(model.get('mape') or 0.0),
                }
            elif kind == 'median':
                cpp = float(model['cpp'])
                if not (50.0 <= cpp <= 10000.0):
                    continue
                models[language] = {
                    'kind': 'median', 'cpp': cpp,
                    'n': int(model.get('n') or 0),
                    'mape': float(model.get('mape') or 0.0),
                }
        except (KeyError, TypeError, ValueError):
            continue
    return models


def recalibrate_results(results, models, settings=None):
    """Recompute estimate-only results with a calibration mapping.

    Returns the number of books whose page count was recalculated. Results
    from embedded print pagination are never changed.
    """
    settings = settings_from_prefs(settings or {})
    if not settings['calibrate_estimates'] or not models:
        return 0
    changed = 0
    for item in (results or {}).values():
        if not isinstance(item, dict):
            continue
        source = item.get('source') or ''
        if not source.startswith('estimate-'):
            continue
        language = item.get('language') or ''
        model = models.get(language)
        if not model:
            continue
        try:
            chars = int(item.get('chars') or 0)
        except (TypeError, ValueError):
            continue
        if chars <= 0:
            continue
        profile = {key: int(item.get(key) or 0) for key in _empty_profile()}
        pages, new_source, calibrated = estimate_from_profile(
            profile, language, settings, {language: model})
        item['pages'] = pages
        item['source'] = new_source
        item['calibrated'] = calibrated
        changed += 1
    return changed


def calibration_summary(models):
    """Return a human readable summary of a calibration mapping."""
    parts = []
    names = {'eng': 'English', 'kor': 'Korean', 'cjk': 'CJK'}
    for language in sorted(models or {}):
        model = models[language]
        try:
            samples = int(model.get('n') or 0)
            error = float(model.get('mape') or 0.0) * 100.0
        except (TypeError, ValueError):
            continue
        parts.append('%s: %d books, %.0f%% median fit error'
                     % (names.get(language, language), samples, error))
    return '; '.join(parts)
