"""Trois lots Catawiki réels, collés depuis le navigateur.

Les jeux d'essai reconstruits de `test_catawiki_extraction.py` décrivent ce que
l'extracteur **doit** faire. Ceux-ci décrivent ce qu'il **fait** sur des pages
réelles, copiées le 8 septembre 2026 — et c'est une tout autre affaire : la
page vraie apporte le menu de navigation, l'historique des enchères, la
biographie de la boutique et dix autres lots du même vendeur.

Six défauts sont nés de ces trois collages, et chacun a son test ici :

1. le titre lu était « Search for brand, model, artist… », du chrome ;
2. la description emportait toute la page, menus compris ;
3. « 2010-2020 » était lu comme l'année 2010 ;
4. la clôture, affichée en relatif, ne produisait aucune explication ;
5. le pays du vendeur n'était pas trouvé — Catawiki ne l'étiquette pas ;
6. la prose du vendeur l'emportait sur la fiche technique de la plateforme.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.collection.adapters import catawiki_text
from app.collection.domain.fields import ListingDraft, Provenance

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "listings"

_LOTS = {
    "jlc": (
        "catawiki-lot-reel-jlc.txt",
        "https://www.catawiki.com/en/l/106583853-jaeger-lecoultre-reverso-duetto"
        "-diamonds-266-1-44-serviced-women-2010-2020?po=search&poq=jaeger",
    ),
    "cartier": (
        "catawiki-lot-reel-cartier.txt",
        "https://www.catawiki.com/en/l/106501518-cartier-must-de-cartier-vendome"
        "-no-reserve-price-w1002253-women-1990-1999?po=search&poq=cartier",
    ),
    "omega": (
        "catawiki-lot-reel-omega.txt",
        "https://www.catawiki.com/en/l/106613690-omega-constellation-no-reserve"
        "-price-1561-61-00-women-1990-1999?po=search&poq=omega",
    ),
}


def _lot(name: str) -> ListingDraft:
    filename, url = _LOTS[name]
    return catawiki_text.extract(
        (_FIXTURES / filename).read_text(encoding="utf-8"), url
    )


# --- Le critère qui compte : le temps de saisie épargné ---------------------


@pytest.mark.parametrize("name", sorted(_LOTS))
def test_a_real_lot_fills_most_of_the_form(name: str) -> None:
    """Trente-six champs sur quarante-six, au minimum, sur les trois lots.

    En dessous, l'import ne fait pas gagner de temps et l'utilisateur retourne
    à la saisie manuelle — auquel cas tout ce module n'aurait servi à rien.
    """

    draft = _lot(name)

    assert draft.filled_count >= 36, {
        field: value.source
        for field, value in draft.fields().items()
        if value.provenance is Provenance.ABSENT
    }


@pytest.mark.parametrize(
    ("name", "lot", "brand", "reference", "bid"),
    [
        ("jlc", "106583853", "Jaeger-LeCoultre", "266.1.44", Decimal("4150")),
        ("cartier", "106501518", "Cartier", "W1002253", Decimal("900")),
        ("omega", "106613690", "Omega", "1561.61.00", Decimal("220")),
    ],
)
def test_the_identifying_fields_are_exact(
    name: str, lot: str, brand: str, reference: str, bid: Decimal
) -> None:
    draft = _lot(name)

    assert draft.lot_number.value == lot
    assert draft.brand.value == brand
    assert draft.reference.value == reference
    assert draft.current_bid_amount.value == bid
    assert draft.current_bid_currency.value == "EUR"
    assert draft.price_kind.value == "current_bid"


# --- Les six défauts trouvés par ces lots -----------------------------------


@pytest.mark.parametrize("name", sorted(_LOTS))
def test_the_title_is_the_lot_not_the_navigation_menu(name: str) -> None:
    """La première ligne d'un collage est « Search for brand, model, artist… ».

    La prendre pour un titre remplissait le dossier avec du chrome.
    """

    draft = _lot(name)

    assert draft.title.value is not None
    assert draft.title.value.startswith(str(draft.brand.value))
    assert "Search for brand" not in draft.title.value


@pytest.mark.parametrize("name", sorted(_LOTS))
def test_the_description_stops_at_the_seller_story(name: str) -> None:
    """« Seller's Story » est la présentation de la boutique, pas la montre.

    Sans borne, la description emportait aussi le menu, l'historique des
    enchères et les dix autres lots du vendeur.
    """

    draft = _lot(name)
    description = draft.description.value

    assert description is not None
    assert "Search for brand" not in description
    assert "Payment options" not in description
    assert "Other objects from" not in description
    # La prose du vendeur, elle, est bien là.
    assert "Brand" in description or "Reference" in description


@pytest.mark.parametrize("name", sorted(_LOTS))
def test_a_period_is_not_read_as_a_year(name: str) -> None:
    """Catawiki publie « 1990-1999 » ou « 2010-2020 ».

    En retenir la borne basse inventerait une précision que la page ne donne
    pas — et une montre datée 1990 alors qu'elle est de 1999 n'a pas la même
    valeur.
    """

    draft = _lot(name)

    assert draft.year.value is None
    assert draft.year.raw is not None
    assert "-" in draft.year.raw


@pytest.mark.parametrize("name", sorted(_LOTS))
def test_a_relative_closing_time_is_reported_not_converted(name: str) -> None:
    """Catawiki n'affiche jamais de date absolue : « Tomorrow 20:26 »,
    « Thursday 21:58 », « Closes in 5d 17m 14s ».

    Convertir supposerait que le collage a lieu à l'instant. Il peut dater
    d'une heure, et une fin d'enchère fausse d'une heure se rate.
    """

    draft = _lot(name)

    assert draft.closing_at.value is None
    assert draft.closing_at.raw is not None
    assert draft.closing_timezone.provenance is Provenance.ABSENT
    assert any("relatif" in warning for warning in draft.warnings)


@pytest.mark.parametrize(
    ("name", "country"), [("jlc", "FR"), ("cartier", "IT"), ("omega", "IT")]
)
def test_the_seller_country_is_read_without_a_label(name: str, country: str) -> None:
    """Catawiki n'étiquette pas le pays : il l'écrit en clair sous le vendeur.

    « Ships from EU » sert de repli mais n'est pas retenu — une zone n'est pas
    un pays.
    """

    draft = _lot(name)

    assert draft.seller_country.value == country
    assert draft.seller_type.value == "professional"


def test_the_specification_table_wins_over_the_seller_prose() -> None:
    """Le vendeur écrit « Movement: High-precision Swiss quartz, Caliber Omega
    1456 (as indicated on the pictogram card) » là où la fiche dit « Quartz ».

    La fiche est le champ structuré que Catawiki impose ; la prose est
    bavarde. Prendre la prose parce qu'elle apparaît plus haut dans la page
    remplissait le formulaire de phrases.
    """

    draft = _lot("omega")

    assert draft.movement.value == "Quartz"
    assert draft.case_material.value == "Steel"
    # La version du vendeur n'est pas perdue pour autant.
    assert any(
        "Caliber Omega 1456" in conflict for conflict in draft.movement.conflicts
    )


def test_a_contradiction_is_flagged_and_never_arbitrated() -> None:
    """La fiche arrondit le diamètre, la description le donne au dixième.

    Aucune des deux n'est « la bonne » : les deux sont conservées et
    l'utilisateur tranche.
    """

    draft = _lot("omega")

    assert draft.case_diameter_mm.value == Decimal("22")
    assert any("22.5" in conflict for conflict in draft.case_diameter_mm.conflicts)
    assert any("contradictoire" in warning for warning in draft.warnings)


# --- Ce que ces lots confirment sur les règles de fiabilité -----------------


@pytest.mark.parametrize(
    ("name", "status"),
    [("jlc", "not_met"), ("cartier", "no_reserve"), ("omega", "no_reserve")],
)
def test_the_reserve_is_read_from_the_explicit_mention(name: str, status: str) -> None:
    assert _lot(name).reserve_status.value == status


@pytest.mark.parametrize(
    ("name", "cost"),
    [("jlc", Decimal("90")), ("cartier", Decimal("50")), ("omega", Decimal("50"))],
)
def test_shipping_to_france_is_taken_and_the_other_line_is_not(
    name: str, cost: Decimal
) -> None:
    """Les lots italiens affichent « €50 from Italy » **avant** « Shipping to
    France: € 50 ». La première ligne ne nomme pas de destination de
    livraison : elle n'est pas retenue."""

    draft = _lot(name)

    assert draft.shipping_cost_amount.value == cost
    assert draft.shipping_destination.value == "FR"


