"""Configuration dialog for TruePageCalibre."""

from qt.core import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QPushButton,
    QSpinBox, QVBoxLayout, QWidget,
)

from calibre.gui2 import error_dialog
from calibre.utils.config import JSONConfig

from calibre_plugins.accurate_page_count.core import (
    DEFAULT_SETTINGS, calibration_summary, normalize_calibration,
)


# Keep the legacy config path so existing users keep their settings and
# calibration after the product rename.
prefs = JSONConfig('plugins/accurate_page_count')
prefs.defaults.update({
    'column': '#pages',
    'prefer_print_pages': True,
    'include_front_matter': True,
    'calibrate_estimates': True,
    'calibration': {},
    'min_page_list_entries': 10,
    'chars_per_page_korean': 300,
    'chars_per_page_cjk': 700,
    'chars_per_page_english': 1500,
    'chars_per_page_other': 1500,
    'overwrite_existing': True,
    'show_report': True,
})


def _gui():
    try:
        from calibre.gui2.ui import get_gui
        return get_gui()
    except Exception:
        return None


def _int_columns():
    gui = _gui()
    db = getattr(gui, 'current_db', None)
    if db is None:
        return []
    try:
        field_metadata = db.field_metadata
    except Exception:
        return []
    try:
        keys = list(field_metadata.custom_field_keys())
    except Exception:
        keys = [key for key in field_metadata if str(key).startswith('#')]
    columns = []
    for key in keys:
        try:
            entry = field_metadata[key]
        except Exception:
            continue
        if entry.get('datatype') == 'int':
            columns.append((key, entry.get('name') or key))
    columns.sort(key=lambda item: item[1].lower())
    return columns


