"""Lire un lot Catawiki dans du texte collé — et refuser de conclure au-delà.

Catawiki est la plateforme d'achat principale, et la seule dont la
récupération serveur est impossible : le bord Akamai refuse tout, y compris
`robots.txt`. Tout passe donc par le texte que l'utilisateur colle, ce qui
déplace le risque : il n'y a plus de balise `schema.org` pour garantir qu'une
valeur est bien ce qu'elle prétend être, seulement des étiquettes dans une
page.

D'où l'insistance de ces tests sur trois choses :

- **la nature des montants** — une enchère en cours n'est pas un prix d'achat,
  et l'estimation de Catawiki n'est pas celle de KAIROS ;
- **ce qui n'est pas dit** — pas de réserve mentionnée ne veut pas dire pas de
  réserve, et des frais sans destination nommée ne sont pas des frais vers la
  France ;
- **ce qui ressemble à une donnée sans en être une** — un millésime dans un
  titre n'est pas un compteur d'enchères, un compte à rebours n'est pas une
  date.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.collection.adapters import catawiki_text
from app.collection.domain.fields import Provenance

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "listings"

_FR_URL = "https://www.catawiki.com/fr/l/98765432-rolex-datejust"
_EN_URL = "https://www.catawiki.com/en/l/11223344-omega-speedmaster"


def _fixture(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def _fr():
    return catawiki_text.extract(_fixture("catawiki-lot-fr.txt"), _FR_URL)


def _en():
    return catawiki_text.extract(_fixture("catawiki-lot-en.txt"), _EN_URL)


# --- Ce qui est lu ----------------------------------------------------------


def test_a_french_lot_fills_most_of_the_form() -> None:
    """Le critère est le temps de saisie épargné : on compte les champs."""

    draft = _fr()

    assert draft.lot_number.value == "98765432"
    assert draft.brand.value == "Rolex"
    assert draft.collection.value == "Datejust"
    assert draft.reference.value == "16233"
    assert draft.year.value == 1994
    assert draft.movement.value == "Automatique"
    assert draft.case_material.value == "Or/acier"
    assert draft.case_diameter_mm.value == Decimal("36")
    assert draft.dial.value == "Champagne"
    assert draft.seller_name.value == "HorlogerieDuMarais"
    assert draft.seller_country.value == "FR"
    assert draft.seller_since.value == 2017

    # Au moins les trois quarts des champs, sinon l'import ne fait pas gagner
    # de temps et l'utilisateur retourne à la saisie manuelle.
    assert draft.filled_count >= 30


def test_the_same_lot_in_english_reads_identically() -> None:
    """L'utilisateur ne doit pas avoir à changer la langue de son compte."""

    draft = _en()

    assert draft.brand.value == "Omega"
    assert draft.reference.value == "145.022"
    assert draft.calibre.value == "861"
    assert draft.year.value == 1978
    assert draft.seller_country.value == "NL"
    assert draft.filled_count >= 30


# --- La nature des montants -------------------------------------------------


def test_the_current_bid_is_recorded_as_a_bid_never_as_a_price() -> None:
    """Une enchère en cours n'est ni un prix d'achat ni un prix final.

    Le schéma distingue `current_bid` de `asking`, `hammer` et `realized`.
    L'enregistrer sans le dire ferait calculer une marge sur un montant qui
    n'existera peut-être jamais : l'enchère monte, et elle peut ne pas
    atteindre la réserve.
    """

    draft = _fr()

    assert draft.current_bid_amount.value == Decimal("3250")
    assert draft.current_bid_currency.value == "EUR"
    assert draft.price_kind.value == "current_bid"
    # Le montant sert aussi de prix du dossier, mais sa nature l'accompagne.
    assert draft.price_amount.value == draft.current_bid_amount.value
    assert any("ni un prix final" in warning for warning in draft.warnings)


def test_the_fetch_timestamp_accompanies_the_bid() -> None:
    """Un montant d'enchère sans son heure ne veut rien dire : il aura changé."""

    draft = _fr()

    assert draft.fetched_at
    assert any(str(draft.fetched_at[:10]) in warning for warning in draft.warnings)


