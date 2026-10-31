"""Calibre plugin definition for Accurate Page Count."""

from calibre.customize import InterfaceActionBase


class AccuratePageCountPlugin(InterfaceActionBase):
    name = 'Accurate Page Count'
    description = (
        'Counts print pages from an EPUB\'s embedded pagination (page-list, '
        'NCX page-map, Adobe page-map or pagebreaks) when available, otherwise '
        'uses a language-aware estimate calibrated from your own library. '
        'PDFs use their real page count.'
    )
    supported_platforms = ['windows', 'osx', 'linux']
    author = 'oatlayers'
    version = (0, 3, 0)
    minimum_calibre_version = (6, 0, 0)
    actual_plugin = (
        'calibre_plugins.accurate_page_count.action:AccuratePageCountAction'
    )

    def is_customizable(self):
        return True

    def config_widget(self):
        from calibre_plugins.accurate_page_count.config import ConfigWidget
        return ConfigWidget()

    def save_settings(self, config_widget):
        config_widget.save_settings()
