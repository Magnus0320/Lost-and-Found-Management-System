"""Integration tests against a real PostgreSQL.

Skipped automatically when no database is reachable (see tests/conftest.py).
"""
import uuid

import pytest


def _mk_item(client, headers, **overrides):
    payload = {
        "name": f"Item {uuid.uuid4().hex[:8]}",
        "description": "A described object left somewhere",
        "kind": "found",
        "occurred_on": "2026-08-01",
    }
    payload.update(overrides)
    resp = client.post("/items", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_health_reports_the_database(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["database"] == "reachable"


def test_openapi_is_served(client):
    assert client.get("/openapi.json").status_code == 200


def test_registration_requires_otp_before_login(client):
    tag = uuid.uuid4().hex[:10]
    email = f"unverified-{tag}@campus.edu"
    reg = client.post("/auth/register", json={
        "email": email, "password": "correct-horse-battery", "first_name": "N",
        "last_name": "V", "roll_number": f"R{tag[:8]}", "batch": 2026,
        "course": "BTECH", "branch": "CSE"})
    assert reg.status_code == 201
    denied = client.post("/auth/login", json={
        "email": email, "password": "correct-horse-battery"})
    assert denied.status_code == 401


def test_duplicate_registration_conflicts(client, auth_headers):
    tag = uuid.uuid4().hex[:10]
    email = f"dupe-{tag}@campus.edu"
    body = {"email": email, "password": "correct-horse-battery", "first_name": "D",
            "last_name": "U", "roll_number": f"R{tag[:8]}", "batch": 2026,
            "course": "BTECH", "branch": "CSE"}
    assert client.post("/auth/register", json=body).status_code == 201
    assert client.post("/auth/register", json=body).status_code == 409


def test_password_reset_round_trip(client):
    tag = uuid.uuid4().hex[:10]
    email = f"reset-{tag}@campus.edu"
    reg = client.post("/auth/register", json={
        "email": email, "password": "original-password-1", "first_name": "R",
        "last_name": "P", "roll_number": f"R{tag[:8]}", "batch": 2026,
        "course": "BTECH", "branch": "CSE"})
    client.post("/auth/verify-registration",
                json={"email": email, "otp": reg.json()["otp_debug"]})
    req = client.post("/auth/password-reset/request", json={"email": email})
    assert req.status_code == 200
    otp = req.json()["otp_debug"]
    done = client.post("/auth/password-reset/confirm", json={
        "email": email, "otp": otp, "new_password": "brand-new-password-2"})
    assert done.status_code == 200
    assert client.post("/auth/login", json={
        "email": email, "password": "brand-new-password-2"}).status_code == 200
    assert client.post("/auth/login", json={
        "email": email, "password": "original-password-1"}).status_code == 401


def test_bad_otp_is_rejected(client):
    tag = uuid.uuid4().hex[:10]
    email = f"badotp-{tag}@campus.edu"
    client.post("/auth/register", json={
        "email": email, "password": "correct-horse-battery", "first_name": "B",
        "last_name": "O", "roll_number": f"R{tag[:8]}", "batch": 2026,
        "course": "BTECH", "branch": "CSE"})
    assert client.post("/auth/verify-registration",
                       json={"email": email, "otp": "000000"}).status_code == 422


def test_item_starts_in_reported(client, auth_headers):
    item = _mk_item(client, auth_headers())
    assert item["status"] == "reported"


def test_location_is_a_joined_entity_not_a_string(client, auth_headers):
    headers = auth_headers()
    loc = client.post("/locations", headers=headers, json={
        "name": f"Hostel {uuid.uuid4().hex[:6]}", "building": "H7"}).json()
    item = _mk_item(client, headers, location_id=loc["id"])
    assert item["location"]["id"] == loc["id"]
    assert item["location"]["building"] == "H7"


def test_search_matches_name_and_description(client, auth_headers):
    headers = auth_headers()
    tag = uuid.uuid4().hex[:8]
    _mk_item(client, headers, name=f"Umbrella {tag}",
             description=f"striped canopy {tag}")
    assert client.get("/items", params={"q": tag}).json()["total"] >= 1
    assert client.get("/items", params={"q": f"striped canopy {tag}"}
                      ).json()["total"] == 1
    assert client.get("/items", params={"q": f"nothing-{tag}"}).json()["total"] == 0


def test_search_filters_by_category_and_status(client, auth_headers):
    headers = auth_headers()
    cat = client.post("/categories", headers=headers, json={
        "name": f"Cat {uuid.uuid4().hex[:6]}"}).json()
    _mk_item(client, headers, category_id=cat["id"])
    assert client.get("/items", params={"category_id": cat["id"]}).json()["total"] == 1
    assert client.get("/items", params={
        "category_id": cat["id"], "status": "closed"}).json()["total"] == 0


def test_search_rejects_a_bad_limit(client):
    assert client.get("/items", params={"limit": 0}).status_code == 422
    assert client.get("/items", params={"limit": 500}).status_code == 422


def test_illegal_transition_is_refused(client, auth_headers):
    headers = auth_headers()
    item = _mk_item(client, headers)
    # reported -> claimed skips 'matched'
    resp = client.post(f"/items/{item['id']}/status", headers=headers,
                       json={"to_status": "claimed"})
    assert resp.status_code == 422
    assert "Cannot move item" in resp.json()["detail"]


def test_full_lifecycle_is_recorded(client, auth_headers):
    headers = auth_headers()
    item = _mk_item(client, headers)
    for state in ("matched", "claimed", "closed"):
        resp = client.post(f"/items/{item['id']}/status", headers=headers,
                           json={"to_status": state})
        assert resp.status_code == 200, resp.text
    history = [e["to_status"] for e in resp.json()["status_events"]]
    assert history == ["reported", "matched", "claimed", "closed"]


def test_closed_is_terminal_over_http(client, auth_headers):
    headers = auth_headers()
    item = _mk_item(client, headers)
    client.post(f"/items/{item['id']}/status", headers=headers,
                json={"to_status": "closed"})
    assert client.post(f"/items/{item['id']}/status", headers=headers,
                       json={"to_status": "matched"}).status_code == 422


def test_claim_advances_item_and_approval_claims_it(client, auth_headers):
    owner, claimant = auth_headers(), auth_headers()
    item = _mk_item(client, owner)
    claim = client.post(f"/items/{item['id']}/claims", headers=claimant,
                        json={"evidence": "receipt serial matches"})
    assert claim.status_code == 201
    assert client.get(f"/items/{item['id']}").json()["status"] == "matched"
    assert client.post(f"/claims/{claim.json()['id']}/decision", headers=owner,
                       json={"approve": True}).status_code == 200
    assert client.get(f"/items/{item['id']}").json()["status"] == "claimed"


def test_cannot_claim_your_own_item(client, auth_headers):
    headers = auth_headers()
    item = _mk_item(client, headers)
    resp = client.post(f"/items/{item['id']}/claims", headers=headers,
                       json={"evidence": "it is mine"})
    assert resp.status_code == 422


def test_duplicate_claim_conflicts(client, auth_headers):
    owner, claimant = auth_headers(), auth_headers()
    item = _mk_item(client, owner)
    body = {"evidence": "mine"}
    assert client.post(f"/items/{item['id']}/claims", headers=claimant,
                       json=body).status_code == 201
    assert client.post(f"/items/{item['id']}/claims", headers=claimant,
                       json=body).status_code == 409


def test_only_reporter_can_decide_a_claim(client, auth_headers):
    owner, claimant = auth_headers(), auth_headers()
    item = _mk_item(client, owner)
    claim = client.post(f"/items/{item['id']}/claims", headers=claimant,
                        json={"evidence": "mine"}).json()
    resp = client.post(f"/claims/{claim['id']}/decision", headers=claimant,
                       json={"approve": True})
    assert resp.status_code == 403


@pytest.mark.parametrize("method,path", [
    ("post", "/items"), ("get", "/notifications"), ("post", "/locations"),
    ("get", "/claims"),
])
def test_protected_routes_require_a_token(client, method, path):
    kwargs = {"json": {}} if method == "post" else {}
    assert getattr(client, method)(path, **kwargs).status_code == 401


def test_non_reporter_cannot_delete(client, auth_headers):
    owner, other = auth_headers(), auth_headers()
    item = _mk_item(client, owner)
    assert client.delete(f"/items/{item['id']}", headers=other).status_code == 403
    assert client.delete(f"/items/{item['id']}", headers=owner).status_code == 200


def test_unknown_item_is_404(client):
    assert client.get("/items/99999999").status_code == 404


def test_transition_notifies_the_reporter(client, auth_headers):
    headers = auth_headers()
    item = _mk_item(client, headers)
    client.post(f"/items/{item['id']}/status", headers=headers,
                json={"to_status": "matched"})
    assert client.get("/notifications", headers=headers).json()["total"] >= 1
