"""Claim decisions: one approval per item, and items that do not get stuck.

* Approval is exclusive. Approving one claim rejects every other pending claim
  on the item, a second approval is refused while one stands, and the database
  enforces the same rule underneath with a partial unique index.
* A rejection that leaves a `matched` item with nothing pending or approved
  sends it back to `reported`.
* Withdrawing an approval (claimed -> matched) reopens the claims it
  auto-rejected, since they lost to it rather than on their own merits.
* An item cannot be relisted (matched -> reported) over pending claims, and a
  claim can only be approved while its item is `matched`.
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


def _claim(client, item_id, headers, evidence="serial number matches"):
    resp = client.post(f"/items/{item_id}/claims", headers=headers,
                       json={"evidence": evidence})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _decide(client, claim_id, headers, approve, note=None):
    body = {"approve": approve}
    if note is not None:
        body["note"] = note
    return client.post(f"/claims/{claim_id}/decision", headers=headers, json=body)


def _statuses(client, item_id, owner):
    rows = client.get("/claims", headers=owner, params={"item_id": item_id}).json()["results"]
    return {c["id"]: c["status"] for c in rows}


def _item(client, item_id):
    return client.get(f"/items/{item_id}").json()


def _messages(client, headers):
    return [n["message"] for n in client.get("/notifications", headers=headers).json()["results"]]


# --- approval is exclusive ------------------------------------------------

def test_approving_rejects_every_other_pending_claim(client, auth_headers):
    owner, a, b, c = (auth_headers() for _ in range(4))
    item = _mk_item(client, owner)
    ca, cb, cc = (_claim(client, item["id"], h) for h in (a, b, c))

    assert _decide(client, ca["id"], owner, True).status_code == 200

    assert _statuses(client, item["id"], owner) == {
        ca["id"]: "approved", cb["id"]: "rejected", cc["id"]: "rejected",
    }
    assert _item(client, item["id"])["status"] == "claimed"


def test_auto_rejected_claimants_are_told_why(client, auth_headers):
    owner, a, b = auth_headers(), auth_headers(), auth_headers()
    item = _mk_item(client, owner)
    ca = _claim(client, item["id"], a)
    _claim(client, item["id"], b)
    _decide(client, ca["id"], owner, True)

    assert any("another claim was approved" in m for m in _messages(client, b))
    # ...and they get no contact details: only the approved claimant does.
    body = client.get(f"/items/{item['id']}", headers=b).json()
    assert body["reporter"]["contact_email"] is None


def test_a_second_approval_is_refused(client, auth_headers):
    owner, a, late = auth_headers(), auth_headers(), auth_headers()
    item = _mk_item(client, owner)
    ca = _claim(client, item["id"], a)
    _decide(client, ca["id"], owner, True)

    # A claim can still be filed on a claimed item; it just cannot win -- and
    # filing it must not knock the item back to 'matched'.
    cl = _claim(client, item["id"], late)
    assert _item(client, item["id"])["status"] == "claimed"
    resp = _decide(client, cl["id"], owner, True)
    assert resp.status_code == 409, resp.text
    assert "already has an approved claim" in resp.json()["detail"]

    assert _statuses(client, item["id"], owner) == {ca["id"]: "approved", cl["id"]: "pending"}
    assert client.get(f"/items/{item['id']}",
                      headers=late).json()["reporter"]["contact_email"] is None


def test_an_admin_cannot_approve_a_second_claim_either(client, auth_headers):
    from app.db.session import SessionLocal
    from app.repositories.user_repo import UserRepository

    owner, a, late, admin = (auth_headers() for _ in range(4))
    admin_id = client.get("/auth/me", headers=admin).json()["id"]
    with SessionLocal() as db:
        repo = UserRepository(db)
        repo.set_admin(repo.get(admin_id), True)
        db.commit()

    item = _mk_item(client, owner)
    _decide(client, _claim(client, item["id"], a)["id"], owner, True)
    cl = _claim(client, item["id"], late)
    assert _decide(client, cl["id"], admin, True).status_code == 409


def test_rejecting_a_late_claim_leaves_a_claimed_item_alone(client, auth_headers):
    owner, a, late = auth_headers(), auth_headers(), auth_headers()
    item = _mk_item(client, owner)
    _decide(client, _claim(client, item["id"], a)["id"], owner, True)
    cl = _claim(client, item["id"], late)

    assert _decide(client, cl["id"], owner, False).status_code == 200
    assert _item(client, item["id"])["status"] == "claimed"


# --- the database backs the rule up ---------------------------------------

def test_the_database_refuses_two_approved_claims_on_one_item(client, auth_headers):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    from app.db.session import engine

    owner, a, b = auth_headers(), auth_headers(), auth_headers()
    item = _mk_item(client, owner)
    ca, cb = _claim(client, item["id"], a), _claim(client, item["id"], b)

    with pytest.raises(IntegrityError, match="uq_claims_one_approved_per_item"):
        with engine.begin() as conn:
            conn.execute(text("UPDATE claims SET status = 'approved' WHERE id IN (:a, :b)"),
                         {"a": ca["id"], "b": cb["id"]})
    assert set(_statuses(client, item["id"], owner).values()) == {"pending"}


def test_a_racing_approval_surfaces_as_a_conflict(client, auth_headers):
    """If two approvals slip past the service check, the index turns the
    loser into a 409 rather than a 500."""
    from sqlalchemy import text

    from app.core.errors import ConflictError
    from app.db.session import SessionLocal, engine
    from app.repositories.claim_repo import ClaimRepository

    owner, a, b = auth_headers(), auth_headers(), auth_headers()
    item = _mk_item(client, owner)
    ca, cb = _claim(client, item["id"], a), _claim(client, item["id"], b)
    with engine.begin() as conn:  # the approval that "won the race"
        conn.execute(text("UPDATE claims SET status = 'approved' WHERE id = :id"),
                     {"id": ca["id"]})

    owner_id = client.get("/auth/me", headers=owner).json()["id"]
    with SessionLocal() as db:
        repo = ClaimRepository(db)
        with pytest.raises(ConflictError) as exc:
            repo.decide(repo.get(cb["id"]), True, decided_by_id=owner_id)
        db.rollback()
    assert "uq_claims_one_approved_per_item" in str(exc.value.__cause__)


# --- rejection no longer strands an item on 'matched' ---------------------

def test_rejecting_the_only_claim_sends_the_item_back_to_reported(client, auth_headers):
    owner, a = auth_headers(), auth_headers()
    item = _mk_item(client, owner)
    ca = _claim(client, item["id"], a)
    assert _item(client, item["id"])["status"] == "matched"

    assert _decide(client, ca["id"], owner, False, note="Wrong colour.").status_code == 200

    body = _item(client, item["id"])
    assert body["status"] == "reported"
    last = body["status_events"][-1]
    assert (last["from_status"], last["to_status"]) == ("matched", "reported")
    assert last["note"] == "All claims rejected. Wrong colour."


def test_rejection_stays_matched_while_other_claims_are_pending(client, auth_headers):
    owner, a, b = auth_headers(), auth_headers(), auth_headers()
    item = _mk_item(client, owner)
    ca, cb = _claim(client, item["id"], a), _claim(client, item["id"], b)

    _decide(client, ca["id"], owner, False)
    body = _item(client, item["id"])
    assert body["status"] == "matched"
    assert body["status_events"][-1]["to_status"] == "matched"

    _decide(client, cb["id"], owner, False)
    body = _item(client, item["id"])
    assert body["status"] == "reported"
    assert body["status_events"][-1]["note"] == "All claims rejected."


def test_a_relisted_item_can_be_claimed_again(client, auth_headers):
    owner, a, b = auth_headers(), auth_headers(), auth_headers()
    item = _mk_item(client, owner)
    _decide(client, _claim(client, item["id"], a)["id"], owner, False)

    _claim(client, item["id"], b)
    assert _item(client, item["id"])["status"] == "matched"


# --- withdrawing an approval -----------------------------------------------

def test_withdrawing_an_approval_reopens_the_claims_it_rejected(client, auth_headers):
    owner, a, b, c = (auth_headers() for _ in range(4))
    item = _mk_item(client, owner)
    ca, cb, cc = (_claim(client, item["id"], h) for h in (a, b, c))
    _decide(client, cc["id"], owner, False)  # rejected on its merits
    _decide(client, ca["id"], owner, True)   # auto-rejects b

    resp = client.post(f"/items/{item['id']}/status", headers=owner,
                       json={"to_status": "matched"})
    assert resp.status_code == 200, resp.text

    # a and b are both open again; c's rejection was a real decision and stands.
    assert _statuses(client, item["id"], owner) == {
        ca["id"]: "pending", cb["id"]: "pending", cc["id"]: "rejected",
    }
    assert any("pending again" in m for m in _messages(client, b))
    # Neither pending claimant can see the reporter's address.
    for who in (a, b):
        assert client.get(f"/items/{item['id']}",
                          headers=who).json()["reporter"]["contact_email"] is None

    # The reporter can now approve the other claim instead.
    assert _decide(client, cb["id"], owner, True).status_code == 200
    assert _statuses(client, item["id"], owner)[ca["id"]] == "rejected"


def test_closing_keeps_auto_rejected_claims_rejected(client, auth_headers):
    owner, a, b = auth_headers(), auth_headers(), auth_headers()
    item = _mk_item(client, owner)
    ca, cb = _claim(client, item["id"], a), _claim(client, item["id"], b)
    _decide(client, ca["id"], owner, True)
    client.post(f"/items/{item['id']}/status", headers=owner, json={"to_status": "closed"})

    assert _statuses(client, item["id"], owner) == {ca["id"]: "approved", cb["id"]: "rejected"}


# --- relisting and approval need the right item state -----------------------

def _move(client, item_id, headers, to_status):
    return client.post(f"/items/{item_id}/status", headers=headers,
                       json={"to_status": to_status})


def test_relisting_is_refused_while_claims_are_pending(client, auth_headers):
    owner, a, b = auth_headers(), auth_headers(), auth_headers()
    item = _mk_item(client, owner)
    _claim(client, item["id"], a)
    _claim(client, item["id"], b)

    resp = _move(client, item["id"], owner, "reported")
    assert resp.status_code == 409, resp.text
    assert "2 pending claim(s)" in resp.json()["detail"]
    body = _item(client, item["id"])
    assert body["status"] == "matched"
    assert body["status_events"][-1]["to_status"] == "matched"  # nothing recorded


def test_an_admin_cannot_relist_over_pending_claims_either(client, auth_headers):
    from app.db.session import SessionLocal
    from app.repositories.user_repo import UserRepository

    owner, a, admin = auth_headers(), auth_headers(), auth_headers()
    admin_id = client.get("/auth/me", headers=admin).json()["id"]
    with SessionLocal() as db:
        repo = UserRepository(db)
        repo.set_admin(repo.get(admin_id), True)
        db.commit()

    item = _mk_item(client, owner)
    _claim(client, item["id"], a)
    assert _move(client, item["id"], admin, "reported").status_code == 409


def test_relisting_without_pending_claims_is_allowed(client, auth_headers):
    owner = auth_headers()
    item = _mk_item(client, owner)
    assert _move(client, item["id"], owner, "matched").status_code == 200
    resp = _move(client, item["id"], owner, "reported")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "reported"


def test_a_claim_on_a_reported_item_cannot_be_approved(client, auth_headers):
    """Unreachable through the API now, but rows from before these rules can
    still be in this state; approving one must not disclose contact details."""
    from sqlalchemy import text

    from app.db.session import engine

    owner, a = auth_headers(), auth_headers()
    item = _mk_item(client, owner)
    ca = _claim(client, item["id"], a)
    with engine.begin() as conn:
        conn.execute(text("UPDATE items SET status = 'reported' WHERE id = :id"),
                     {"id": item["id"]})

    resp = _decide(client, ca["id"], owner, True)
    assert resp.status_code == 409, resp.text
    assert "only be approved while the item is 'matched'" in resp.json()["detail"]
    assert "'reported'" in resp.json()["detail"]
    assert _statuses(client, item["id"], owner) == {ca["id"]: "pending"}
    assert client.get(f"/items/{item['id']}",
                      headers=a).json()["reporter"]["contact_email"] is None


def test_a_claim_on_a_claimed_item_without_an_approval_cannot_be_approved(client, auth_headers):
    """The reporter walked the item to 'claimed' by hand, with no claim at all;
    a claim filed afterwards cannot be approved into it."""
    owner, late = auth_headers(), auth_headers()
    item = _mk_item(client, owner)
    for state in ("matched", "claimed"):
        assert _move(client, item["id"], owner, state).status_code == 200
    cl = _claim(client, item["id"], late)

    resp = _decide(client, cl["id"], owner, True)
    assert resp.status_code == 409, resp.text
    assert "it is 'claimed'" in resp.json()["detail"]
    # Rejecting it is still fine.
    assert _decide(client, cl["id"], owner, False).status_code == 200
