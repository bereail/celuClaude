from conftest import TEST_EMAIL, TEST_PASSWORD


def test_login_success(client):
    res = client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    assert res.status_code == 200
    body = res.json()
    assert body["access_token"] and body["refresh_token"]


def test_login_wrong_password(client):
    res = client.post("/auth/login", json={"email": TEST_EMAIL, "password": "wrong"})
    assert res.status_code == 401


def test_login_wrong_email(client):
    res = client.post("/auth/login", json={"email": "someone-else@example.com", "password": TEST_PASSWORD})
    assert res.status_code == 401


def test_login_rate_limited_after_five_failed_attempts(client):
    for _ in range(5):
        client.post("/auth/login", json={"email": TEST_EMAIL, "password": "wrong"})
    res = client.post("/auth/login", json={"email": TEST_EMAIL, "password": "wrong"})
    assert res.status_code == 429


def test_refresh_with_access_token_is_rejected(client):
    login = client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}).json()
    res = client.post("/auth/refresh", json={"refresh_token": login["access_token"]})
    assert res.status_code == 401