def test_the_platform_estimate_is_kept_apart() -> None:
    """L'estimation de Catawiki n'est pas une estimation KAIROS.

    Elle est conservée dans ses propres champs et n'alimente aucun calcul :
    la confondre reviendrait à valider une valorisation par l'avis du vendeur.
    """

    draft = _fr()

    assert draft.estimate_low.value == Decimal("3800")
    assert draft.estimate_high.value == Decimal("4500")
    assert draft.estimate_currency.value == "EUR"
    # Elle ne contamine pas le prix du dossier.
    assert draft.price_amount.value == Decimal("3250")
    assert any("pas celle de KAIROS" in warning for warning in draft.warnings)


def test_the_bid_count_is_not_read_from_a_year_in_the_title() -> None:
    """« Rolex … 1990-1999 » suivi de « Enchère actuelle » se lisait
    « 1999 enchères ». Le nombre et le mot doivent être sur la même ligne."""

    draft = _fr()

    assert draft.bid_count.value == 12


# --- Ce que la page ne dit pas ----------------------------------------------


def test_the_reserve_is_read_only_from_an_explicit_mention() -> None:
    assert _fr().reserve_status.value == "not_met"
    assert _en().reserve_status.value == "no_reserve"


def test_no_mention_of_a_reserve_does_not_mean_there_is_none() -> None:
    """C'est la confusion coûteuse : croire qu'on emporte le lot au prix
    affiché alors qu'une réserve non atteinte annulera la vente."""

    draft = catawiki_text.extract(
        "Rolex Submariner\nEnchère actuelle\n€ 5 000\n", _FR_URL
    )

    assert draft.reserve_status.provenance is Provenance.ABSENT
    assert any("ne veut pas dire" in warning for warning in draft.warnings)


def test_shipping_is_only_taken_when_france_is_named() -> None:
    draft = _fr()

    assert draft.shipping_cost_amount.value == Decimal("25.00")
    assert draft.shipping_destination.value == "FR"


def test_a_shipping_cost_without_a_named_destination_is_refused() -> None:
    """Catawiki affiche le tarif du pays du visiteur. Le prendre pour un tarif
    français fausserait le coût de revient sans que rien ne le signale."""

    draft = catawiki_text.extract("Rolex\nFrais d'expédition : € 18,00\n", _FR_URL)

    assert draft.shipping_cost_amount.provenance is Provenance.ABSENT
    assert draft.shipping_destination.provenance is Provenance.ABSENT
    assert any("quelle destination" in warning for warning in draft.warnings)


def test_a_closing_time_without_a_timezone_is_not_imported() -> None:
    """Se tromper d'une heure sur une fin d'enchère, c'est la rater."""

    draft = catawiki_text.extract(
        "Rolex\nSe termine le : 14 septembre 2026 à 20:15\n", _FR_URL
    )

    assert draft.closing_at.raw is not None  # ce qui était écrit est conservé
    assert draft.closing_at.value is None  # mais l'heure n'est pas reprise
    assert draft.closing_timezone.provenance is Provenance.ABSENT
    assert any("aucun fuseau" in warning for warning in draft.warnings)


def test_a_countdown_is_never_converted_into_a_date() -> None:
    """« 2 j 03 h » suppose que le collage a lieu à l'instant. Il peut dater
    d'une heure, et l'heure de fin serait fausse d'autant."""

    draft = catawiki_text.extract("Rolex\nSe termine dans 2 j 03 h 15 min\n", _FR_URL)

    # Aucune date n'est produite, mais ce que la page affichait est conservé :
    # l'utilisateur sait quoi aller vérifier.
    assert draft.closing_at.value is None
    assert draft.closing_at.raw == "Se termine dans 2 j 03 h 15 min"
    assert draft.closing_timezone.provenance is Provenance.ABSENT
    assert any("relatif" in warning for warning in draft.warnings)


def test_box_and_papers_are_read_separately() -> None:
    fr, en = _fr(), _en()

    assert (fr.box.value, fr.papers.value) == (True, False)
    assert (en.box.value, en.papers.value) == (False, True)


def test_a_declared_condition_is_kept_as_a_declaration() -> None:
    """« Bon état » est ce que le vendeur écrit, pas un constat."""

    draft = _fr()

    assert draft.declared_condition.raw is not None
    assert draft.declared_condition.value is None
    assert any("pas un constat" in warning for warning in draft.warnings)


# --- Sûreté ------------------------------------------------------------------


def test_a_serial_number_never_reaches_the_draft() -> None:
    draft = _fr()

    assert "R7889221" not in str(draft.to_json())
    assert any("numéro de série" in warning for warning in draft.warnings)


