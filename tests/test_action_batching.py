"""Tests for the parallel batching used by the Calibre action.

These need the Qt/Calibre libraries, so they are skipped when Calibre is not
importable.
"""

import os
import sys
import types
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TESTS_DIR)

from _support import PLUGIN_DIR  # noqa: E402


def _install_plugin_alias():
    """Make ``calibre_plugins.accurate_page_count`` point at the source tree.

    Inside Calibre the plugin lives in a zip and is imported under that name,
    but in the source tree it is an ordinary directory. This alias lets the
    test import the very same modules the plugin ships.
    """
    package = types.ModuleType('calibre_plugins')
    package.__path__ = []
    sys.modules['calibre_plugins'] = package
    module = types.ModuleType('calibre_plugins.accurate_page_count')
    module.__path__ = [str(PLUGIN_DIR)]
    sys.modules['calibre_plugins.accurate_page_count'] = module


try:
    _install_plugin_alias()
    from calibre_plugins.accurate_page_count.action import AccuratePageCountAction
    HAVE_CALIBRE = True
except Exception:  # pragma: no cover - depends on the environment
    HAVE_CALIBRE = False


class _Stub:
    """Stands in for the action, without needing a GUI."""

    def __init__(self, workers):
        self._workers = workers

    def _worker_count(self):
        return self._workers


def split(tasks, workers):
    return AccuratePageCountAction._split_tasks(_Stub(workers), tasks)


def make_tasks(count):
    return [{'book_id': i, 'paths': ['book-%d.epub' % i]} for i in range(count)]


@unittest.skipUnless(HAVE_CALIBRE, 'Calibre is not importable')
class SplitTasksTests(unittest.TestCase):

    def test_single_worker_gives_one_chunk(self):
        chunks = split(make_tasks(3), 1)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(len(chunks[0]), 3)

    def test_all_tasks_are_kept(self):
        tasks = make_tasks(50)
        chunks = split(tasks, 4)
        seen = []
        for chunk in chunks:
            seen.extend(chunk)
        self.assertEqual(len(seen), 50)
        self.assertEqual({t['book_id'] for t in seen},
                         {t['book_id'] for t in tasks})

    def test_no_duplicate_tasks(self):
        chunks = split(make_tasks(50), 4)
        seen = []
        for chunk in chunks:
            seen.extend(chunk)
        self.assertEqual(len(seen), len({t['book_id'] for t in seen}))

    def test_chunk_count_does_not_exceed_task_count(self):
        chunks = split(make_tasks(3), 8)
        self.assertEqual(len(chunks), 3)
        self.assertTrue(all(chunk for chunk in chunks))

    def test_more_workers_than_tasks(self):
        chunks = split(make_tasks(1), 8)
        self.assertEqual(len(chunks), 1)

    def test_empty_task_list(self):
        self.assertEqual(split([], 4), [[]])

    def test_chunks_are_balanced_by_size(self):
        # No single book dominates, so the batches should end up nearly equal.
        sizes = [100, 90, 80, 70, 60, 50, 40, 30, 20, 10]
        totals = self._split_with_sizes(sizes, 3)
        self.assertEqual(len(totals), 3)
        self.assertLessEqual(max(totals) - min(totals), 20,
                             'chunks are unbalanced: %r' % totals)

    def test_one_huge_book_does_not_slow_every_batch(self):
        # A single huge book has to go somewhere, but it must not drag the
        # other batches down with it.
        sizes = [1000] + [10] * 11
        totals = self._split_with_sizes(sizes, 3)
        self.assertEqual(len(totals), 3)
        # The huge book ends up on its own, the other batches stay small.
        self.assertEqual(max(totals), 1000)
        self.assertLessEqual(sorted(totals)[1], 60)

    def test_slowest_batch_is_close_to_the_ideal(self):
        sizes = [97, 61, 43, 29, 13, 7, 5, 2, 91, 53, 11, 3]
        totals = self._split_with_sizes(sizes, 4)
        ideal = max(max(sizes), sum(sizes) / float(len(totals)))
        self.assertLessEqual(max(totals), ideal * 1.10,
                             'slowest batch %r is far from the ideal %r'
                             % (max(totals), ideal))

    def _split_with_sizes(self, sizes, workers):
        tasks = make_tasks(len(sizes))
        original = os.path.getsize

        def fake_getsize(path):
            return sizes[int(path.split('-')[1].split('.')[0])]

        os.path.getsize = fake_getsize
        try:
            chunks = split(tasks, workers)
        finally:
            os.path.getsize = original
        return [sum(sizes[t['book_id']] for t in chunk) for chunk in chunks]


if __name__ == '__main__':
    unittest.main()
