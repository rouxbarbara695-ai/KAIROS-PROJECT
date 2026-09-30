"""Contrôle d'identité, configuration, doublons — sur de vrais titres.

Les titres viennent des lots réellement lus le 30 septembre 2026 (les trois
références de l'essai d'accès) et de voisins réellement renvoyés par la
recherche : c'est le voisin, pas l'exact, qui met le contrôle à l'épreuve.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.market_search.domain.candidate import Candidate
from app.market_search.domain.dedupe import deduplicate
from app.market_search.domain.policy import SearchPolicy
from app.market_search.domain.reference import (
    brand_present,
    match_reference,
    spelling_variants,
)
from app.market_search.domain.screening import screen

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
POLICY = SearchPolicy()


def candidate(
    title: str,
    *,
    amount: str = "800",
    kind: str = "asking",
    ends_in_hours: float | None = None,
    bids: int | None = None,
    external_id: str = "v1|1|0",
    country: str | None = "FR",
) -> Candidate:
    return Candidate(
        source="ebay",
        external_id=external_id,
        title=title,
        url="https://www.ebay.fr/itm/1",
        amount=Decimal(amount),
        currency="EUR",
        price_kind=kind,  # type: ignore[arg-type]
        observed_at=NOW,
        ends_at=None if ends_in_hours is None else NOW + timedelta(hours=ends_in_hours),
        bid_count=bids,
        country=country,
    )


# --- La référence : ponctuation et casse seulement -------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Omega - Constellation - No reserve price - 1561.61.00 - Women - 1990-1999",
        "OMEGA CONSTELLATION 1561 61 00 QUARTZ",
        "omega constellation 1561-61-00",
        "Omega Constellation 15616100 acier",
        "Omega Constellation Ref. 1561.61.00.",
    ],
)
def test_omega_reference_spellings_are_accepted(text: str) -> None:
    assert match_reference(text, "1561.61.00").found


@pytest.mark.parametrize(
    "text",
    [
        # Les voisins réellement renvoyés par Catawiki pour cette recherche.
        "Omega - Constellation Double Eagle - 1501.51.00 - Unisexe - 2007",
        "Omega - Constellation - 1512.30.00 (396.1201) - Homme - 1990-1999",
        "Omega - Constellation Mini - 1562.30 - Femme - 1990-1999",
        "Omega Constellation 1561.61",  # groupe manquant : autre référence
        "Omega Constellation 1561.61.001",
        "Omega Constellation 1561.61.00.5",
        "Omega Constellation 3.1561.61.00",
    ],
)
def test_neighbouring_omega_references_are_rejected(text: str) -> None:
    assert not match_reference(text, "1561.61.00").found


def test_cartier_reference_needs_its_letter() -> None:
    assert match_reference("Cartier Must Vendôme W1002253 argent", "W1002253").found
    assert match_reference("Cartier Must Vendôme W 1002253", "W1002253").found
    # « 1002253 » sans son « W » n'est pas la même référence.
    assert not match_reference("Cartier Must Vendôme 1002253", "W1002253").found


def test_jlc_reference_is_not_found_inside_a_longer_number() -> None:
    assert match_reference("JLC Reverso Duetto 266.1.44 Serviced", "266.1.44").found
    assert not match_reference("Reverso Q2668450 2661440", "266.1.44").found


def test_spelling_variants_only_change_punctuation() -> None:
    variants = spelling_variants("1561.61.00")
    assert "1561.61.00" in variants and "15616100" in variants
    assert all(match_reference(v, "1561.61.00").found for v in variants)


def test_brand_aliases() -> None:
    assert brand_present("JLC Reverso Duetto", "Jaeger-LeCoultre")
    assert brand_present("Jaeger LeCoultre Reverso", "Jaeger-LeCoultre")
    assert not brand_present("Reverso Duetto 266.1.44", "Jaeger-LeCoultre")


# --- Le verdict : motif pour chaque annonce ---------------------------------


def verdict(c: Candidate, reference: str = "1561.61.00", brand: str = "Omega"):
    return screen(
        c,
        brand=brand,
        reference=reference,
        model="Constellation",
        policy=POLICY,
        now=NOW,
    )


def test_exact_listing_is_accepted() -> None:
    v = verdict(candidate("Omega Constellation Mini 1561.61.00 quartz acier"))
    assert v.accepted and v.code == "accepted"


def test_neighbour_is_rejected_with_its_reason_never_substituted() -> None:
    v = verdict(candidate("Omega Constellation Mini 1562.30 quartz"))
    assert not v.accepted and v.code == "reference_not_stated"


def test_same_number_under_another_brand_is_rejected() -> None:
    v = verdict(candidate("Seiko 5 1561.61.00 vintage"))
    assert not v.accepted and v.code == "brand_not_stated"


@pytest.mark.parametrize(
    ("title", "code"),
    [
        ("Omega Constellation 1561.61.00 for parts", "not_a_complete_watch"),
        ("Omega Constellation 1561.61.00 pour pièces", "not_a_complete_watch"),
        ("Omega Constellation 1561.61.00 defekt Bastler", "not_a_complete_watch"),
        ("Omega 1561.61.00 bracelet only", "not_a_complete_watch"),
        ("Omega Constellation 1561.61.00 replica", "counterfeit_marker"),
        ("Lot de 3 montres Omega Constellation 1561.61.00", "multiple_items"),
    ],
)
def test_incomplete_or_counterfeit_listings_are_rejected(title: str, code: str) -> None:
    v = verdict(candidate(title))
    assert not v.accepted and v.code == code


def test_complete_set_is_not_mistaken_for_an_accessory() -> None:
    v = verdict(candidate("Omega Constellation 1561.61.00 avec boîte et papiers"))
    assert v.accepted


def test_missing_model_is_a_warning_not_a_rejection() -> None:
    v = verdict(candidate("Omega 1561.61.00 quartz acier dame"))
    assert v.accepted and "model_not_stated" in v.warnings


# --- Nature du prix : une enchère n'est pas un prix demandé ------------------


def test_auction_far_from_its_end_is_not_a_price() -> None:
    v = verdict(
        candidate("Omega 1561.61.00", kind="current_bid", ends_in_hours=70, bids=3)
    )
    assert not v.accepted and v.code == "auction_too_early"


def test_auction_without_bid_is_not_a_price() -> None:
    v = verdict(
        candidate("Omega 1561.61.00", kind="current_bid", ends_in_hours=2, bids=0)
    )
    assert not v.accepted and v.code == "auction_without_bids"


def test_auction_without_end_time_is_rejected() -> None:
    v = verdict(candidate("Omega 1561.61.00", kind="current_bid", bids=2))
    assert not v.accepted and v.code == "auction_end_unknown"


def test_close_auction_is_kept_but_flagged_as_not_final() -> None:
    v = verdict(
        candidate("Omega 1561.61.00", kind="current_bid", ends_in_hours=3, bids=4)
    )
    assert v.accepted and "current_bid_not_final" in v.warnings


def test_zero_price_is_rejected() -> None:
    v = verdict(candidate("Omega 1561.61.00", amount="0"))
    assert not v.accepted and v.code == "no_price"


# --- Doublons ---------------------------------------------------------------


def test_relisted_watch_is_counted_once() -> None:
    first = candidate("Omega Constellation 1561.61.00", external_id="v1|111|0")
    relisted = candidate("OMEGA Constellation 1561.61.00 !", external_id="v1|222|0")
    other = candidate(
        "Omega Constellation 1561.61.00", amount="950", external_id="v1|333|0"
    )
    result = deduplicate([first, relisted, other])
    assert [c.external_id for c in result.kept] == ["v1|111|0", "v1|333|0"]
    assert result.duplicates[0][0].external_id == "v1|222|0"


def test_same_listing_read_twice_is_not_a_duplicate() -> None:
    a = candidate("Omega 1561.61.00", external_id="v1|111|0")
    result = deduplicate([a, a])
    assert len(result.kept) == 1 and result.duplicates == []


def test_amount_formatting_does_not_hide_a_duplicate() -> None:
    a = candidate("Omega 1561.61.00", amount="800", external_id="v1|1|0")
    b = candidate("Omega 1561.61.00", amount="800.00", external_id="v1|2|0")
    assert len(deduplicate([a, b]).kept) == 1
