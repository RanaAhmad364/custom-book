import re


def authenticated_client(app, client, email):
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-battery"},
    )
    message = app.extensions["auth_email_outbox"][-1][2]
    code = re.search(r"\b(\d{6})\b", message).group(1)
    client.post("/api/v1/auth/verify-otp", json={"email": email, "code": code})
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery"})
    csrf = next(
        header.split(";", 1)[0].split("=", 1)[1]
        for header in login.headers.getlist("Set-Cookie")
        if header.startswith("csrf_access_token=")
    )
    return {"X-CSRF-TOKEN": csrf}


def test_print_legacy_contract_requires_authentication(client):
    response = client.post("/api/print/quotes")

    assert response.status_code == 401


def test_print_contract_requires_valid_quote_input_for_authenticated_request(app, client):
    csrf = authenticated_client(app, client, "print@example.test")

    versioned = client.post("/api/v1/print/quotes", json={}, headers=csrf)
    legacy = client.post("/api/print/quotes", json={}, headers=csrf)

    assert versioned.status_code == 400
    assert legacy.status_code == 400


def test_pdf_frontend_contract_paths_are_preserved(app, client):
    authenticated_client(app, client, "pdf@example.test")

    offer = client.get("/api/pdf/offer?projectId=project-1")
    order_list = client.get("/api/v1/pdf/downloads")

    assert offer.status_code == 404
    assert order_list.status_code == 200
    assert order_list.json["items"] == []
