"""Build small EPUB files used by the calibre backed tests.

The fixtures are deliberately tiny but exercise every code path of
``core.count_epub``: plain text, Korean text, an EPUB 3 nav page-list, an
EPUB 2 NCX page map, pagebreak markers, the anchors Calibre itself creates,
fixed-layout books, a page-list that is too short to be trusted, Adobe page
maps, roman front matter, ruby annotations and mixed-language text.
"""

import os
import zipfile

CONTAINER = '''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
'''

ENGLISH = ('It was the best of times, it was the worst of times, it was the age of '
           'wisdom, it was the age of foolishness. ')

KOREAN = ('그녀는 아무 말도 하지 않았다. 창밖에는 비가 내리고 있었다. '
          '오래된 책방의 문이 삐걱거렸다. ')

CHAPTER = '''<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>Chapter</title><style>p {{ margin: 0; }}</style></head>
<body>
{body}
</body>
</html>
'''


def opf(lang='en', extra_meta='', epub2=False, extra_manifest=''):
    manifest = (
        '    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>\n'
        '    <item id="c1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>\n'
        '    <item id="c2" href="chapter2.xhtml" media-type="application/xhtml+xml"/>'
    )
    if extra_manifest:
        manifest += '\n' + extra_manifest
    if epub2:
        manifest += '\n    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
    version = '2.0' if epub2 else '3.0'
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="{version}" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Test Book</dc:title>
    <dc:language>{lang}</dc:language>
    <dc:identifier id="uid">urn:uuid:1234</dc:identifier>
    {extra_meta}
  </metadata>
  <manifest>
{manifest}
  </manifest>
  <spine toc="ncx">
    <itemref idref="c1"/>
    <itemref idref="c2"/>
  </spine>
</package>
'''


def nav_doc(page_list=None, fragment_labels=False, roman=()):
    pl = ''
    items = []
    for i in page_list or ():
        if fragment_labels:
            items.append(
                f'<li><a href="chapter1.xhtml#p{i}">navpoint-{i}</a></li>')
        else:
            items.append(
                f'<li><a href="chapter1.xhtml#page_{i}">{i}</a></li>')
    for i in roman:
        items.append(f'<li><a href="chapter1.xhtml#page_{i}">{i}</a></li>')
    if items:
        pl = f'<nav epub:type="page-list" hidden=""><ol>{"".join(items)}</ol></nav>'
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>Nav</title></head>
<body>
<nav epub:type="toc"><ol><li><a href="chapter1.xhtml">Chapter 1</a></li></ol></nav>
{pl}
</body>
</html>
'''


def ncx_doc(page_map=None):
    pm = ''
    if page_map:
        targets = ''.join(
            f'<pageTarget id="pt{i}" type="normal" value="{i}">'
            f'<content src="chapter1.xhtml#page_{i}"/></pageTarget>'
            for i in page_map)
        pm = f'<pageMap>{targets}</pageMap>'
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="urn:uuid:1234"/></head>
  <docTitle><text>Test Book</text></docTitle>
  <navMap>
    <navPoint id="np1" playOrder="1">
      <navLabel><text>Chapter 1</text></navLabel>
      <content src="chapter1.xhtml"/>
    </navPoint>
  </navMap>
  {pm}
</ncx>
'''


def page_map_doc(pages, roman=()):
    entries = []
    for i in roman:
        entries.append(f'  <page name="{i}" href="chapter1.xhtml"/>')
    for i in pages:
        entries.append(f'  <page name="{i}" href="chapter1.xhtml#p{i}"/>')
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<page-map xmlns="http://www.idpf.org/2007/opf">
{chr(10).join(entries)}
</page-map>
'''


def _build(path, chapters, nav=None, opf_xml=None, ncx=None, extra=None):
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('mimetype', 'application/epub+zip', zipfile.ZIP_STORED)
        z.writestr('META-INF/container.xml', CONTAINER)
        z.writestr('OEBPS/content.opf', opf_xml or opf())
        if nav is not None:
            z.writestr('OEBPS/nav.xhtml', nav)
        if ncx is not None:
            z.writestr('OEBPS/toc.ncx', ncx)
        for name, data in (extra or {}).items():
            z.writestr('OEBPS/' + name, data)
        for i, chapter in enumerate(chapters, 1):
            z.writestr(f'OEBPS/chapter{i}.xhtml', chapter)


