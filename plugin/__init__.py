"""Calibre plugin definition for TruePageCalibre.

The import package and configuration path keep the legacy
``accurate_page_count`` name so existing installations and settings survive
the product rename.
"""

from calibre.customize import InterfaceActionBase


class TruePageCalibrePlugin(InterfaceActionBase):
    name = 'TruePageCalibre'
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
        'calibre_plugins.accurate_page_count.action:TruePageCalibreAction'
    )

    def is_customizable(self):
        return True

    def config_widget(self):
        from calibre_plugins.accurate_page_count.config import ConfigWidget
        return ConfigWidget()

    def save_settings(self, config_widget):
        config_widget.save_settings()
