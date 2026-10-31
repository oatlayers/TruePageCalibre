"""Build the Calibre plugin ZIP file.

Usage::

    python build_plugin.py

The installable ZIP is written to ``dist/TruePageCalibre.zip``. The contents
of ``plugin/`` form the root of that ZIP; ``LICENSE`` is added from the
repository root. The plugin import marker keeps the legacy
``accurate_page_count`` name so existing installations keep working.
"""

from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent
PLUGIN_DIR = ROOT / 'plugin'
OUTPUT = ROOT / 'dist' / 'TruePageCalibre.zip'

PLUGIN_FILES = (
    '__init__.py',
    'action.py',
    'config.py',
    'core.py',
    'worker.py',
    'plugin-import-name-accurate_page_count.txt',
    'images/page.png',
)


def main():
    missing = [name for name in PLUGIN_FILES if not (PLUGIN_DIR / name).is_file()]
    if missing:
        raise SystemExit('Missing files: %s' % ', '.join(missing))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT.exists():
        OUTPUT.unlink()
    with zipfile.ZipFile(OUTPUT, 'w', zipfile.ZIP_DEFLATED) as z:
        for name in PLUGIN_FILES:
            z.write(PLUGIN_DIR / name, name)
        z.write(ROOT / 'LICENSE', 'LICENSE')
    with zipfile.ZipFile(OUTPUT) as z:
        print('Contents of %s:' % OUTPUT.name)
        for info in z.infolist():
            print('  %-45s %7d bytes' % (info.filename, info.file_size))
    print('\nWrote %s (%d bytes)' % (OUTPUT, OUTPUT.stat().st_size))


if __name__ == '__main__':
    main()
