from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

_CATAWIKI = {
    "provenance_url": "https://www.catawiki.com/fr/help/selling-fees",
    "buyer_fee_rate": "0.09",
    "seller_fee_rate": "0.125",
    "seller_fee_fixed": "20.00",
    "currency": "EUR",
}


async def _create(client: AsyncClient, code: str = "catawiki", **overrides: object):
    return await client.post(
        f"/api/v1/platforms/{code}/rules", json={**_CATAWIKI, **overrides}
    )


async def test_no_platform_has_a_fee_schedule_out_of_the_box(
    client: AsyncClient,
) -> None:
    """Aucune grille n'est seedée, et c'est délibéré : une commission inventée
    fausserait tous les profits sans que rien ne le signale."""

    body = (await client.get("/api/v1/platforms")).json()
    assert body
    assert all(not platform["has_active_rule"] for platform in body)


async def test_a_recorded_schedule_becomes_the_active_one(
    client: AsyncClient,
) -> None:
    created = await _create(client)
    assert created.status_code == 201, created.text
    assert created.json()["version"] == 1

    body = (await client.get("/api/v1/platforms")).json()
    catawiki = next(item for item in body if item["code"] == "catawiki")
    assert catawiki["has_active_rule"]
    assert catawiki["active_rule"]["seller_fee_rate"] == "0.1250000000"
    assert catawiki["active_rule"]["seller_fee_fixed"] == "20.00"


