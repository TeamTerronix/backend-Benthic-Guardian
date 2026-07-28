"""Auth API tests."""

from fastapi.testclient import TestClient

from models import User


def test_register_login_and_me(client: TestClient):
    register = client.post(
        "/auth/register",
        json={"email": "new.user@example.com", "password": "secure-pass-1"},
    )
    assert register.status_code == 201
    body = register.json()
    assert body["email"] == "new.user@example.com"
    assert body["role"] == "user"
    assert "id" in body

    login = client.post(
        "/auth/token",
        data={"username": "new.user@example.com", "password": "secure-pass-1"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    assert login.json()["token_type"] == "bearer"

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "new.user@example.com"


def test_register_duplicate_email(client: TestClient, regular_user: User):
    response = client.post(
        "/auth/register",
        json={"email": regular_user.email, "password": "another-pass"},
    )
    assert response.status_code == 400
    assert "already registered" in response.json()["detail"].lower()


def test_login_wrong_password(client: TestClient, regular_user: User):
    response = client.post(
        "/auth/token",
        data={"username": regular_user.email, "password": "not-the-password"},
    )
    assert response.status_code == 401


def test_me_requires_auth(client: TestClient):
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_me_with_token(client: TestClient, auth_headers: dict[str, str], regular_user: User):
    response = client.get("/auth/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["email"] == regular_user.email