@pytest.mark.parametrize("name", sorted(_LOTS))
def test_the_buyer_protection_fee_is_taken_when_displayed(name: str) -> None:
    """« Buyer Protection fee: 9% + € 3 » est affiché noir sur blanc et pèse
    sur le coût de revient. Il est repris — et jamais supposé ailleurs."""

    draft = _lot(name)

    assert draft.buyer_fee_rate.value == Decimal("0.09")
    assert draft.buyer_fee_fixed.value == Decimal("3")
    assert draft.buyer_fee_currency.value == "EUR"


@pytest.mark.parametrize("name", sorted(_LOTS))
def test_box_and_papers_come_from_their_own_lines(name: str) -> None:
    draft = _lot(name)

    assert isinstance(draft.box.value, bool)
    assert isinstance(draft.papers.value, bool)


def test_the_platform_estimate_never_becomes_the_price() -> None:
    """L'Omega est à 220 € pour une estimation Catawiki de 800-900 €.

    Confondre les deux ferait croire à une affaire déjà faite.
    """

    draft = _lot("omega")

    assert draft.estimate_low.value == Decimal("800")
    assert draft.estimate_high.value == Decimal("900")
    assert draft.price_amount.value == Decimal("220")
    assert any("pas celle de KAIROS" in warning for warning in draft.warnings)


@pytest.mark.parametrize("name", sorted(_LOTS))
def test_the_declared_condition_stays_a_declaration(name: str) -> None:
    draft = _lot(name)

    assert draft.declared_condition.raw is not None
    assert draft.declared_condition.value is None
