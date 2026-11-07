"""Test layers for local runs and CI.

``browser`` tests drive real Chromium through Playwright (``pytest -m browser``);
everything else is fast and needs no browser (``pytest -m "not browser"``).
A test is a browser test when its module is named ``*_browser.py`` or its own
body uses Playwright or requests a PDF export (the runtime renders PDFs with
Chromium and merges them with poppler); fixtures follow the naming convention.
"""
import inspect

import pytest

BROWSER_HINTS = ('playwright', "'format': 'pdf'", '"format": "pdf"')


def pytest_collection_modifyitems(items):
    for item in items:
        module = getattr(item.module, '__name__', '') if getattr(item, 'module', None) else ''
        try:
            source = inspect.getsource(item.function)
        except (OSError, TypeError, AttributeError):
            source = ''
        if module.endswith('_browser') or any(hint in source for hint in BROWSER_HINTS):
            item.add_marker(pytest.mark.browser)
