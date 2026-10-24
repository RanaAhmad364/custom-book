import re


def authenticated_client(app, email):
    client = app.test_client()
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-battery"},
    )
    assert response.status_code == 201
    message = app.extensions["auth_email_outbox"][-1][2]
    code = re.search(r"\b(\d{6})\b", message).group(1)
    assert client.post("/api/v1/auth/verify-otp", json={"email": email, "code": code}).status_code == 200
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery"})
    assert login.status_code == 200
    csrf = next(
        value.split(";", 1)[0].split("=", 1)[1]
        for value in login.headers.getlist("Set-Cookie")
        if value.startswith("csrf_access_token=")
    )
    return client, {"X-CSRF-TOKEN": csrf}


def test_shipping_addresses_are_persistent_and_owner_scoped(app):
    owner, csrf = authenticated_client(app, "address-owner@example.test")
    other, other_csrf = authenticated_client(app, "address-other@example.test")
    payload = {
        "recipientName": "A. Customer",
        "addressLine1": "10 Sample Road",
        "city": "Lahore",
        "postalCode": "54000",
        "countryCode": "pk",
    }

    first = owner.post("/api/v1/auth/me/addresses", json=payload, headers=csrf)
    assert first.status_code == 201
    assert first.json["address"]["isDefault"] is True
    second = owner.post(
        "/api/v1/auth/me/addresses",
        json={**payload, "recipientName": "Second recipient", "isDefault": False},
        headers=csrf,
    )
    assert second.status_code == 201

    addresses = owner.get("/api/v1/auth/me/addresses").json["items"]
    assert len(addresses) == 2
    assert addresses[0]["countryCode"] == "PK"
    assert sum(address["isDefault"] for address in addresses) == 1

    address_id = second.json["address"]["id"]
    assert other.delete(f"/api/v1/auth/me/addresses/{address_id}", headers=other_csrf).status_code == 404
    assert owner.delete(f"/api/v1/auth/me/addresses/{first.json['address']['id']}", headers=csrf).status_code == 204
    remaining = owner.get("/api/v1/auth/me/addresses").json["items"]
    assert len(remaining) == 1
    assert remaining[0]["isDefault"] is True

    invalid = owner.post(
        "/api/v1/auth/me/addresses",
        json={**payload, "countryCode": "USA"},
        headers=csrf,
    )
    assert invalid.status_code == 400


def test_notification_preferences_persist_per_user_and_validate_values(app):
    owner, csrf = authenticated_client(app, "preferences-owner@example.test")
    other, _ = authenticated_client(app, "preferences-other@example.test")

    initial = owner.get("/api/v1/auth/me/notification-preferences")
    assert initial.status_code == 200
    assert next(
        item for item in initial.json["items"]
        if item["channel"] == "email" and item["category"] == "order"
    )["enabled"] is True

    updated = owner.patch(
        "/api/v1/auth/me/notification-preferences",
        json={"channel": "email", "category": "product_news", "enabled": True},
        headers=csrf,
    )
    assert updated.status_code == 200
    saved = owner.get("/api/v1/auth/me/notification-preferences").json["items"]
    assert next(item for item in saved if item["category"] == "product_news")["enabled"] is True

    other_preferences = other.get("/api/v1/auth/me/notification-preferences").json["items"]
    assert next(item for item in other_preferences if item["category"] == "product_news")["enabled"] is False

    invalid = owner.patch(
        "/api/v1/auth/me/notification-preferences",
        json={"channel": "external", "category": "product_news", "enabled": True},
        headers=csrf,
    )
    assert invalid.status_code == 400
