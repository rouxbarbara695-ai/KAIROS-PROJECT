from __future__ import annotations

from app.identity.domain.seller import (
    PROTECTIONS,
    RELIABILITY,
    RISK_LEVEL,
    reliability_data,
)


def test_the_three_fields_are_normalised() -> None:
    data = reliability_data(
        reliability="Strong History",
        risk_level="MEDIUM",
        transaction_protections="one-protection",
    )
    assert data == {
        RELIABILITY: "strong_history",
        RISK_LEVEL: "medium",
        PROTECTIONS: "one_protection",
    }


def test_an_absent_field_leaves_the_previous_value() -> None:
    """Une correction partielle ne doit pas effacer ce qu'elle ne mentionne
    pas : corriger le pays ne doit pas remettre la fiabilité à zéro."""

    current = {RELIABILITY: "verified", RISK_LEVEL: "low", PROTECTIONS: "none"}
    data = reliability_data(
        reliability=None,
        risk_level="high",
        transaction_protections=None,
        current=current,
    )
    assert data[RELIABILITY] == "verified"
    assert data[RISK_LEVEL] == "high"
    assert data[PROTECTIONS] == "none"


def test_an_unknown_value_falls_back_to_the_most_cautious() -> None:
    """Jamais vers la valeur la plus favorable : une saisie illisible ne doit
    pas se transformer en vendeur vérifié."""

    data = reliability_data(
        reliability="excellentissime",
        risk_level="peut-être",
        transaction_protections="assurance maison",
    )
    assert data[RELIABILITY] == "unknown"
    assert data[RISK_LEVEL] == "unknown"
    # `protections` n'a pas de case « inconnu » : l'absence de protection
    # constatée est « aucune », le niveau le plus prudent.
    assert data[PROTECTIONS] == "none"


def test_nothing_provided_yields_nothing() -> None:
    """Un profil jamais renseigné se distingue d'un profil renseigné à
    « inconnu » : l'un est une case vide, l'autre un constat."""

    assert (
        reliability_data(
            reliability=None, risk_level=None, transaction_protections=None
        )
        == {}
    )
