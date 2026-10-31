# Contributing

Thanks for considering a contribution to TruePageCalibre. This is a small
Calibre plugin, and focused bug reports and pull requests are very welcome.

## Reporting bugs

Please include:

- your Calibre version and operating system;
- the TruePageCalibre version (shown in **Preferences → Plugins**);
- the target custom column and its type;
- the source reported in the completion dialog (for example `print-page-list`
  or `estimate-eng`);
- the steps that reproduce the problem and the result you expected;
- any traceback from Calibre's job details.

Do **not** upload copyrighted books. A minimal EPUB built with
`tests/epub_fixtures.py`, or a description of the EPUB's pagination markup, is
usually enough to reproduce a counting bug.

## Development setup

- Python 3.10 or newer for the pure unit tests.
- Calibre 6.0 or newer for the Calibre-backed tests and for manual testing.
- No third-party Python packages are required.

The plugin payload lives in `plugin/`. Its contents form the root of the ZIP
that Calibre installs, and `build_plugin.py` packages them.

## Running tests

Run the pure tests with any Python 3:

```powershell
python -m unittest discover -s tests -v
```

or:

```powershell
python run_tests.py
```

Calibre-backed tests are skipped automatically when Calibre cannot be imported.
To run them with Calibre's bundled Python:

```powershell
& "C:\Program Files\Calibre2\calibre-debug.exe" -e run_tests.py
```

On macOS:

```sh
/Applications/calibre.app/Contents/MacOS/calibre-debug -e run_tests.py
```

On Linux:

```sh
calibre-debug -e run_tests.py
```

## Building the plugin

```powershell
python build_plugin.py
```

This writes `dist/TruePageCalibre.zip`. The ZIP is a build artifact and is
ignored by git. Do not commit it.

## Code guidelines

- `plugin/core.py` must stay free of Qt and GUI imports so it remains
  unit-testable.
- Calibre imports belong inside the functions that need them, or in the GUI
  modules (`plugin/action.py`, `plugin/config.py`).
- Keep the code compatible with Python 3.10 and newer.
- Follow the existing style: four-space indentation, single-quoted strings and
  lines around 79 characters where practical.
- Add or update tests for any counting, pagination or calibration change.
- Update `README.md` and `CHANGELOG.md` when behaviour changes.
- `assets/logo.svg` is the source of truth for the icon. Export
  `plugin/images/page.png` at 128 x 128 and `assets/logo.png` at 512 x 512
  after changing it.

## Pull requests

- Keep each pull request focused on one change.
- Explain the behaviour before and after, and any effect on accuracy.
- List the test commands you ran.
- If a change affects page counts, include a representative example (book
  type, embedded pagination source, previous count, new count).
