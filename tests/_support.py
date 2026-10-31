"""Shared paths for the test suite.

The plugin payload lives in ``plugin/`` so it can be zipped as-is. Adding that
directory to ``sys.path`` lets the pure tests import ``core`` directly.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_DIR = ROOT / 'plugin'

if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))