class ConfigWidget(QWidget):

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self._calibration_cleared = False
        layout = QVBoxLayout(self)

        intro = QLabel(
            'TruePageCalibre prefers a book\'s embedded print pagination '
            '(EPUB page-list, NCX page-map, Adobe page-map or pagebreak '
            'markers) and otherwise estimates from the text using a '
            'language-aware characters-per-page value.'
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()

        self.column = QComboBox(self)
        columns = _int_columns()
        current = prefs['column']
        seen = set()
        for key, name in columns:
            self.column.addItem('%s (%s)' % (name, key), key)
            seen.add(key)
        if current not in seen:
            self.column.addItem(current, current)
        index = self.column.findData(current)
        if index >= 0:
            self.column.setCurrentIndex(index)
        form.addRow('Target integer column:', self.column)

        self.builtin_warning = QLabel(
            'This is Calibre\'s built-in Pages column. Calibre maintains that '
            'column itself and can overwrite the values with its own '
            'estimate, so a custom integer column is the safer choice.'
        )
        self.builtin_warning.setWordWrap(True)
        self.builtin_warning.setVisible(False)
        form.addRow('', self.builtin_warning)
        self.column.currentIndexChanged.connect(self._update_builtin_warning)

        self.prefer_print_pages = QCheckBox(
            'Use embedded print pagination when the EPUB provides it (recommended)'
        )
        self.prefer_print_pages.setChecked(bool(prefs['prefer_print_pages']))
        form.addRow('', self.prefer_print_pages)

        self.include_front_matter = QCheckBox(
            'Include roman-numbered front matter in embedded page counts'
        )
        self.include_front_matter.setChecked(bool(prefs['include_front_matter']))
        self.include_front_matter.setToolTip(
            'A book with pages i-xviii and 1-300 has 318 printed pages. '
            'Turn this off to use the last arabic page number (300) instead.'
        )
        form.addRow('', self.include_front_matter)

        self.min_page_list_entries = QSpinBox(self)
        self.min_page_list_entries.setRange(2, 500)
        self.min_page_list_entries.setValue(int(prefs['min_page_list_entries']))
        self.min_page_list_entries.setToolTip(
            'Ignore tiny embedded page-lists or pagebreak sets (for example a '
            '3-page sample) and estimate instead.'
        )
        form.addRow('Minimum embedded pagination entries:', self.min_page_list_entries)

        self.calibrate = QCheckBox(
            'Calibrate text estimates from this library\'s embedded pagination'
        )
        self.calibrate.setChecked(bool(prefs['calibrate_estimates']))
        self.calibrate.setToolTip(
            'After a count, books with real embedded print pagination are used '
            'to learn how many characters this library\'s books hold per page. '
            'The learned values are stored and used for books without embedded '
            'pagination.'
        )
        form.addRow('', self.calibrate)

        self.calibration_label = QLabel(self)
        self.calibration_label.setWordWrap(True)
        form.addRow('Calibration:', self.calibration_label)

        self.clear_calibration = QPushButton('Clear stored calibration', self)
        self.clear_calibration.clicked.connect(self._clear_calibration)
        form.addRow('', self.clear_calibration)

        self.korean = QSpinBox(self)
        self.korean.setRange(50, 10000)
        self.korean.setValue(int(prefs['chars_per_page_korean']))
        form.addRow('Korean characters per page:', self.korean)

        self.cjk = QSpinBox(self)
        self.cjk.setRange(50, 10000)
        self.cjk.setValue(int(prefs['chars_per_page_cjk']))
        form.addRow('Chinese/Japanese characters per page:', self.cjk)

        self.english = QSpinBox(self)
        self.english.setRange(50, 10000)
        self.english.setValue(int(prefs['chars_per_page_english']))
        form.addRow('English characters per page:', self.english)

        self.other = QSpinBox(self)
        self.other.setRange(50, 10000)
        self.other.setValue(int(prefs['chars_per_page_other']))
        form.addRow('Other languages characters per page:', self.other)

        self.overwrite = QCheckBox('Overwrite existing page counts')
        self.overwrite.setChecked(bool(prefs['overwrite_existing']))
        form.addRow('', self.overwrite)

        self.show_report = QCheckBox('Show a summary when counting finishes')
        self.show_report.setChecked(bool(prefs['show_report']))
        form.addRow('', self.show_report)

        layout.addLayout(form)

        note = QLabel(
            'The characters-per-page values are the fallback for books without '
            'embedded print pagination. Calibration learns from books that do '
            'have it, so the defaults do not have to fit every book. '
            'Korean novels typically hold 280-360 non-whitespace characters '
            'per printed page; trade English books 1000-2100.'
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QHBoxLayout()
        reset = QPushButton('Restore recommended values', self)
        reset.clicked.connect(self.restore_defaults)
        buttons.addWidget(reset)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        layout.addStretch(1)

        self._update_builtin_warning()
        self._update_calibration_label()

    def _update_builtin_warning(self):
        """Warn when Calibre's own Pages column is used as the target."""
        self.builtin_warning.setVisible(self.column.currentData() == 'pages')

    def _update_calibration_label(self):
        if self._calibration_cleared:
            self.calibration_label.setText(
                'Calibration will be cleared when this dialog is saved.')
            return
        models = normalize_calibration(prefs['calibration'])
        if models:
            self.calibration_label.setText(calibration_summary(models))
        else:
            self.calibration_label.setText(
                'Not calibrated yet. Run "Count pages for all books" once; '
                'books with embedded print pagination will be used '
                'automatically.')

    def _clear_calibration(self):
        self._calibration_cleared = True
        self._update_calibration_label()

    def restore_defaults(self):
        self.prefer_print_pages.setChecked(DEFAULT_SETTINGS['prefer_print_pages'])
        self.include_front_matter.setChecked(
            DEFAULT_SETTINGS['include_front_matter'])
        self.calibrate.setChecked(DEFAULT_SETTINGS['calibrate_estimates'])
        self.min_page_list_entries.setValue(DEFAULT_SETTINGS['min_page_list_entries'])
        self.korean.setValue(DEFAULT_SETTINGS['chars_per_page_korean'])
        self.cjk.setValue(DEFAULT_SETTINGS['chars_per_page_cjk'])
        self.english.setValue(DEFAULT_SETTINGS['chars_per_page_english'])
        self.other.setValue(DEFAULT_SETTINGS['chars_per_page_other'])

    def validate(self):
        column = self.column.currentData()
        if not column:
            error_dialog(self, 'No column selected',
                         'Select an integer custom column to store page counts.',
                         show=True)
            return False
        gui = _gui()
        db = getattr(gui, 'current_db', None)
        if db is not None:
            try:
                entry = db.field_metadata[column]
            except Exception:
                entry = None
            if entry is None:
                error_dialog(self, 'Column not found',
                             'The column %s does not exist in this library.' % column,
                             show=True)
                return False
            if entry.get('datatype') != 'int':
                error_dialog(self, 'Wrong column type',
                             '%s is not an integer column.' % column, show=True)
                return False
        return True

    def save_settings(self):
        prefs['column'] = self.column.currentData() or '#pages'
        prefs['prefer_print_pages'] = self.prefer_print_pages.isChecked()
        prefs['include_front_matter'] = self.include_front_matter.isChecked()
        prefs['calibrate_estimates'] = self.calibrate.isChecked()
        if self._calibration_cleared:
            prefs['calibration'] = {}
        prefs['min_page_list_entries'] = self.min_page_list_entries.value()
        prefs['chars_per_page_korean'] = self.korean.value()
        prefs['chars_per_page_cjk'] = self.cjk.value()
        prefs['chars_per_page_english'] = self.english.value()
        prefs['chars_per_page_other'] = self.other.value()
        prefs['overwrite_existing'] = self.overwrite.isChecked()
        prefs['show_report'] = self.show_report.isChecked()
