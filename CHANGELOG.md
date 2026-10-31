# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2026-10-31

### Added

- SVG logo/icon artwork, with 128 px and 512 px PNG exports.
- The placeholder toolbar icon is replaced with a numbered, measured-page
  mark.

### Changed

- Renamed the project to TruePageCalibre. The Calibre plugin import name and
  settings path remain `accurate_page_count`, so existing settings and
  calibration are preserved.
- Source files now live under `plugin/`, brand artwork under `assets/`, and
  the built ZIP is written to `dist/`.

### Fixed

- The toolbar icon is now loaded from the plugin ZIP, so the numbered icon
  actually appears in Calibre.

## [0.3.0]

First version tracked in this changelog. It includes:

### Added

- Print page counts from EPUB 3 nav page-lists, EPUB 2 NCX page maps, Adobe
  `page-map.xml` files and pagebreak markers.
- Roman front matter handling, so pages i-xviii + 1-300 report 318 pages.
- Language-aware estimates for Korean, Chinese/Japanese, Latin and mixed-script
  books, including ruby-annotation filtering.
- Per-language calibration fitted from books that have real embedded
  pagination, with a flat-median fallback for small samples.
- Parallel counting, with batches balanced by file size.
- A configuration dialog for the target column, pagination preferences,
  characters-per-page values, calibration and reporting.
- Pure-Python unit tests plus Calibre-backed EPUB fixture tests.
