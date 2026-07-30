from __future__ import annotations

from collections.abc import Mapping

from app.identity.domain import vocabularies as vocab

# Clés de `sellers.reliability_data`. Elles sont lues telles quelles par la
# porte « risque vendeur » et par le pilier « qualité des preuves » : les
# renommer ici sans les renommer là ferait retomber silencieusement tout un
# portefeuille sur « inconnu ».
RELIABILITY = "reliability"
RISK_LEVEL = "risk_level"
PROTECTIONS = "protections"


def reliability_data(
    *,
    reliability: str | None,
    risk_level: str | None,
    transaction_protections: str | None,
    current: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Normalise le profil de risque du vendeur.

    Un champ absent de la requête laisse la valeur en place — une correction
    partielle ne doit pas effacer ce qu'elle ne mentionne pas. Un champ
    présent mais hors vocabulaire retombe sur la valeur la plus prudente,
    jamais sur la plus favorable.
    """

    data: dict[str, object] = dict(current or {})

    if reliability is not None:
        data[RELIABILITY] = vocab.normalize(
            reliability,
            vocab.SELLER_RELIABILITY_LEVELS,
            vocab.SELLER_RELIABILITY_FALLBACK,
        )
    if risk_level is not None:
        data[RISK_LEVEL] = vocab.normalize(
            risk_level, vocab.SELLER_RISK_LEVELS, vocab.SELLER_RISK_FALLBACK
        )
    if transaction_protections is not None:
        data[PROTECTIONS] = vocab.normalize(
            transaction_protections,
            vocab.TRANSACTION_PROTECTIONS,
            vocab.TRANSACTION_PROTECTIONS_FALLBACK,
        )

    return data
