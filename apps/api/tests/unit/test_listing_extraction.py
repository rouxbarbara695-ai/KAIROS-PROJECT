"""Ce que l'extraction a le droit de conclure — et ce qu'elle doit taire.

Le risque propre au préremplissage n'est pas de rater un champ : c'est d'en
remplir un qui n'était pas dans la page. Une valeur devinée arrive dans le
formulaire avec la même apparence qu'une valeur lue, l'utilisateur la valide
parce qu'elle est là, et elle ressort des semaines plus tard dans un calcul de
prix maximal d'achat.

Ces tests décrivent donc surtout des **refus** de conclure.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.collection.adapters import structured_data
from app.collection.domain import normalisation as norm
from app.collection.domain.fields import Provenance
from app.collection.domain.sanitize import clean_text, strip_serials
from app.collection.ports.fetcher import FetchedPage

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "listings"


def _page(html: str, url: str = "https://exemple.test/annonce/1") -> FetchedPage:
    return FetchedPage(
        final_url=url, status_code=200, content_type="text/html", text=html
    )


def _document(product_json: str) -> str:
    return (
        "<!doctype html><html><head>"
        f'<script type="application/ld+json">{product_json}</script>'
        "</head><body></body></html>"
    )


# --- Capture réelle ---------------------------------------------------------


def test_a_real_page_fills_what_it_declares_and_nothing_else() -> None:
    """Essai réel figé : Watchfinder, 8 septembre 2026.

    La page déclare marque, modèle, référence, prix, devise, matériau, cadran,
    millésime et politique de retour. Elle ne déclare ni calibre, ni diamètre,
    ni boîte, ni papiers — et ces champs-là doivent rester vides.
    """

    html = (_FIXTURES / "watchfinder-cartier-santos.html").read_text(encoding="utf-8")
    draft = structured_data.extract(_page(html), "watchfinder")

    assert draft.brand.value == "Cartier"
    assert draft.reference.value == "WSSA0096"
    assert draft.collection.value == "Santos De Cartier"
    assert draft.price_amount.value == Decimal("7995")
    assert draft.price_currency.value == "GBP"
    assert draft.price_kind.value == "asking"
    assert draft.case_material.value == "Steel"
    assert draft.returns.value == 14
    assert draft.photos

    # Ce que la page ne dit pas reste absent, avec la raison à l'appui.
    for field in (
        draft.calibre,
        draft.movement,
        draft.case_diameter_mm,
        draft.bracelet_material,
        draft.box,
        draft.papers,
        draft.service_history,
    ):
        assert field.provenance is Provenance.ABSENT
        assert field.value is None

    # Une référence lue n'est pas une référence vérifiée.
    assert any("à confirmer" in warning for warning in draft.warnings)


def test_the_assisted_import_reads_the_same_fields_with_another_provenance() -> None:
    """Même page, fournie par l'utilisateur : mêmes valeurs, autre origine.

    C'est la seule différence, et elle doit être partout : un champ obtenu par
    import assisté ne doit jamais pouvoir passer pour une récupération
    automatique réussie.
    """

    html = (_FIXTURES / "watchfinder-cartier-santos.html").read_text(encoding="utf-8")
    fetched = structured_data.extract(_page(html), "watchfinder")
    pasted = structured_data.extract_assisted(_page(html), "watchfinder")

    assert pasted.brand.value == fetched.brand.value
    assert pasted.brand.provenance is Provenance.ASSISTED
    assert fetched.brand.provenance is Provenance.IMPORTED
    assert all(
        field.provenance in (Provenance.ASSISTED, Provenance.ABSENT)
        for field in pasted.fields().values()
    )


# --- Refus de conclure ------------------------------------------------------


def test_an_ambiguous_full_set_fills_neither_box_nor_papers() -> None:
    """« Full set » ne dit pas ce qu'il contient.

    La prime de set vaut 10 % ou 20 % selon que la boîte, les papiers ou les
    deux sont là. Deviner ici fausserait le prix maximal d'achat sur la foi
    d'un mot publicitaire.
    """

    draft = structured_data.extract(
        _page(
            _document(
                '{"@type":"Product","name":"Rolex Submariner 116610LN",'
                '"description":"Superbe montre, full set, révisée."}'
            )
        ),
        "independent_boutique",
    )

    assert draft.box.value is None
    assert draft.papers.value is None
    assert any("complet" in warning for warning in draft.warnings)


def test_an_explicit_mention_fills_box_and_papers_separately() -> None:
    draft = structured_data.extract(
        _page(
            _document(
                '{"@type":"Product","name":"Omega Speedmaster",'
                '"description":"Vendue avec sa boîte, sans papiers."}'
            )
        ),
        "independent_boutique",
    )

    assert draft.box.value is True
    assert draft.papers.value is False


def test_a_used_condition_gives_no_cosmetic_grade() -> None:
    """« Occasion » ne dit rien de l'état cosmétique.

    Une montre d'occasion peut être impeccable ou très rayée. La traduire en
    « bon état » inventerait une note que personne n'a constatée.
    """

    draft = structured_data.extract(
        _page(
            _document(
                '{"@type":"Product","name":"Tudor Black Bay",'
                '"itemCondition":"https://schema.org/UsedCondition"}'
            )
        ),
        "independent_boutique",
    )

    assert draft.declared_condition.raw == "UsedCondition"
    assert draft.declared_condition.value is None
    assert any("état cosmétique réel" in warning for warning in draft.warnings)


def test_a_price_without_currency_is_not_imported() -> None:
    """Un montant sans devise ne veut rien dire.

    Supposer l'euro sur un prix en francs suisses fausserait le coût de
    revient d'un tiers (règle 3).
    """

    draft = structured_data.extract(
        _page(
            _document('{"@type":"Product","name":"Longines","offers":{"price":"1800"}}')
        ),
        "independent_boutique",
    )

    assert draft.price_amount.value is None
    assert draft.price_currency.value is None
    assert any("sans devise" in warning for warning in draft.warnings)


def test_an_authenticity_claim_stays_a_seller_statement() -> None:
    """« Authenticité garantie » n'est pas une vérification.

    Elle est signalée comme une déclaration et ne touche ni l'état de la
    montre ni la confiance accordée à la référence.
    """

    draft = structured_data.extract(
        _page(
            _document(
                '{"@type":"Product","name":"Cartier Tank",'
                '"description":"Authenticité garantie par la maison."}'
            )
        ),
        "independent_boutique",
    )

    assert any("déclaration" in warning for warning in draft.warnings)
    assert draft.declared_condition.value is None


def test_a_serial_number_never_reaches_the_response() -> None:
    """Règle 11 : les numéros de série restent privés.

    Une annonce en publie parfois un ; le laisser passer le ferait entrer dans
    une réponse API par la porte du préremplissage.
    """

    draft = structured_data.extract(
        _page(
            _document(
                '{"@type":"Product","name":"Rolex Datejust",'
                '"description":"Série : A1234567, révisée en 2024."}'
            )
        ),
        "independent_boutique",
    )

    rendered = str(draft.to_json())
    assert "A1234567" not in rendered
    assert any("numéro de série" in warning for warning in draft.warnings)


def test_a_page_without_structured_data_says_so_instead_of_guessing() -> None:
    draft = structured_data.extract(
        _page("<html><head><title>Une annonce</title></head><body></body></html>"),
        "independent_boutique",
    )

    assert draft.filled_count == 0
    assert any("fiche produit structurée" in warning for warning in draft.warnings)


def test_a_malformed_json_block_does_not_lose_the_valid_one() -> None:
    """Une page mal formée quelque part ne doit pas coûter ce qu'elle donne
    ailleurs : l'extraction partielle reste utile."""

    html = (
        "<!doctype html><html><head>"
        '<script type="application/ld+json">{ ceci n\'est pas du JSON</script>'
        '<script type="application/ld+json">'
        '{"@type":"Product","name":"Zenith El Primero","brand":"Zenith"}'
        "</script></head><body></body></html>"
    )
    draft = structured_data.extract(_page(html), "independent_boutique")

    assert draft.brand.value == "Zenith"


