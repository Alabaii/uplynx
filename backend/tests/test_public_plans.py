def test_public_plans_no_auth(client):
    response = client.get("/api/v1/plans")
    assert response.status_code == 200
    plans = response.json()
    assert [plan["slug"] for plan in plans] == ["free", "pro", "business"]
    assert plans[1]["price_monthly_kopeks"] == 99000
