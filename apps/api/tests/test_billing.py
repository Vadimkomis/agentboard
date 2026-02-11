from httpx import AsyncClient

from src.models.user import User


async def test_list_plans(auth_client: AsyncClient):
    resp = await auth_client.get("/api/billing/plans")
    assert resp.status_code == 200
    plans = resp.json()
    assert len(plans) == 3

    plan_ids = {p["id"] for p in plans}
    assert plan_ids == {"free", "pro", "team"}

    # Verify free plan
    free = next(p for p in plans if p["id"] == "free")
    assert free["price_monthly"] == 0
    assert free["execution_quota"] == 50

    # Verify pro plan
    pro = next(p for p in plans if p["id"] == "pro")
    assert pro["price_monthly"] == 29
    assert pro["execution_quota"] == 500

    # Verify team plan
    team = next(p for p in plans if p["id"] == "team")
    assert team["price_monthly"] == 79
    assert team["execution_quota"] == 2000


async def test_get_usage_free_tier(auth_client: AsyncClient, user: User):
    resp = await auth_client.get("/api/billing/usage")
    assert resp.status_code == 200
    data = resp.json()
    assert data["plan_tier"] == "free"
    assert data["execution_quota"] == 50
    assert data["executions_used"] == 0
    assert data["remaining"] == 50


async def test_checkout_invalid_plan(auth_client: AsyncClient):
    resp = await auth_client.post(
        "/api/billing/checkout",
        json={"plan_id": "nonexistent"},
    )
    assert resp.status_code == 400


async def test_checkout_free_plan_rejected(auth_client: AsyncClient):
    resp = await auth_client.post(
        "/api/billing/checkout",
        json={"plan_id": "free"},
    )
    assert resp.status_code == 400


async def test_checkout_without_stripe_configured(auth_client: AsyncClient):
    """Without STRIPE_SECRET_KEY, checkout should return 503."""
    resp = await auth_client.post(
        "/api/billing/checkout",
        json={"plan_id": "pro"},
    )
    assert resp.status_code == 503
