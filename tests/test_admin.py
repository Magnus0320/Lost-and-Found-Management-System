"""The staff role.

Admins exist because the lifecycle has no oversight otherwise: a reporter
decides the claims on their own item, so a wrong decision has nobody to correct
it. These tests pin down both halves -- what an admin may do, and what is still
refused to everyone else.
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


@pytest.fixture
def admin_headers(client, auth_headers):
    """A verified account promoted to staff, plus its bearer header."""

    def _make():
        headers = auth_headers()
        me = client.get("/auth/me", headers=headers).json()
        # Promotion is out-of-band by design: see scripts/make_admin.py.
        from app.db.session import SessionLocal
        from app.repositories.user_repo import UserRepository

        with SessionLocal() as db:
            repo = UserRepository(db)
            repo.set_admin(repo.get(me["id"]), True)
            db.commit()
        return headers

    return _make


# --- the gate -------------------------------------------------------------

ADMIN_ROUTES = [
    ("get", "/admin/stats", None),
    ("get", "/admin/users", None),
    ("post", "/admin/items/bulk-delete", {"item_ids": [1]}),
    ("delete", "/admin/items/1", None),
    ("delete", "/admin/users/1", None),
    ("delete", "/admin/locations/1", None),
    ("delete", "/admin/categories/1", None),
    ("post", "/admin/users/1/role", {"is_admin": True}),
]


@pytest.mark.parametrize("method,path,body", ADMIN_ROUTES)
def test_admin_routes_reject_anonymous_callers(client, method, path, body):
    kwargs = {"json": body} if body is not None else {}
    assert getattr(client, method)(path, **kwargs).status_code == 401


@pytest.mark.parametrize("method,path,body", ADMIN_ROUTES)
def test_admin_routes_reject_ordinary_users(client, auth_headers, method, path, body):
    kwargs = {"json": body} if body is not None else {}
    resp = getattr(client, method)(path, headers=auth_headers(), **kwargs)
    assert resp.status_code == 403, resp.text


def test_is_admin_is_false_by_default(client, auth_headers):
    assert client.get("/auth/me", headers=auth_headers()).json()["is_admin"] is False


def test_the_flag_is_reported_to_the_client(client, admin_headers):
    assert client.get("/auth/me", headers=admin_headers()).json()["is_admin"] is True


# --- managing items -------------------------------------------------------

def test_admin_can_delete_an_item_they_did_not_report(client, auth_headers, admin_headers):
    owner, admin = auth_headers(), admin_headers()
    item = _mk_item(client, owner)
    assert client.delete(f"/admin/items/{item['id']}", headers=admin).status_code == 200
    assert client.get(f"/items/{item['id']}").status_code == 404


def test_an_ordinary_user_still_cannot_delete_someone_elses_item(client, auth_headers):
    owner, other = auth_headers(), auth_headers()
    item = _mk_item(client, owner)
    assert client.delete(f"/items/{item['id']}", headers=other).status_code == 403


def test_admin_can_transition_and_edit_any_item(client, auth_headers, admin_headers):
    owner, admin = auth_headers(), admin_headers()
    item = _mk_item(client, owner)
    assert client.post(f"/items/{item['id']}/status", headers=admin,
                       json={"to_status": "matched"}).status_code == 200
    assert client.patch(f"/items/{item['id']}", headers=admin,
                        json={"name": "Renamed by staff"}).status_code == 200


def test_bulk_delete_removes_many_items(client, auth_headers, admin_headers):
    owner, admin = auth_headers(), admin_headers()
    ids = [_mk_item(client, owner)["id"] for _ in range(3)]
    resp = client.post("/admin/items/bulk-delete", headers=admin, json={"item_ids": ids})
    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"] == 3
    for i in ids:
        assert client.get(f"/items/{i}").status_code == 404


def test_bulk_delete_tolerates_ids_that_are_already_gone(client, auth_headers, admin_headers):
    owner, admin = auth_headers(), admin_headers()
    item = _mk_item(client, owner)
    body = {"item_ids": [item["id"], 99_000_001, 99_000_002]}
    resp = client.post("/admin/items/bulk-delete", headers=admin, json=body)
    assert resp.status_code == 200
    assert (resp.json()["requested"], resp.json()["deleted"]) == (3, 1)


def test_bulk_delete_rejects_an_empty_or_oversized_list(client, admin_headers):
    admin = admin_headers()
    assert client.post("/admin/items/bulk-delete", headers=admin,
                       json={"item_ids": []}).status_code == 422
    assert client.post("/admin/items/bulk-delete", headers=admin,
                       json={"item_ids": list(range(1, 502))}).status_code == 422


# --- managing claims ------------------------------------------------------

def test_admin_sees_claims_they_are_not_a_party_to(client, auth_headers, admin_headers):
    owner, claimant, admin = auth_headers(), auth_headers(), admin_headers()
    item = _mk_item(client, owner)
    claim = client.post(f"/items/{item['id']}/claims", headers=claimant,
                        json={"evidence": "serial matches"}).json()

    rows = client.get("/claims", headers=admin,
                      params={"item_id": item["id"]}).json()["results"]
    assert [c["id"] for c in rows] == [claim["id"]]


def test_admin_can_decide_someone_elses_claim(client, auth_headers, admin_headers):
    owner, claimant, admin = auth_headers(), auth_headers(), admin_headers()
    item = _mk_item(client, owner)
    claim = client.post(f"/items/{item['id']}/claims", headers=claimant,
                        json={"evidence": "serial matches"}).json()

    resp = client.post(f"/claims/{claim['id']}/decision", headers=admin,
                       json={"approve": True})
    assert resp.status_code == 200, resp.text
    assert client.get(f"/items/{item['id']}").json()["status"] == "claimed"


# --- managing accounts ----------------------------------------------------

def test_admin_can_list_and_search_accounts(client, auth_headers, admin_headers):
    admin = admin_headers()
    headers = auth_headers()
    target = client.get("/auth/me", headers=headers).json()

    body = client.get("/admin/users", headers=admin,
                      params={"q": target["email"]}).json()
    assert [u["id"] for u in body["results"]] == [target["id"]]


def test_admin_can_promote_and_demote_another_account(client, auth_headers, admin_headers):
    admin = admin_headers()
    other = auth_headers()
    other_id = client.get("/auth/me", headers=other).json()["id"]

    granted = client.post(f"/admin/users/{other_id}/role", headers=admin,
                          json={"is_admin": True})
    assert granted.status_code == 200 and granted.json()["is_admin"] is True
    # The promotion is real: the newly-made admin can use an admin route.
    assert client.get("/admin/stats", headers=other).status_code == 200

    revoked = client.post(f"/admin/users/{other_id}/role", headers=admin,
                          json={"is_admin": False})
    assert revoked.status_code == 200 and revoked.json()["is_admin"] is False
    assert client.get("/admin/stats", headers=other).status_code == 403


def test_an_admin_cannot_demote_themselves(client, admin_headers):
    admin = admin_headers()
    me = client.get("/auth/me", headers=admin).json()
    resp = client.post(f"/admin/users/{me['id']}/role", headers=admin,
                       json={"is_admin": False})
    assert resp.status_code == 422
    assert client.get("/auth/me", headers=admin).json()["is_admin"] is True


def test_an_admin_cannot_delete_themselves(client, admin_headers):
    admin = admin_headers()
    me = client.get("/auth/me", headers=admin).json()
    assert client.delete(f"/admin/users/{me['id']}", headers=admin).status_code == 422


def test_deleting_an_admin_requires_demoting_them_first(client, auth_headers, admin_headers):
    admin, victim = admin_headers(), admin_headers()
    victim_id = client.get("/auth/me", headers=victim).json()["id"]

    assert client.delete(f"/admin/users/{victim_id}", headers=admin).status_code == 422
    client.post(f"/admin/users/{victim_id}/role", headers=admin, json={"is_admin": False})
    assert client.delete(f"/admin/users/{victim_id}", headers=admin).status_code == 200


def test_deleting_an_account_takes_its_items_with_it(client, auth_headers, admin_headers):
    admin, owner = admin_headers(), auth_headers()
    owner_id = client.get("/auth/me", headers=owner).json()["id"]
    item = _mk_item(client, owner)

    assert client.delete(f"/admin/users/{owner_id}", headers=admin).status_code == 200
    assert client.get(f"/items/{item['id']}").status_code == 404


def test_stats_report_real_counts(client, auth_headers, admin_headers):
    admin = admin_headers()
    before = client.get("/admin/stats", headers=admin).json()
    _mk_item(client, auth_headers())
    after = client.get("/admin/stats", headers=admin).json()
    assert after["items"] == before["items"] + 1
    assert after["admins"] >= 1


# --- reference data -------------------------------------------------------

def test_admin_can_delete_a_location_without_deleting_its_items(client, auth_headers, admin_headers):
    admin, owner = admin_headers(), auth_headers()
    loc = client.post("/locations", headers=owner,
                      json={"name": f"Block {uuid.uuid4().hex[:6]}"}).json()
    item = _mk_item(client, owner, location_id=loc["id"])

    assert client.delete(f"/admin/locations/{loc['id']}", headers=admin).status_code == 200
    body = client.get(f"/items/{item['id']}")
    assert body.status_code == 200 and body.json()["location"] is None


def test_deleting_an_unknown_location_is_404(client, admin_headers):
    assert client.delete("/admin/locations/99999999",
                         headers=admin_headers()).status_code == 404
