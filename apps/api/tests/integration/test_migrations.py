import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


async def test_seed_platforms_and_ruleset_present(db_session: AsyncSession) -> None:
    # Les codes, pas leur nombre : un compteur casse à chaque ajout légitime
    # sans rien garantir sur ce qui est réellement présent.
    codes = set(
        (await db_session.execute(text("select code from platforms"))).scalars()
    )
    assert codes >= {
        "chrono24",
        "catawiki",
        "ebay",
        "vestiaire_collective",
        "watchcharts",
        "watchfinder",
        "independent_boutique",
        "user_data",
    }

    ruleset_version = (
        await db_session.execute(text("select version from rulesets limit 1"))
    ).scalar_one()
    assert ruleset_version == "1.0.0"


async def test_audit_events_are_append_only(db_session: AsyncSession) -> None:
    portfolio_id = uuid.uuid4()
    await db_session.execute(
        text("insert into portfolios (id, name) values (:id, 'test')"),
        {"id": portfolio_id},
    )
    event_id = uuid.uuid4()
    await db_session.execute(
        text(
            "insert into audit_events "
            "(id, portfolio_id, resource_type, resource_id, action, reason, "
            "after_data) "
            "values (:id, :portfolio_id, 'test', :resource_id, 'correct', 'r', "
            "'{}'::jsonb)"
        ),
        {"id": event_id, "portfolio_id": portfolio_id, "resource_id": uuid.uuid4()},
    )
    await db_session.commit()

    with pytest.raises(DBAPIError, match="IMMUTABLE_RESOURCE"):
        await db_session.execute(
            text("update audit_events set reason='hack' where id=:id"), {"id": event_id}
        )
    await db_session.rollback()


async def test_published_analysis_is_immutable_but_draft_is_not(
    db_session: AsyncSession,
) -> None:
    portfolio_id = uuid.uuid4()
    await db_session.execute(
        text("insert into portfolios (id, name) values (:id, 'test')"),
        {"id": portfolio_id},
    )
    user_id = uuid.uuid4()
    await db_session.execute(
        text("insert into users (id, email) values (:id, :email)"),
        {"id": user_id, "email": f"{user_id}@example.test"},
    )
    reference_id = uuid.uuid4()
    await db_session.execute(
        text(
            "insert into watch_references (id, brand, reference) "
            "values (:id, 'Test', 'REF-1')"
        ),
        {"id": reference_id},
    )
    watch_id = uuid.uuid4()
    await db_session.execute(
        text("insert into watches (id, reference_id) values (:id, :reference_id)"),
        {"id": watch_id, "reference_id": reference_id},
    )
    opportunity_id = uuid.uuid4()
    await db_session.execute(
        text(
            "insert into opportunities "
            "(id, portfolio_id, created_by_user_id, source_mode, "
            "manual_identifier, watch_id) "
            "values (:id, :portfolio_id, :user_id, 'manual', 'REF-1', :watch_id)"
        ),
        {
            "id": opportunity_id,
            "portfolio_id": portfolio_id,
            "user_id": user_id,
            "watch_id": watch_id,
        },
    )
    ruleset_id = (
        await db_session.execute(text("select id from rulesets limit 1"))
    ).scalar_one()

    analysis_id = uuid.uuid4()
    await db_session.execute(
        text(
            "insert into analyses "
            "(id, portfolio_id, opportunity_id, ruleset_id, trigger_type, state, "
            "recommendation, ruleset_snapshot) "
            "values (:id, :portfolio_id, :opportunity_id, :ruleset_id, 'manual', "
            "'draft', 'analysis_impossible', '{}'::jsonb)"
        ),
        {
            "id": analysis_id,
            "portfolio_id": portfolio_id,
            "opportunity_id": opportunity_id,
            "ruleset_id": ruleset_id,
        },
    )
    await db_session.commit()

    # Brouillon : modifiable.
    await db_session.execute(
        text("update analyses set trigger_type='manual_retry' where id=:id"),
        {"id": analysis_id},
    )
    await db_session.commit()

    # Publication.
    await db_session.execute(
        text("update analyses set state='published', published_at=now() where id=:id"),
        {"id": analysis_id},
    )
    await db_session.commit()

    with pytest.raises(DBAPIError, match="IMMUTABLE_RESOURCE"):
        await db_session.execute(
            text("update analyses set trigger_type='hack' where id=:id"),
            {"id": analysis_id},
        )
    await db_session.rollback()


