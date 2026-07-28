from app.opportunities.domain.canonical_url import canonicalize_url


def test_strips_www_and_lowercases_host() -> None:
    a = canonicalize_url("https://WWW.Chrono24.fr/watch/123")
    b = canonicalize_url("https://chrono24.fr/watch/123")
    assert a == b


def test_strips_tracking_params() -> None:
    a = canonicalize_url("https://chrono24.fr/watch/123?utm_source=newsletter")
    b = canonicalize_url("https://chrono24.fr/watch/123?gclid=abc123")
    c = canonicalize_url("https://chrono24.fr/watch/123")
    assert a == b == c


def test_strips_trailing_slash() -> None:
    assert canonicalize_url("https://chrono24.fr/watch/123/") == canonicalize_url(
        "https://chrono24.fr/watch/123"
    )


def test_sorts_remaining_query_params() -> None:
    a = canonicalize_url("https://chrono24.fr/watch?size=41&color=blue")
    b = canonicalize_url("https://chrono24.fr/watch?color=blue&size=41")
    assert a == b


def test_keeps_meaningful_params_distinct() -> None:
    a = canonicalize_url("https://chrono24.fr/watch?id=1")
    b = canonicalize_url("https://chrono24.fr/watch?id=2")
    assert a != b


def test_strips_fragment() -> None:
    assert canonicalize_url("https://chrono24.fr/watch#gallery") == canonicalize_url(
        "https://chrono24.fr/watch"
    )
