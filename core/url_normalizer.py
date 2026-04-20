"""
URL Normalization Utility

Provides URL normalization for deduplication purposes by:
1. Stripping tracking parameters (utm_*, fbclid, gclid, etc.)
2. Normalizing scheme (https preferred)
3. Normalizing www/non-www
4. Removing fragment (#)
5. Sorting query parameters
"""

import re
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
from typing import Set


# Tracking parameters to strip from URLs
_TRACKING_PARAMS: Set[str] = {
    # Google Analytics / UTMs
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'utm_id',
    # Facebook
    'fbclid', 'fb_action_ids', 'fb_action_types', 'fb_source',
    # Google Click ID
    'gclid', 'gclsrc', 'gbraid', 'wbraid',
    # Microsoft
    'msclkid', 'msclickid',
    # Instagram
    'igshid', 'ig_rid',
    # Google Analytics
    '_ga', '_gid', '_gat', '_gl',
    # Twitter/X
    'ref', 'ref_src', 's', 't',
    # Reddit
    'ref_source', 'ref_share_url',
    # LinkedIn
    'refId', 'trackingId', 'trk',
    # Generic
    'source', 'feature', 'si', 'cn', 'sn', 'mc', 'mcd',
    # Product Hunt specific
    'via', 'share', 'utm',
    # YouTube
    'feature', 'si',
}


def normalize_url(url: str, strip_tracking: bool = True,
                  remove_fragment: bool = True,
                  prefer_https: bool = True,
                  normalize_www: bool = True) -> str:
    """
    Normalize a URL for deduplication purposes.

    Args:
        url: The URL to normalize
        strip_tracking: Remove tracking parameters (default: True)
        remove_fragment: Remove fragment/hash (default: True)
        prefer_https: Normalize to https (default: True)
        normalize_www: Normalize www/non-www (default: True)

    Returns:
        Normalized URL string

    Examples:
        >>> normalize_url("https://example.com/path?utm_source=google&id=123#section")
        'https://example.com/path?id=123'

        >>> normalize_url("http://www.example.com/")
        'https://example.com/'
    """
    if not url:
        return url

    try:
        # Parse URL
        parsed = urlparse(url)

        # Normalize scheme
        scheme = parsed.scheme
        if prefer_https and scheme in ('http', 'https'):
            scheme = 'https'

        # Normalize netloc (www handling)
        netloc = parsed.netloc.lower()
        if normalize_www:
            # Remove www prefix
            if netloc.startswith('www.'):
                netloc = netloc[4:]

        # Parse and filter query parameters
        query_params = parse_qsl(parsed.query, keep_blank_values=True)

        if strip_tracking:
            # Remove tracking parameters
            filtered_params = [
                (k, v) for k, v in query_params
                if k.lower() not in _TRACKING_PARAMS
            ]
        else:
            filtered_params = query_params

        # Sort query parameters for consistent ordering
        filtered_params.sort(key=lambda x: x[0])

        # Rebuild query string
        query = urlencode(filtered_params) if filtered_params else ''

        # Handle fragment
        fragment = '' if remove_fragment else parsed.fragment

        # Rebuild URL
        normalized = urlunparse((
            scheme,
            netloc,
            parsed.path,
            parsed.params,  # Rarely used, keep as-is
            query,
            fragment
        ))

        return normalized

    except Exception:
        # If parsing fails, return original URL
        return url


def normalize_url_list(urls: list, **kwargs) -> list:
    """
    Normalize a list of URLs.

    Args:
        urls: List of URLs to normalize
        **kwargs: Arguments passed to normalize_url

    Returns:
        List of normalized URLs
    """
    return [normalize_url(url, **kwargs) for url in urls]


def extract_base_url(url: str) -> str:
    """
    Extract the base URL (scheme + netloc) from a URL.

    Args:
        url: URL to extract from

    Returns:
        Base URL (e.g., 'https://example.com')
    """
    if not url:
        return url

    try:
        parsed = urlparse(url)
        scheme = parsed.scheme or 'https'
        netloc = parsed.netloc.lower()

        # Remove www prefix
        if netloc.startswith('www.'):
            netloc = netloc[4:]

        return f"{scheme}://{netloc}"
    except Exception:
        return url


def are_same_url(url1: str, url2: str, **kwargs) -> bool:
    """
    Check if two URLs are the same after normalization.

    Args:
        url1: First URL
        url2: Second URL
        **kwargs: Arguments passed to normalize_url

    Returns:
        True if URLs are the same after normalization
    """
    return normalize_url(url1, **kwargs) == normalize_url(url2, **kwargs)


def get_url_fingerprint(url: str, **kwargs) -> str:
    """
    Get a normalized URL for use as a deduplication fingerprint.

    Args:
        url: URL to fingerprint
        **kwargs: Arguments passed to normalize_url

    Returns:
        Normalized URL suitable for deduplication
    """
    return normalize_url(url, **kwargs)


# Platform-specific normalizers

def normalize_twitter_url(url: str) -> str:
    """Normalize Twitter/X URLs"""
    # Twitter/X specific handling
    normalized = normalize_url(url)

    # Remove /i/ redirect prefixes
    normalized = re.sub(r'^https?://(x\.com|twitter\.com)/i/', r'https://\1/', normalized)

    # Normalize x.com to twitter.com (or vice versa - here we use x.com)
    normalized = normalized.replace('https://twitter.com/', 'https://x.com/')

    return normalized


def normalize_reddit_url(url: str) -> str:
    """Normalize Reddit URLs"""
    normalized = normalize_url(url)

    # Remove /comments/ duplicate (Reddit sometimes has this)
    normalized = re.sub(r'/comments/comments/', '/comments/', normalized)

    # Remove old.reddit.com references
    normalized = normalized.replace('old.reddit.com', 'www.reddit.com')

    # Remove www prefix for reddit
    normalized = normalized.replace('https://www.reddit.com/', 'https://reddit.com/')

    return normalized


def normalize_product_hunt_url(url: str) -> str:
    """Normalize Product Hunt URLs"""
    normalized = normalize_url(url)

    # Product Hunt specific handling
    # Remove /posts/ duplicate if present
    normalized = re.sub(r'/posts/posts/', '/posts/', normalized)

    return normalized