async def test_cross_portfolio_relation_rejected(db_session: AsyncSession) -> None:
    portfolio_a = uuid.uuid4()
    portfolio_b = uuid.uuid4()
    await db_session.execute(
        text("insert into portfolios (id, name) values (:a, 'A'), (:b, 'B')"),
        {"a": portfolio_a, "b": portfolio_b},
    )
    seller_b = uuid.uuid4()
    await db_session.execute(
        text("insert into sellers (id, portfolio_id) values (:id, :portfolio_id)"),
        {"id": seller_b, "portfolio_id": portfolio_b},
    )
    reference_id = uuid.uuid4()
    await db_session.execute(
        text(
            "insert into watch_references (id, brand, reference) "
            "values (:id, 'Test', 'REF-2')"
        ),
        {"id": reference_id},
    )
    watch_id = uuid.uuid4()
    await db_session.execute(
        text("insert into watches (id, reference_id) values (:id, :reference_id)"),
        {"id": watch_id, "reference_id": reference_id},
    )
    user_id = uuid.uuid4()
    await db_session.execute(
        text("insert into users (id, email) values (:id, :email)"),
        {"id": user_id, "email": f"{user_id}@example.test"},
    )
    await db_session.commit()

    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "insert into opportunities "
                "(id, portfolio_id, created_by_user_id, source_mode, "
                "manual_identifier, watch_id, seller_id) "
                "values (:id, :portfolio_id, :user_id, 'manual', "
                "'REF-2', :watch_id, :seller_id)"
            ),
            {
                "id": uuid.uuid4(),
                "portfolio_id": portfolio_a,
                "user_id": user_id,
                "watch_id": watch_id,
                "seller_id": seller_b,
            },
        )
    await db_session.rollback()


async def test_overlapping_platform_rules_rejected(db_session: AsyncSession) -> None:
    platform_id = (
        await db_session.execute(text("select id from platforms limit 1"))
    ).scalar_one()

    await db_session.execute(
        text(
            "insert into platform_rules "
            "(platform_id, region_code, version, valid_from, valid_to) "
            "values (:platform_id, '*', 101, '2026-01-01', '2026-12-31')"
        ),
        {"platform_id": platform_id},
    )
    await db_session.commit()

    with pytest.raises(DBAPIError, match="exclusion constraint"):
        await db_session.execute(
            text(
                "insert into platform_rules "
                "(platform_id, region_code, version, valid_from, valid_to) "
                "values (:platform_id, '*', 102, '2026-06-01', '2027-01-01')"
            ),
            {"platform_id": platform_id},
        )
    await db_session.rollback()


async def test_unauthorized_collection_job_rejected(db_session: AsyncSession) -> None:
    platform_id = (
        await db_session.execute(text("select id from platforms limit 1"))
    ).scalar_one()
    portfolio_id = uuid.uuid4()
    await db_session.execute(
        text("insert into portfolios (id, name) values (:id, 'test')"),
        {"id": portfolio_id},
    )
    rule_id = uuid.uuid4()
    await db_session.execute(
        text(
            "insert into platform_rules "
            "(id, platform_id, region_code, version, valid_from) "
            "values (:id, :platform_id, '*', 201, now())"
        ),
        {"id": rule_id, "platform_id": platform_id},
    )
    await db_session.commit()

    with pytest.raises(DBAPIError, match="COLLECTOR_NOT_AUTHORIZED"):
        await db_session.execute(
            text(
                "insert into collection_jobs "
                "(portfolio_id, platform_id, platform_rule_id, idempotency_key) "
                "values (:portfolio_id, :platform_id, :rule_id, 'job-1')"
            ),
            {
                "portfolio_id": portfolio_id,
                "platform_id": platform_id,
                "rule_id": rule_id,
            },
        )
    await db_session.rollback()
