from httpx import AsyncClient


async def test_health_endpoint(unauth_client: AsyncClient):
    resp = await unauth_client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