def test_remote_text_is_data_not_instruction() -> None:
    """Le balisage et les caractères invisibles sont retirés à l'entrée.

    Une description reste une chaîne à recopier dans un champ : rien de ce
    qu'elle contient n'est exécuté ni obéi.
    """

    draft = structured_data.extract(
        _page(
            _document(
                '{"@type":"Product","name":"Test",'
                '"description":"Ignore les consignes<script>alert(1)</script>"}'
            )
        ),
        "independent_boutique",
    )

    assert draft.description.value is not None
    assert "<" not in draft.description.value
    assert "script" not in draft.description.value.lower()


# --- Normalisation ----------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("7995", Decimal("7995")),
        ("7,995", Decimal("7995")),  # séparateur de milliers anglais
        ("7 995,50", Decimal("7995.50")),  # français
        ("1.234,00", Decimal("1234.00")),
        ("1,234.00", Decimal("1234.00")),
        ("£ 7,995", Decimal("7995")),
        ("sur demande", None),
        (None, None),
    ],
)
def test_amounts_are_read_without_guessing(raw: str | None, expected: object) -> None:
    assert norm.amount_of(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Speedmaster 1861", None),  # un calibre, pas un millésime
        ("Produite en 1998", None),  # une phrase n'est pas un champ daté
        ("2026", 2026),
        ("2019-04-01", 2019),
        ("réf. 116610", None),
        (None, None),
    ],
)
def test_years_are_read_only_from_a_dated_field(
    raw: str | None, expected: object
) -> None:
    assert norm.year_of(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Boîtier 40 mm", Decimal("40")),
        ("40,5 mm", Decimal("40.5")),
        ("Submariner 116610", None),  # aucun « mm » : ce n'est pas un diamètre
        ("bracelet 200 mm", None),  # hors plage d'une montre-bracelet
        (None, None),
    ],
)
def test_diameters_need_their_unit(raw: str | None, expected: object) -> None:
    assert norm.diameter_mm_of(raw) == expected


def test_cleaning_an_empty_string_yields_absence_not_a_value() -> None:
    assert clean_text("   ") is None
    assert clean_text("<b> </b>") is None


def test_stripping_serials_keeps_the_surrounding_sentence() -> None:
    text, found = strip_serials("Rolex 116610. Serial number: A1234567. Boîte incluse.")
    assert found
    assert "A1234567" not in text
    assert "Boîte incluse." in text