async def test_recording_again_closes_the_previous_version(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Une grille n'est jamais réécrite : une analyse produite sous l'ancienne
    reste rejouable."""

    first = (await _create(client)).json()
    second = (await _create(client, seller_fee_rate="0.15")).json()

    assert second["version"] == first["version"] + 1

    closed = (
        await db_session.execute(
            text("select valid_to from platform_rules where id = :id"),
            {"id": first["id"]},
        )
    ).scalar_one()
    assert closed is not None

    body = (await client.get("/api/v1/platforms")).json()
    catawiki = next(item for item in body if item["code"] == "catawiki")
    assert catawiki["active_rule"]["id"] == second["id"]


async def test_recording_a_schedule_authorises_no_collection(
    client: AsyncClient,
) -> None:
    """Règle 9 : saisir des tarifs ne vaut pas feu vert de collecte. Le mode
    d'accès et son autorisation relèvent d'une validation écrite distincte."""

    body = (await _create(client)).json()
    assert body["access_method"] == "manual"
    assert body["access_authorized"] is False


async def test_provenance_is_required(client: AsyncClient) -> None:
    """Une grille qu'on ne peut pas vérifier ne vaut pas mieux qu'une grille
    inventée."""

    response = await client.post(
        "/api/v1/platforms/catawiki/rules", json={"seller_fee_rate": "0.10"}
    )
    assert response.status_code == 422


async def test_a_floor_above_its_cap_is_refused(client: AsyncClient) -> None:
    response = await _create(client, seller_fee_min="500.00", seller_fee_max="100.00")
    assert response.status_code == 422


async def test_an_unknown_platform_is_not_found(client: AsyncClient) -> None:
    assert (await _create(client, code="brocante-du-coin")).status_code == 404


async def test_rates_travel_as_decimal_strings(client: AsyncClient) -> None:
    body = (await _create(client)).json()
    for field in ("buyer_fee_rate", "seller_fee_rate", "seller_fee_fixed"):
        assert isinstance(body[field], str), field


async def test_a_schedule_with_no_fees_is_accepted(client: AsyncClient) -> None:
    """Une plateforme sans frais est un constat, pas un oubli de saisie."""

    response = await client.post(
        "/api/v1/platforms/user_data/rules",
        json={"provenance_url": "https://exemple.test/tarifs"},
    )
    assert response.status_code == 201
    assert response.json()["seller_fee_rate"] is None


# --- Effet sur l'analyse -------------------------------------------------


async def test_fees_reach_the_scenarios(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """Sans grille, le profit affiché est celui d'une vente entre
    particuliers. Avec la grille de Catawiki, il baisse — c'est tout l'enjeu
    de la saisie."""

    await db_session.execute(
        text(
            """
            insert into portfolio_ledger_entries (portfolio_id, kind,
              amount_source, currency, amount_eur, rate_to_eur, fx_rate_at,
              fx_source, occurred_at, actor_user_id)
            select :pf, 'capital_contribution', 30000, 'EUR', 30000, 1, now(),
                   'saisie manuelle', now(), id from users limit 1
            """
        ),
        {"pf": default_portfolio_id},
    )
    await db_session.commit()

    opportunity = (
        await client.post(
            "/api/v1/opportunities",
            json={
                "portfolio_id": str(default_portfolio_id),
                "source": {"mode": "manual", "manual_identifier": "PLT-001"},
                "watch": {
                    "brand": "Tudor",
                    "reference": "79030N",
                    "mechanical_condition": "verified",
                    "cosmetic_condition": "excellent",
                    "box": True,
                    "papers": True,
                },
                "seller": {"country_code": "FR", "seller_type": "private"},
                "price": {"amount": "2400.00", "currency": "EUR"},
            },
        )
    ).json()

    # Sans référence confirmée, la porte d'identification bloque et l'analyse
    # ne produit aucun scénario : le test porterait alors sur autre chose.
    confirmed = await client.post(
        f"/api/v1/opportunities/{opportunity['id']}/reference-confirmations",
        json={
            "status": "confirmed",
            "reference_id": opportunity["watch"]["reference_id"],
            "reason": "Référence vérifiée sur le fond de boîtier.",
        },
    )
    assert confirmed.status_code == 200, confirmed.text

    for index, amount in enumerate(
        ["3500.00", "3550.00", "3600.00", "3620.00", "3680.00", "3700.00"]
    ):
        await client.post(
            f"/api/v1/opportunities/{opportunity['id']}/comparables",
            json={
                "source_name": "Chrono24",
                "seller_fingerprint": f"s{index}",
                "price_kind": "asking",
                "amount": amount,
                "currency": "EUR",
                "market_status": "active",
                "observed_at": "2026-07-20T10:00:00Z",
                "source_reliability": "a",
                "mechanical_condition": "verified",
                "cosmetic_condition": "excellent",
                "box": True,
                "papers": True,
            },
        )
    await client.post(f"/api/v1/opportunities/{opportunity['id']}/valuations")

    analysis = (
        await client.post(f"/api/v1/opportunities/{opportunity['id']}/analyses")
    ).json()

    # Une opportunité manuelle n'est rattachée à aucune plateforme : ses coûts
    # sont ceux d'une vente entre particuliers.
    central = analysis["scenario_results"]["central"]
    assert central["total_cost_before_sale_eur"] == "2400.00"


async def test_a_manual_opportunity_can_declare_its_purchase_platform(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """Une saisie manuelle peut venir de Catawiki sans qu'on ait collé l'URL.
    Sans cette déclaration, l'achat passerait pour une vente de particulier à
    particulier et sa commission disparaîtrait du calcul."""

    await _create(client)  # grille Catawiki : 9 % à l'achat

    await db_session.execute(
        text(
            """
            insert into portfolio_ledger_entries (portfolio_id, kind,
              amount_source, currency, amount_eur, rate_to_eur, fx_rate_at,
              fx_source, occurred_at, actor_user_id)
            select :pf, 'capital_contribution', 30000, 'EUR', 30000, 1, now(),
                   'saisie manuelle', now(), id from users limit 1
            """
        ),
        {"pf": default_portfolio_id},
    )
    await db_session.commit()

    created = await client.post(
        "/api/v1/opportunities",
        json={
            "portfolio_id": str(default_portfolio_id),
            "source": {
                "mode": "manual",
                "manual_identifier": "PLT-MANUEL",
                "platform_code": "catawiki",
            },
            "watch": {
                "brand": "Tudor",
                "reference": "79030N",
                "mechanical_condition": "verified",
                "cosmetic_condition": "excellent",
                "box": True,
                "papers": True,
            },
            "seller": {"country_code": "FR", "seller_type": "private"},
            "price": {"amount": "2400.00", "currency": "EUR"},
        },
    )
    assert created.status_code == 201, created.text
    opportunity = created.json()
    assert opportunity["purchase_platform_code"] == "catawiki"

    confirmed = await client.post(
        f"/api/v1/opportunities/{opportunity['id']}/reference-confirmations",
        json={
            "status": "confirmed",
            "reference_id": opportunity["watch"]["reference_id"],
            "reason": "Référence vérifiée.",
        },
    )
    assert confirmed.status_code == 200, confirmed.text

    for index, amount in enumerate(
        ["3500.00", "3550.00", "3600.00", "3620.00", "3680.00", "3700.00"]
    ):
        await client.post(
            f"/api/v1/opportunities/{opportunity['id']}/comparables",
            json={
                "source_name": "Chrono24",
                "seller_fingerprint": f"m{index}",
                "price_kind": "asking",
                "amount": amount,
                "currency": "EUR",
                "market_status": "active",
                "observed_at": "2026-07-20T10:00:00Z",
                "source_reliability": "a",
                "mechanical_condition": "verified",
                "cosmetic_condition": "excellent",
                "box": True,
                "papers": True,
            },
        )
    await client.post(f"/api/v1/opportunities/{opportunity['id']}/valuations")

    analysis = (
        await client.post(f"/api/v1/opportunities/{opportunity['id']}/analyses")
    ).json()

    # 2 400 € + 9 % de commission d'achat : la plateforme déclarée s'applique
    # bien, alors qu'aucune annonce n'existe.
    central = analysis["scenario_results"]["central"]
    assert central["total_cost_before_sale_eur"] == "2616.00"


async def test_an_unknown_purchase_platform_is_refused(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    response = await client.post(
        "/api/v1/opportunities",
        json={
            "portfolio_id": str(default_portfolio_id),
            "source": {
                "mode": "manual",
                "manual_identifier": "PLT-INCONNU",
                "platform_code": "brocante-du-coin",
            },
            "watch": {"brand": "Tudor", "reference": "79030N"},
            "seller": {},
            "price": {"amount": "100.00", "currency": "EUR"},
        },
    )
    assert response.status_code == 404


# --- TVA sur commission et frais de paiement -----------------------------


async def test_ebay_is_a_known_platform(client: AsyncClient) -> None:
    """eBay manquait à la liste. Une revente qui s'y fait n'était donc pas
    modélisable, et aucun écran ne le disait."""

    codes = {item["code"] for item in (await client.get("/api/v1/platforms")).json()}
    assert "ebay" in codes


async def test_vat_and_payment_fees_are_recorded(client: AsyncClient) -> None:
    body = (
        await _create(
            client,
            seller_fee_vat_rate="0.20",
            buyer_fee_vat_rate="0",
            payment_fee_rate="0.03",
        )
    ).json()

    assert body["seller_fee_vat_rate"] == "0.2000000000"
    assert body["payment_fee_rate"] == "0.0300000000"
    # Zéro et non renseigné sont deux constats différents : un zéro affirme que
    # les frais sont déjà taxe comprise, un vide dit qu'on ne sait pas.
    assert body["buyer_fee_vat_rate"] == "0.0000000000"


async def test_an_unstated_vat_rate_stays_unstated(client: AsyncClient) -> None:
    body = (await _create(client)).json()
    assert body["seller_fee_vat_rate"] is None
    assert body["payment_fee_rate"] is None


async def test_a_vat_rate_written_as_a_percentage_is_refused(
    client: AsyncClient,
) -> None:
    """« 20 » au lieu de « 0.20 » multiplierait la commission par vingt.
    Accepter la saisie la rendrait indétectable dans les profits."""

    response = await _create(client, seller_fee_vat_rate="20")
    assert response.status_code == 422


async def test_vat_on_commission_reaches_the_analysis(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """Le cas du vendeur particulier : la TVA sur la commission ne se récupère
    pas, donc elle sort du profit. Sans elle, tout profit de revente était
    surestimé d'un cinquième de la commission."""

    await db_session.execute(
        text(
            """
            insert into portfolio_ledger_entries (portfolio_id, kind,
              amount_source, currency, amount_eur, rate_to_eur, fx_rate_at,
              fx_source, occurred_at, actor_user_id)
            select :pf, 'capital_contribution', 30000, 'EUR', 30000, 1, now(),
                   'saisie manuelle', now(), id from users limit 1
            """
        ),
        {"pf": default_portfolio_id},
    )
    await db_session.commit()

    opportunity = (
        await client.post(
            "/api/v1/opportunities",
            json={
                "portfolio_id": str(default_portfolio_id),
                "source": {"mode": "manual", "manual_identifier": "TVA-001"},
                "watch": {
                    "brand": "Tudor",
                    "reference": "79030N",
                    "mechanical_condition": "verified",
                    "cosmetic_condition": "excellent",
                    "box": True,
                    "papers": True,
                },
                "seller": {"country_code": "FR", "seller_type": "private"},
                "price": {"amount": "2400.00", "currency": "EUR"},
            },
        )
    ).json()
    opportunity_id = opportunity["id"]

    await client.post(
        f"/api/v1/opportunities/{opportunity_id}/reference-confirmations",
        json={
            "status": "confirmed",
            "reference_id": opportunity["watch"]["reference_id"],
            "reason": "Référence vérifiée.",
        },
    )
    for index, amount in enumerate(
        ["3500.00", "3550.00", "3600.00", "3620.00", "3680.00", "3700.00"]
    ):
        await client.post(
            f"/api/v1/opportunities/{opportunity_id}/comparables",
            json={
                "source_name": "Chrono24",
                "seller_fingerprint": f"v{index}",
                "price_kind": "asking",
                "amount": amount,
                "currency": "EUR",
                "market_status": "active",
                "observed_at": "2026-07-20T10:00:00Z",
                "source_reliability": "a",
                "mechanical_condition": "verified",
                "cosmetic_condition": "excellent",
                "box": True,
                "papers": True,
            },
        )
    await client.post(f"/api/v1/opportunities/{opportunity_id}/valuations")

    async def central_with(**fees: object) -> dict[str, str]:
        await client.post(
            "/api/v1/platforms/chrono24/rules",
            json={
                "provenance_url": "https://exemple.test/chrono24",
                "seller_fee_rate": "0.10",
                "currency": "EUR",
                **fees,
            },
        )
        await client.post(
            f"/api/v1/portfolios/{default_portfolio_id}/strategy",
            json={"resale_platform_code": "chrono24"},
        )
        analysis = (
            await client.post(f"/api/v1/opportunities/{opportunity_id}/analyses")
        ).json()
        central: dict[str, str] = analysis["scenario_results"]["central"]
        return central

    without_vat = await central_with()
    with_vat = await central_with(seller_fee_vat_rate="0.20")

    # Le prix de vente ne dépend pas des frais : c'est la cote qui le fixe.
    assert with_vat["sale_price_eur"] == without_vat["sale_price_eur"]

    # La TVA vaut 20 % d'une commission de 10 %, soit exactement 2 % du prix de
    # vente. Un écart différent signalerait qu'elle s'applique au mauvais
    # montant, ou deux fois.
    sale_price = Decimal(with_vat["sale_price_eur"])
    lost = Decimal(without_vat["net_profit_eur"]) - Decimal(with_vat["net_profit_eur"])
    assert lost == (sale_price * Decimal("0.02")).quantize(Decimal("0.01"))


# --- Barèmes par tranches ------------------------------------------------

_EBAY_TIERS = [
    {"up_to": "2000.00", "rate": "0.10"},
    {"up_to": None, "rate": "0.02"},
]


async def test_ebays_real_scale_is_recorded_as_tiers(client: AsyncClient) -> None:
    """La grille réelle d'eBay France : 10 % sur les 2 000 premiers euros,
    2 % au-delà, 0,35 € par commande, et une base qui inclut le port."""

    response = await client.post(
        "/api/v1/platforms/ebay/rules",
        json={
            "provenance_url": "https://www.ebay.fr/help/selling/fees-credits-invoices"
            "/services-de-paiement-frais-pour-les-vendeurs-particuliers?id=4822",
            "seller_fee_tiers": _EBAY_TIERS,
            "seller_fee_fixed": "0.35",
            "seller_fee_basis": "price_and_shipping",
            "payment_fee_rate": "0.0042",
            "currency": "EUR",
        },
    )
    assert response.status_code == 201, response.text

    body = response.json()
    assert body["seller_fee_basis"] == "price_and_shipping"
    assert [tier["rate"] for tier in body["seller_fee_tiers"]] == [
        "0.10",
        "0.02",
    ]
    assert body["seller_fee_tiers"][1]["up_to"] is None


async def test_a_scale_without_a_final_open_tier_is_refused(
    client: AsyncClient,
) -> None:
    """Sans tranche finale ouverte, un montant au-delà du dernier palier ne
    saurait pas se calculer — et l'extrapoler serait inventer une règle."""

    response = await client.post(
        "/api/v1/platforms/ebay/rules",
        json={
            "provenance_url": "https://exemple.test/ebay",
            "seller_fee_tiers": [{"up_to": "2000.00", "rate": "0.10"}],
        },
    )
    assert response.status_code == 422


async def test_tiers_out_of_order_are_refused(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/platforms/ebay/rules",
        json={
            "provenance_url": "https://exemple.test/ebay",
            "seller_fee_tiers": [
                {"up_to": "5000.00", "rate": "0.10"},
                {"up_to": "2000.00", "rate": "0.05"},
                {"up_to": None, "rate": "0.02"},
            ],
        },
    )
    assert response.status_code == 422


async def test_an_unknown_fee_basis_is_refused(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/platforms/ebay/rules",
        json={
            "provenance_url": "https://exemple.test/ebay",
            "seller_fee_basis": "au_pif",
        },
    )
    assert response.status_code == 422


async def test_the_tiered_scale_reaches_the_analysis(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """Le chiffre qui compte : sur une revente à 3 600 €, eBay prélève 232 € de
    commission et non 360 €. Un taux unique de 10 % se tromperait de 128 €, et
    un taux unique de 2 % de 160 € dans l'autre sens."""

    await client.post(
        "/api/v1/platforms/ebay/rules",
        json={
            "provenance_url": "https://exemple.test/ebay",
            "seller_fee_tiers": _EBAY_TIERS,
            "currency": "EUR",
        },
    )
    await db_session.execute(
        text(
            """
            insert into portfolio_ledger_entries (portfolio_id, kind,
              amount_source, currency, amount_eur, rate_to_eur, fx_rate_at,
              fx_source, occurred_at, actor_user_id)
            select :pf, 'capital_contribution', 30000, 'EUR', 30000, 1, now(),
                   'saisie manuelle', now(), id from users limit 1
            """
        ),
        {"pf": default_portfolio_id},
    )
    await db_session.commit()

    opportunity = (
        await client.post(
            "/api/v1/opportunities",
            json={
                "portfolio_id": str(default_portfolio_id),
                "source": {"mode": "manual", "manual_identifier": "TRANCHES-001"},
                "watch": {
                    "brand": "Tudor",
                    "reference": "79030N",
                    "mechanical_condition": "verified",
                    "cosmetic_condition": "excellent",
                    "box": True,
                    "papers": True,
                },
                "seller": {"country_code": "FR", "seller_type": "private"},
                "price": {"amount": "2400.00", "currency": "EUR"},
            },
        )
    ).json()

    await client.post(
        f"/api/v1/opportunities/{opportunity['id']}/reference-confirmations",
        json={
            "status": "confirmed",
            "reference_id": opportunity["watch"]["reference_id"],
            "reason": "Référence vérifiée.",
        },
    )
    for index, amount in enumerate(
        ["3500.00", "3550.00", "3600.00", "3620.00", "3680.00", "3700.00"]
    ):
        await client.post(
            f"/api/v1/opportunities/{opportunity['id']}/comparables",
            json={
                "source_name": "Chrono24",
                "seller_fingerprint": f"t{index}",
                "price_kind": "asking",
                "amount": amount,
                "currency": "EUR",
                "market_status": "active",
                "observed_at": "2026-07-20T10:00:00Z",
                "source_reliability": "a",
                "mechanical_condition": "verified",
                "cosmetic_condition": "excellent",
                "box": True,
                "papers": True,
            },
        )
    await client.post(f"/api/v1/opportunities/{opportunity['id']}/valuations")
    await client.post(
        f"/api/v1/portfolios/{default_portfolio_id}/strategy",
        json={"resale_platform_code": "ebay"},
    )

    analysis = (
        await client.post(f"/api/v1/opportunities/{opportunity['id']}/analyses")
    ).json()
    central = analysis["scenario_results"]["central"]

    sale_price = Decimal(central["sale_price_eur"])
    commission = sale_price - Decimal(central["net_sale_proceeds_eur"])
    expected = Decimal("200.00") + (sale_price - Decimal("2000")) * Decimal("0.02")
    assert commission == expected.quantize(Decimal("0.01"))