def test_every_field_carries_its_provenance() -> None:
    """Un champ importé ne doit jamais être indistinguable d'une saisie."""

    draft = _fr()

    for name, field in draft.fields().items():
        assert field.provenance in (Provenance.ASSISTED, Provenance.ABSENT), name
        # Une absence dit pourquoi ; une présence dit d'où elle vient.
        assert field.source is not None, name


def test_the_missing_photos_are_announced() -> None:
    """Un copier-coller de texte ne transporte pas les images. Le taire
    laisserait croire que l'annonce n'en avait pas."""

    assert any("photos ne sont pas reprises" in w for w in _fr().warnings)


def test_a_lot_number_mismatch_between_link_and_text_is_flagged() -> None:
    draft = catawiki_text.extract("Rolex\nNuméro de lot : 55555555\n", _FR_URL)

    assert draft.lot_number.value == "98765432"  # le lien fait foi
    assert any("diffèrent" in warning for warning in draft.warnings)


@pytest.mark.parametrize("text", ["", "   \n\n  ", "Bonjour"])
def test_useless_text_fills_nothing_rather_than_guessing(text: str) -> None:
    draft = catawiki_text.extract(text, _FR_URL)

    assert draft.brand.provenance is Provenance.ABSENT
    assert draft.current_bid_amount.provenance is Provenance.ABSENT
    assert draft.price_amount.provenance is Provenance.ABSENT


# --- La règle d'élaboration ne doit jamais effacer un désaccord --------------
#
# `_elaborates` conclut « même chose, en plus détaillé » quand les mots de la
# version courte se retrouvent dans la longue. Prise seule, cette inclusion
# efface les négations : « révisée » **est** contenue dans « non révisée ».
# Ces cas fixent les garde-fous, parce qu'une alerte de trop coûte un regard
# quand une négation perdue coûte une montre.


@pytest.mark.parametrize(
    ("short", "long"),
    [
        # Négation, dans les trois langues servies par Catawiki.
        ("révisée", "non révisée"),
        ("Serviced", "not serviced"),
        ("bracelet d'origine", "bracelet non d'origine"),
        ("papiers inclus", "sans papiers"),
        ("papers included", "no papers included"),
        ("originele doos", "geen originele doos"),
        ("boîte incluse", "boîte non incluse"),
        # Quantité : même unité, valeur différente.
        ("21 mm", "21 mm (crown excluded) 20.7 mm real"),
        ("12 mois", "24 mois de garantie"),
        ("0.32 ct", "0.32 ct et 0.50 ct"),
        ("40 mm", "40 mm de large, 12 mm d'épaisseur, 38 mm entrecorne"),
    ],
)
def test_a_disagreement_is_never_swallowed_by_the_inclusion_rule(
    short: str, long: str
) -> None:
    assert catawiki_text._elaborates(short, long) is False
    assert catawiki_text._elaborates(long, short) is False


@pytest.mark.parametrize(
    ("short", "long"),
    [
        # Vraies élaborations : la fiche dit court, le vendeur développe.
        ("Quartz", "High-precision Swiss quartz, Caliber Omega 1456"),
        ("Steel", "Stainless steel. Fixed bezel engraved with Roman numerals"),
        ("Yellow gold", "18k yellow gold, polished and brushed"),
        ("24 mm", "Case diameter: 24 mm."),
        ("Leather", "Leather strap, bright blue, aftermarket"),
        # Accent et ponctuation ne font pas une divergence.
        ("Must de Cartier Vendome", "Must de Cartier Vendôme."),
    ],
)
def test_a_genuine_elaboration_is_still_recognised(short: str, long: str) -> None:
    assert catawiki_text._elaborates(short, long) is True


def test_an_ambiguous_pair_keeps_both_and_asks_for_confirmation() -> None:
    """Le doute ne se tranche pas tout seul : les deux déclarations restent, et
    le champ demande confirmation."""

    text = (
        "Rolex\n"
        "Description from the seller\n"
        "Case material: acier non plaqué\n"
        "Details\n"
        "Case material\n"
        "acier plaqué\n"
    )
    draft = catawiki_text.extract(text, _FR_URL)

    assert draft.case_material.value == "acier plaqué"
    assert draft.case_material.needs_confirmation is True
    assert any("non plaqué" in conflict for conflict in draft.case_material.conflicts)
