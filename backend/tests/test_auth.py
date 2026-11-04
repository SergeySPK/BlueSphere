from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_schools_without_token_returns_401():
    response = client.get("/api/schools")

    assert response.status_code == 401
    assert response.json() == {"detail": "Требуется авторизация"}


def test_schools_with_invalid_token_returns_401():
    response = client.get(
        "/api/schools",
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Токен недействителен или устарел"}
