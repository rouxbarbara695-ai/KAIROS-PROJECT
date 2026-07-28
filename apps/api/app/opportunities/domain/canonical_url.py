from __future__ import annotations

import fnmatch
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Liste de configuration, pas une constante figée (docs/delivery/
# implementation-plan-kai-001-103.md §8). Les motifs supportent `*`.
DEFAULT_TRACKING_PARAM_PATTERNS = (
    "utm_*",
    "gclid",
    "fbclid",
    "ref",
    "mc_cid",
    "mc_eid",
)


def _is_tracking_param(name: str, patterns: tuple[str, ...]) -> bool:
    lowered = name.lower()
    return any(fnmatch.fnmatch(lowered, pattern) for pattern in patterns)


def canonicalize_url(
    url: str, tracking_param_patterns: tuple[str, ...] = DEFAULT_TRACKING_PARAM_PATTERNS
) -> str:
    """Canonicalise une URL pour la déduplication (KAI-103) :
    schéma/hôte en minuscules, retrait de `www.`, retrait du fragment,
    retrait des paramètres de suivi, tri des paramètres restants, retrait
    du `/` final du chemin."""

    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[len("www.") :]

    path = parts.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    kept_params = [
        (name, value)
        for name, value in parse_qsl(parts.query, keep_blank_values=True)
        if not _is_tracking_param(name, tracking_param_patterns)
    ]
    kept_params.sort()
    query = urlencode(kept_params)

    return urlunsplit((scheme, host, path, query, ""))
