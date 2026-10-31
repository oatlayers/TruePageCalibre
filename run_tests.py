"""Run the test suite.

Works with a normal Python interpreter and with the Python that ships with
Calibre::

    python run_tests.py
    calibre-debug -e run_tests.py

Tests that need Calibre are skipped automatically when Calibre cannot be
imported.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.join(HERE, 'tests')
PLUGIN = os.path.join(HERE, 'plugin')


def main():
    sys.path.insert(0, PLUGIN)
    suite = unittest.TestLoader().discover(TESTS, top_level_dir=TESTS)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
