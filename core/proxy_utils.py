"""Proxy utility functions for Chinese API services."""

import os


def disable_proxy_for_china() -> dict:
    """Disable proxy for Chinese API calls.

    Returns the original proxy settings so they can be restored later.
    """
    original_proxies = {
        'HTTP_PROXY': os.environ.get('HTTP_PROXY'),
        'HTTPS_PROXY': os.environ.get('HTTPS_PROXY'),
        'http_proxy': os.environ.get('http_proxy'),
        'https_proxy': os.environ.get('https_proxy'),
    }
    for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
        if key in os.environ:
            del os.environ[key]
    return original_proxies


def restore_proxy(original_proxies: dict) -> None:
    """Restore original proxy settings."""
    for key, value in original_proxies.items():
        if value is not None:
            os.environ[key] = value
