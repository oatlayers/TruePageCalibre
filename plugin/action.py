"""Calibre interface action for Accurate Page Count."""

import os

from qt.core import QIcon, QMenu, QMessageBox, QPixmap

from calibre.gui2 import error_dialog, info_dialog, warning_dialog
from calibre.gui2.actions import InterfaceAction

from calibre_plugins.accurate_page_count.config import prefs
from calibre_plugins.accurate_page_count.core import (
    calibration_samples, calibration_summary, fit_calibration,
    normalize_calibration, recalibrate_results, settings_from_prefs,
)


class AccuratePageCountAction(InterfaceAction):

    name = 'Accurate Page Count'
    action_spec = (
        'Count pages',
        'images/page.png',
        'Count print pages accurately using embedded pagination or a language-aware estimate',
        None,
    )
    action_type = 'current'

    def genesis(self):
        self._load_icon()
        self.qaction.triggered.connect(self.count_selected)
        self.menu = QMenu(self.gui)
        self.menu.addAction('Count pages for selected books', self.count_selected)
        self.menu.addAction('Count pages for all books', self.count_all)
        self.menu.addSeparator()
        self.menu.addAction('Configure Accurate Page Count...', self.configure)
        self.qaction.setMenu(self.menu)

    def _load_icon(self):
        """Load the toolbar icon from this plugin's ZIP archive."""
        try:
            data = self.load_resources(['images/page.png']).get('images/page.png')
        except (AttributeError, OSError, ValueError):
            return
        if not data:
            return
        pixmap = QPixmap()
        if not pixmap.loadFromData(data, 'PNG'):
            return
        icon = QIcon(pixmap)
        self.qaction.setIcon(icon)
        self.menuless_qaction.setIcon(icon)

    def location_selected(self, loc):
        self.qaction.setEnabled(loc == 'library')

    def configure(self):
        self.interface_action_base_plugin.do_user_config(parent=self.gui)

    def count_selected(self):
        rows = self.gui.library_view.selectionModel().selectedRows()
        book_ids = [self.gui.library_view.model().id(row) for row in rows]
        if not book_ids:
            return self.count_all()
        self._start(book_ids)

    def count_all(self):
        db = self.gui.current_db
        book_ids = list(db.new_api.all_book_ids())
        if not book_ids:
            return info_dialog(self.gui, 'Accurate Page Count',
                               'The library has no books.', show=True)
        answer = QMessageBox.question(
            self.gui,
            'Accurate Page Count',
            'Count pages for all %d books in this library?' % len(book_ids),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._start(book_ids)

    def _validate_column(self, db, column):
        try:
            entry = db.field_metadata[column]
        except Exception:
            entry = None
        if entry is None:
            error_dialog(
                self.gui, 'Column not found',
                'The target column %s does not exist in this library.\n\n'
                'Create an integer custom column (for example #pages) first.' % column,
                show=True,
            )
            return False
        if entry.get('datatype') != 'int':
            error_dialog(
                self.gui, 'Wrong column type',
                'The target column %s is not an integer column.' % column,
                show=True,
            )
            return False
        return True

    def _book_title_and_language(self, db, book_id):
        """Return (title, language) for a book.

        ``get_metadata()`` builds a complete metadata object for a book, which
        is needlessly slow when only the title and the language are needed.
        Reading the two fields directly keeps the GUI responsive for large
        libraries.
        """
        title = ''
        language = ''
        try:
            title = db.new_api.field_for('title', book_id) or ''
        except Exception:
            title = ''
        try:
            languages = db.new_api.field_for('languages', book_id) or ()
        except Exception:
            languages = ()
        if isinstance(languages, str):
            language = languages
        else:
            try:
                language = languages[0]
            except (TypeError, IndexError):
                language = ''
        return str(title), str(language)

    def _start(self, book_ids):
        db = self.gui.current_db
        column = (prefs['column'] or '#pages').strip()
        if not self._validate_column(db, column):
            return

        settings = settings_from_prefs(prefs)
        overwrite = bool(prefs['overwrite_existing'])
        tasks = []
        skipped = 0
        for book_id in book_ids:
            try:
                formats = list(db.new_api.formats(book_id) or ())
            except Exception:
                skipped += 1
                continue

            ordered = [fmt for fmt in ('EPUB', 'PDF') if fmt in formats]
            ordered += [fmt for fmt in formats if fmt not in ('EPUB', 'PDF')]
            if not ordered:
                skipped += 1
                continue

            if not overwrite:
                try:
                    current = db.new_api.field_for(column, book_id)
                except Exception:
                    current = None
                if current not in (None, '', 0):
                    skipped += 1
                    continue

            paths = []
            used_formats = []
            for fmt in ordered:
                try:
                    path = db.new_api.format_abspath(book_id, fmt)
                except Exception:
                    path = None
                if path and os.path.exists(path):
                    paths.append(path)
                    used_formats.append(fmt)
            if not paths:
                skipped += 1
                continue

            title, language = self._book_title_and_language(db, book_id)
            tasks.append({
                'book_id': book_id,
                'title': title or str(book_id),
                'language': language,
                'formats': used_formats,
                'paths': paths,
            })

        if not tasks:
            return info_dialog(
                self.gui, 'Accurate Page Count',
                'No selected books have a readable EPUB or PDF format.',
                show=True,
            )

        self._job_column = column
        self._job_library_id = str(db.library_id)
        self._job_skipped = skipped
        self._job_results = {}
        self._failed_jobs = []
        self._jobs_remaining = 0

        chunks = self._split_tasks(tasks)
        self._jobs_remaining = len(chunks)
        for chunk in chunks:
            args = [
                'calibre_plugins.accurate_page_count.worker',
                'count_books',
                (chunk, settings),
            ]
            try:
                self.gui.job_manager.run_job(
                    self.Dispatcher(self._count_done),
                    'arbitrary_n',
                    args=args,
                    description='Accurate Page Count (%d books)' % len(chunk),
                )
            except Exception:
                # The batch was never started, so no callback will arrive for
                # it. Account for it here, otherwise the results would never
                # be written.
                self._jobs_remaining -= 1
                self._failed_jobs.append(None)
        if self._jobs_remaining == 0:
            # Every batch failed to start. Write the (empty) result so the
            # user gets the error report instead of silence.
            return self._write_results()
        self.gui.status_bar.show_message(
            'Counting pages for %d books...' % len(tasks), 5000)

    def _worker_count(self):
        """How many jobs Calibre is willing to run at the same time."""
        try:
            pool_size = int(self.gui.job_manager.server.pool_size)
        except Exception:
            pool_size = 1
        return max(1, min(pool_size, 8))

    def _split_tasks(self, tasks):
        """Split the books into chunks that can be counted in parallel.

        The chunks are balanced by file size, because a handful of very large
        EPUBs would otherwise decide how long the whole run takes. The books
        are handed out largest first, each one going to the chunk that is
        currently the smallest. That keeps the slowest chunk as fast as it
        can be, which is what decides how long the whole run takes.
        """
        count = min(self._worker_count(), len(tasks))
        if count <= 1:
            return [tasks]

        def size_of(task):
            total = 0
            for path in task.get('paths') or ():
                try:
                    total += os.path.getsize(path)
                except OSError:
                    pass
            return total

        sized = sorted(((size_of(task), task) for task in tasks),
                       key=lambda item: item[0], reverse=True)
        chunks = [[] for _ in range(count)]
        totals = [0] * count
        for size, task in sized:
            # The chunk with the smallest total wins. Books of equal size are
            # spread over the emptiest chunk, so that identical files do not
            # all land in the same batch.
            index = min(range(count), key=lambda i: (totals[i], len(chunks[i])))
            chunks[index].append(task)
            totals[index] += size
        return [chunk for chunk in chunks if chunk]

    def _count_done(self, job):
        if job.failed:
            self._failed_jobs.append(job)
        else:
            result = job.result
            if isinstance(result, dict):
                self._job_results.update(result)
            else:
                self._failed_jobs.append(job)
        self._jobs_remaining -= 1
        if self._jobs_remaining > 0:
            return
        return self._write_results()

    def _write_results(self):
        result = self._job_results
        db = self.gui.current_db.new_api
        if str(db.library_id) != self._job_library_id:
            return error_dialog(
                self.gui, 'Library changed',
                'The active library changed while pages were being counted. '
                'The results were not written.',
                show=True,
            )

        settings = settings_from_prefs(prefs)
        models = normalize_calibration(prefs['calibration'])
        calibrated_count = 0
        if settings['calibrate_estimates']:
            # Books with real embedded pagination are a calibration set for
            # the books that have none. Fitting after the count means the
            # estimates in this very run can use what was learned.
            new_models = fit_calibration(calibration_samples(result))
            if new_models:
                # Do not let a small "count selected" run replace a model
                # fitted from the whole library.
                for language, model in new_models.items():
                    old = models.get(language) or {}
                    if int(model.get('n') or 0) >= int(old.get('n') or 0):
                        models[language] = model
                prefs['calibration'] = models
            calibrated_count = recalibrate_results(result, models, settings)
        else:
            calibrated_count = sum(
                1 for item in result.values()
                if isinstance(item, dict) and item.get('calibrated'))

        column = self._job_column
        updates = {}
        errors = {}
        sources = {}
        for book_id, item in result.items():
            if item.get('error'):
                errors[book_id] = item['error']
                continue
            pages = item.get('pages')
            if not pages:
                errors[book_id] = 'No page count produced'
                continue
            source = item.get('source') or 'unknown'
            sources[source] = sources.get(source, 0) + 1
            try:
                current = db.field_for(column, book_id)
            except Exception:
                current = None
            if current != pages:
                updates[book_id] = int(pages)

        if updates:
            try:
                db.set_field(column, updates)
            except Exception as err:
                return error_dialog(
                    self.gui, 'Could not update column',
                    'Failed to write page counts to %s.' % column,
                    det_msg='%s: %s' % (type(err).__name__, err),
                    show=True,
                )
            try:
                self.gui.library_view.model().refresh_ids(list(updates))
            except Exception:
                pass

        print_list_count = sum(v for k, v in sources.items() if k == 'print-page-list')
        print_map_count = sum(v for k, v in sources.items() if k == 'print-page-map')
        print_adobe_count = sum(
            v for k, v in sources.items() if k == 'print-page-map-adobe')
        print_break_count = sum(v for k, v in sources.items() if k == 'print-pagebreak')
        print_count = (print_list_count + print_map_count
                       + print_adobe_count + print_break_count)
        pdf_count = sum(v for k, v in sources.items() if k == 'pdf')
        fixed_count = sum(v for k, v in sources.items() if k == 'fixed-layout')
        image_count = sum(v for k, v in sources.items() if k == 'image-pages')
        estimate_count = sum(v for k, v in sources.items() if k.startswith('estimate-'))
        other_count = sum(v for k, v in sources.items()
                          if k not in ('print-page-list', 'print-page-map',
                                       'print-page-map-adobe', 'print-pagebreak',
                                       'pdf', 'fixed-layout', 'image-pages')
                          and not k.startswith('estimate-'))

        lines = [
            'Books processed: %d' % len(result),
            'Column updated: %d' % len(updates),
            'Unchanged: %d' % (len(result) - len(updates) - len(errors)),
            'Skipped before counting: %d' % self._job_skipped,
        ]
        if print_count:
            lines.append(
                'Embedded print pagination: %d (page-list %d, page-map %d, '
                'Adobe page-map %d, pagebreak %d)'
                % (print_count, print_list_count, print_map_count,
                   print_adobe_count, print_break_count)
            )
        if pdf_count:
            lines.append('PDF real page counts: %d' % pdf_count)
        if fixed_count:
            lines.append('Fixed-layout pages: %d' % fixed_count)
        if image_count:
            lines.append('Image-only pages: %d' % image_count)
        if estimate_count:
            extra = ''
            if calibrated_count:
                extra = ' (%d calibrated)' % calibrated_count
            lines.append('Text estimates: %d%s' % (estimate_count, extra))
        if other_count:
            lines.append('Other formats: %d' % other_count)
        if models and settings['calibrate_estimates']:
            summary = calibration_summary(models)
            if summary:
                lines.append('Estimate calibration: %s' % summary)
        if errors:
            lines.append('Errors: %d' % len(errors))
        if self._failed_jobs:
            lines.append('Failed batches: %d' % len(self._failed_jobs))

        details = []
        for book_id, error in list(errors.items())[:50]:
            details.append('Book %s: %s' % (book_id, error))

        if not prefs['show_report'] and not errors and not self._failed_jobs:
            self.gui.status_bar.show_message(
                'Accurate Page Count: updated %d books.' % len(updates), 5000)
            return

        if errors or self._failed_jobs:
            for job in self._failed_jobs[:3]:
                if job is None:
                    details.append('A batch of books could not be started.')
                    continue
                try:
                    log = job.details or ''
                except Exception:
                    log = ''
                details.append('A batch of books could not be counted (exit code %s); '
                               'those books keep their previous value.'
                               % getattr(job, 'returncode', '?'))
                if log.strip():
                    details.append(log.strip()[-2000:])
            return warning_dialog(
                self.gui, 'Accurate Page Count finished with errors',
                '\n'.join(lines),
                det_msg='\n'.join(details),
                show=True,
            )
        return info_dialog(
            self.gui, 'Accurate Page Count',
            '\n'.join(lines),
            show=True,
        )