def build_fixtures(directory):
    """Write every fixture into *directory* and return the directory."""
    os.makedirs(directory, exist_ok=True)

    def path(name):
        return os.path.join(directory, name)

    # Plain reflowable English book without any pagination.
    _build(path('plain.epub'),
           [CHAPTER.format(body=f'<p>{ENGLISH * 200}</p>'),
            CHAPTER.format(body=f'<p>{ENGLISH * 200}</p>')],
           nav=nav_doc())

    # Korean book, the language comes from the metadata.
    _build(path('korean.epub'),
           [CHAPTER.format(body=f'<p>{KOREAN * 300}</p>'),
            CHAPTER.format(body=f'<p>{KOREAN * 300}</p>')],
           nav=nav_doc(), opf_xml=opf(lang='ko'))

    # EPUB 3 nav page-list with 30 pages.
    _build(path('pagelist.epub'),
           [CHAPTER.format(body=f'<p>{ENGLISH * 200}</p>'),
            CHAPTER.format(body=f'<p>{ENGLISH * 200}</p>')],
           nav=nav_doc(page_list=list(range(1, 31))))

    # Nav page-list whose link text is not a number; the number is in the
    # href fragment, as in some real publisher files.
    _build(path('navfrag.epub'),
           [CHAPTER.format(body=f'<p>{ENGLISH * 200}</p>'),
            CHAPTER.format(body=f'<p>{ENGLISH * 200}</p>')],
           nav=nav_doc(page_list=list(range(1, 21)), fragment_labels=True))

    # Roman front matter followed by 20 arabic pages.
    _build(path('roman.epub'),
           [CHAPTER.format(body=f'<p>{ENGLISH * 200}</p>'),
            CHAPTER.format(body=f'<p>{ENGLISH * 200}</p>')],
           nav=nav_doc(page_list=list(range(1, 21)),
                       roman=tuple('i ii iii iv'.split())))

    # 30 numbered pagebreak markers.
    breaks = ''.join(f'<span epub:type="pagebreak" id="page_{i}" title="{i}"/>'
                     for i in range(1, 31))
    _build(path('pagebreak.epub'),
           [CHAPTER.format(body=f'<p>{breaks}{ENGLISH * 200}</p>'),
            CHAPTER.format(body=f'<p>{ENGLISH * 200}</p>')],
           nav=nav_doc())

    # An Adobe page map that agrees with the pagebreak markers. The map is
    # more complete (it includes two front-matter pages) and should win.
    _build(path('pagemap_agree.epub'),
           [CHAPTER.format(body=f'<p>{breaks}{ENGLISH * 200}</p>'),
            CHAPTER.format(body=f'<p>{ENGLISH * 200}</p>')],
           nav=nav_doc(),
           opf_xml=opf(extra_manifest=(
               '    <item id="pm" href="page-map.xml" '
               'media-type="application/oebps-page-map+xml"/>')),
           extra={'page-map.xml': page_map_doc(range(1, 33))})

    # An Adobe page map from a different (larger) printing. The pagebreak
    # markers in this EPUB are the better source.
    _build(path('pagemap_conflict.epub'),
           [CHAPTER.format(body=f'<p>{breaks}{ENGLISH * 200}</p>'),
            CHAPTER.format(body=f'<p>{ENGLISH * 200}</p>')],
           nav=nav_doc(),
           opf_xml=opf(extra_manifest=(
               '    <item id="pm" href="page-map.xml" '
               'media-type="application/oebps-page-map+xml"/>')),
           extra={'page-map.xml': page_map_doc(range(1, 51))})

    # The anchors Calibre creates, they must not be counted as pages.
    _build(path('calibre_pb.epub'),
           [CHAPTER.format(body=f'<p><span id="calibre_pb_0"></span>{ENGLISH * 400}</p>'),
            CHAPTER.format(body=f'<p><span id="calibre_pb_1"></span>{ENGLISH * 400}</p>')],
           nav=nav_doc())

    # Fixed layout books.
    _build(path('fixed.epub'),
           [CHAPTER.format(body='<p>x</p>'), CHAPTER.format(body='<p>y</p>')],
           nav=nav_doc(),
           opf_xml=opf(extra_meta='<meta property="rendition:layout">pre-paginated</meta>'
                                 '<meta name="fixed-layout" content="true"/>'))
    _build(path('fixed_rendition.epub'),
           [CHAPTER.format(body='<p>x</p>'), CHAPTER.format(body='<p>y</p>')],
           nav=nav_doc(),
           opf_xml=opf(extra_meta='<meta property="rendition:layout">pre-paginated</meta>'))

    # EPUB 2 book with an NCX page map.
    _build(path('ncx_pagemap.epub'),
           [CHAPTER.format(body=f'<p>{ENGLISH * 200}</p>'),
            CHAPTER.format(body=f'<p>{ENGLISH * 200}</p>')],
           nav=nav_doc(), opf_xml=opf(epub2=True), ncx=ncx_doc(page_map=list(range(1, 41))))

    # A page-list that is far too short to describe the whole book.
    _build(path('truncated_pagelist.epub'),
           [CHAPTER.format(body=f'<p>{ENGLISH * 2000}</p>'),
            CHAPTER.format(body=f'<p>{ENGLISH * 2000}</p>')],
           nav=nav_doc(page_list=list(range(1, 13))))

    # A sparse page-list: every tenth page of a long book.
    _build(path('sparse_pagelist.epub'),
           [CHAPTER.format(body=f'<p>{ENGLISH * 2000}</p>'),
            CHAPTER.format(body=f'<p>{ENGLISH * 2000}</p>')],
           nav=nav_doc(page_list=list(range(10, 400, 10))))

    # Adobe page-map.xml, which Calibre's TOC parser does not understand.
    _build(path('pagemap.epub'),
           [CHAPTER.format(body=f'<p>{ENGLISH * 200}</p>'),
            CHAPTER.format(body=f'<p>{ENGLISH * 200}</p>')],
           nav=nav_doc(),
           opf_xml=opf(extra_manifest=(
               '    <item id="pm" href="page-map.xml" '
               'media-type="application/oebps-page-map+xml"/>')),
           extra={'page-map.xml': page_map_doc(range(1, 26))})

    # Ruby annotations: the furigana text must not be counted as extra text.
    ruby = ('<p>' + ''.join(
        '<ruby>漢<rt>かん</rt></ruby>字<ruby>語<rt>ご</rt></ruby> ' for _ in range(30))
        + '</p>')
    plain = '<p>' + '漢字語 ' * 30 + '</p>'
    _build(path('ruby.epub'),
           [CHAPTER.format(body=ruby), CHAPTER.format(body=ruby)],
           nav=nav_doc(), opf_xml=opf(lang='ja'))
    _build(path('no_ruby.epub'),
           [CHAPTER.format(body=plain), CHAPTER.format(body=plain)],
           nav=nav_doc(), opf_xml=opf(lang='ja'))

    # Mixed Korean/English text and a useless "und" language tag.
    mixed_body = (KOREAN * 30) + ' ' + (ENGLISH * 30)
    _build(path('mixed.epub'),
           [CHAPTER.format(body=f'<p>{mixed_body}</p>'),
            CHAPTER.format(body=f'<p>{mixed_body}</p>')],
           nav=nav_doc(), opf_xml=opf(lang='ko'))
    _build(path('und_language.epub'),
           [CHAPTER.format(body=f'<p>{KOREAN * 200}</p>'),
            CHAPTER.format(body=f'<p>{KOREAN * 200}</p>')],
           nav=nav_doc(), opf_xml=opf(lang='und'))

    return directory
