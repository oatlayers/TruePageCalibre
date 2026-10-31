"""Background worker executed by Calibre's job manager."""

from calibre_plugins.accurate_page_count.core import count_task


def count_books(tasks, settings, notification=lambda *args: None):
    """Count pages for every task and return {book_id: result}."""
    results = {}
    total = max(1, len(tasks))
    for index, task in enumerate(tasks):
        book_id = task.get('book_id')
        title = task.get('title') or str(book_id)
        try:
            notification(index / float(total), 'Counting pages: %s' % title[:80])
        except Exception:
            pass
        try:
            result = count_task(task, settings)
        except Exception as err:
            result = {
                'book_id': book_id,
                'error': '%s: %s' % (type(err).__name__, err),
            }
        results[book_id] = result
    try:
        notification(1.0, 'Finished counting pages')
    except Exception:
        pass
    return results
