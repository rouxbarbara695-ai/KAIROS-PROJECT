import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def test_me_returns_bootstrapped_principal(client: AsyncClient) -> None:
    response = await client.get("/api/v1/me")
    assert response.status_code == 200
    body = response.json()
    assert body["user_id"]
    assert len(body["portfolio_ids"]) >= 1
