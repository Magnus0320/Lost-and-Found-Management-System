"""Contact disclosure, and keeping an item and its claim in step.

Two rules are under test:

* An address is visible only to the other party of an *approved* claim. Names
  are public; contact details are not.
* Moving an item back out of `claimed` withdraws the approval that put it
  there, which reopens the claim and takes the disclosure away with it.
"""
import uuid


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


def _me(client, headers):
    return client.get("/auth/me", headers=headers).json()


def _claim(client, item_id, headers, evidence="serial number matches"):
    resp = client.post(f"/items/{item_id}/claims", headers=headers,
                       json={"evidence": evidence})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _claims_on(client, item_id, headers):
    resp = client.get("/claims", headers=headers, params={"item_id": item_id})
    assert resp.status_code == 200, resp.text
    return resp.json()["results"]


# --- disclosure -----------------------------------------------------------

def test_anonymous_reader_never_sees_the_reporter_address(client, auth_headers):
    owner = auth_headers()
    item = _mk_item(client, owner)
    reporter = client.get(f"/items/{item['id']}").json()["reporter"]
    assert reporter["contact_email"] is None
    # The narrowed schema must not carry the other identifying fields either.
    assert "email" not in reporter and "roll_number" not in reporter


def test_search_results_never_carry_contact_details(client, auth_headers):
    owner = auth_headers()
    _mk_item(client, owner)
    for row in client.get("/items", params={"limit": 100}).json()["results"]:
        assert row["reporter"]["contact_email"] is None


def test_unrelated_user_sees_no_contact_details(client, auth_headers):
    owner, bystander = auth_headers(), auth_headers()
    item = _mk_item(client, owner)
    body = client.get(f"/items/{item['id']}", headers=bystander).json()
    assert body["reporter"]["contact_email"] is None


def test_a_pending_claim_discloses_nothing(client, auth_headers):
    owner, claimant = auth_headers(), auth_headers()
    item = _mk_item(client, owner)
    _claim(client, item["id"], claimant)

    assert client.get(f"/items/{item['id']}",
                      headers=claimant).json()["reporter"]["contact_email"] is None
    row = _claims_on(client, item["id"], owner)[0]
    assert row["claimant"]["contact_email"] is None
    assert row["reporter"]["contact_email"] is None


def test_approval_discloses_both_addresses_to_both_parties(client, auth_headers):
    owner, claimant = auth_headers(), auth_headers()
    owner_email = _me(client, owner)["email"]
    claimant_email = _me(client, claimant)["email"]

    item = _mk_item(client, owner)
    claim = _claim(client, item["id"], claimant)
    decision = client.post(f"/claims/{claim['id']}/decision", headers=owner,
                           json={"approve": True})
    assert decision.status_code == 200, decision.text

    # The reporter, deciding, is handed the claimant's address straight back.
    assert decision.json()["claimant"]["contact_email"] == claimant_email

    # The claimant sees the reporter on the item page...
    body = client.get(f"/items/{item['id']}", headers=claimant).json()
    assert body["reporter"]["contact_email"] == owner_email

    # ...and on their own claim, without a second request for the item.
    mine = client.get("/claims", headers=claimant,
                      params={"mine_only": True}).json()["results"]
    row = next(c for c in mine if c["id"] == claim["id"])
    assert row["reporter"]["contact_email"] == owner_email
    assert row["item_name"] == item["name"]

    # A third party still sees nothing.
    bystander = auth_headers()
    assert client.get(f"/items/{item['id']}",
                      headers=bystander).json()["reporter"]["contact_email"] is None


def test_a_rejected_claim_discloses_nothing(client, auth_headers):
    owner, claimant = auth_headers(), auth_headers()
    item = _mk_item(client, owner)
    claim = _claim(client, item["id"], claimant)
    client.post(f"/claims/{claim['id']}/decision", headers=owner,
                json={"approve": False})

    assert client.get(f"/items/{item['id']}",
                      headers=claimant).json()["reporter"]["contact_email"] is None


# --- item and claim stay in step -----------------------------------------

def test_moving_back_out_of_claimed_reopens_the_claim(client, auth_headers):
    owner, claimant = auth_headers(), auth_headers()
    item = _mk_item(client, owner)
    claim = _claim(client, item["id"], claimant)
    client.post(f"/claims/{claim['id']}/decision", headers=owner,
                json={"approve": True})
    assert _claims_on(client, item["id"], owner)[0]["status"] == "approved"

    resp = client.post(f"/items/{item['id']}/status", headers=owner,
                       json={"to_status": "matched"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "matched"

    reopened = _claims_on(client, item["id"], owner)[0]
    assert reopened["status"] == "pending"
    assert reopened["decided_at"] is None


def test_a_reopened_claim_can_be_decided_again(client, auth_headers):
    owner, claimant = auth_headers(), auth_headers()
    item = _mk_item(client, owner)
    claim = _claim(client, item["id"], claimant)
    client.post(f"/claims/{claim['id']}/decision", headers=owner,
                json={"approve": True})
    client.post(f"/items/{item['id']}/status", headers=owner,
                json={"to_status": "matched"})

    # Before the fix this returned 409 "Claim already approved." and the item
    # was stuck: matched, with a claim that could never be decided again.
    again = client.post(f"/claims/{claim['id']}/decision", headers=owner,
                        json={"approve": False})
    assert again.status_code == 200, again.text
    assert again.json()["status"] == "rejected"


def test_reopening_withdraws_the_disclosure(client, auth_headers):
    owner, claimant = auth_headers(), auth_headers()
    item = _mk_item(client, owner)
    claim = _claim(client, item["id"], claimant)
    client.post(f"/claims/{claim['id']}/decision", headers=owner,
                json={"approve": True})
    assert client.get(f"/items/{item['id']}",
                      headers=claimant).json()["reporter"]["contact_email"] is not None

    client.post(f"/items/{item['id']}/status", headers=owner,
                json={"to_status": "matched"})
    assert client.get(f"/items/{item['id']}",
                      headers=claimant).json()["reporter"]["contact_email"] is None


def test_reopening_is_recorded_in_the_history(client, auth_headers):
    owner, claimant = auth_headers(), auth_headers()
    item = _mk_item(client, owner)
    claim = _claim(client, item["id"], claimant)
    client.post(f"/claims/{claim['id']}/decision", headers=owner,
                json={"approve": True})
    body = client.post(f"/items/{item['id']}/status", headers=owner,
                       json={"to_status": "matched"}).json()

    last = body["status_events"][-1]
    assert (last["from_status"], last["to_status"]) == ("claimed", "matched")
    assert "reopened" in (last["note"] or "")


def test_reopening_notifies_the_claimant(client, auth_headers):
    owner, claimant = auth_headers(), auth_headers()
    item = _mk_item(client, owner)
    claim = _claim(client, item["id"], claimant)
    client.post(f"/claims/{claim['id']}/decision", headers=owner,
                json={"approve": True})
    client.post(f"/items/{item['id']}/status", headers=owner,
                json={"to_status": "matched"})

    messages = [n["message"] for n in
                client.get("/notifications", headers=claimant).json()["results"]]
    assert any("withdrawn" in m for m in messages), messages


def test_closing_a_claimed_item_leaves_the_claim_approved(client, auth_headers):
    """Closing is the successful end of the handover, not a reversal."""
    owner, claimant = auth_headers(), auth_headers()
    item = _mk_item(client, owner)
    claim = _claim(client, item["id"], claimant)
    client.post(f"/claims/{claim['id']}/decision", headers=owner,
                json={"approve": True})
    client.post(f"/items/{item['id']}/status", headers=owner,
                json={"to_status": "closed"})

    assert _claims_on(client, item["id"], owner)[0]["status"] == "approved"


def test_an_explicit_note_survives_a_reopening(client, auth_headers):
    owner, claimant = auth_headers(), auth_headers()
    item = _mk_item(client, owner)
    claim = _claim(client, item["id"], claimant)
    client.post(f"/claims/{claim['id']}/decision", headers=owner,
                json={"approve": True})
    body = client.post(f"/items/{item['id']}/status", headers=owner,
                       json={"to_status": "matched",
                             "note": "Collector never showed up."}).json()

    assert body["status_events"][-1]["note"] == "Collector never showed up."


# --- who may read a claim at all ------------------------------------------

def test_a_stranger_cannot_read_claims_on_someone_elses_item(client, auth_headers):
    """The evidence field holds serial numbers and receipts."""
    owner, claimant, stranger = auth_headers(), auth_headers(), auth_headers()
    item = _mk_item(client, owner)
    _claim(client, item["id"], claimant, evidence="passport number X1234")

    resp = client.get("/claims", headers=stranger, params={"item_id": item["id"]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0 and body["results"] == []


def test_both_parties_can_read_the_claim(client, auth_headers):
    owner, claimant = auth_headers(), auth_headers()
    item = _mk_item(client, owner)
    claim = _claim(client, item["id"], claimant)

    for who in (owner, claimant):
        ids = [c["id"] for c in _claims_on(client, item["id"], who)]
        assert ids == [claim["id"]]


def test_one_claimant_cannot_read_another_claimants_claim(client, auth_headers):
    owner, first, second = auth_headers(), auth_headers(), auth_headers()
    item = _mk_item(client, owner)
    mine = _claim(client, item["id"], first, evidence="mine, engraved")
    _claim(client, item["id"], second, evidence="no, mine")

    # Two claims exist on the item; each claimant sees only their own.
    assert len(_claims_on(client, item["id"], owner)) == 2
    visible = _claims_on(client, item["id"], first)
    assert [c["id"] for c in visible] == [mine["id"]]
    assert "no, mine" not in visible[0]["evidence"]


def test_the_unscoped_list_covers_both_directions(client, auth_headers):
    """No filter at all still means "claims I am a party to", not everything."""
    owner, claimant, stranger = auth_headers(), auth_headers(), auth_headers()
    item = _mk_item(client, owner)
    claim = _claim(client, item["id"], claimant)
    # A claim the stranger is wholly uninvolved in must not appear for them.
    assert claim["id"] not in [
        c["id"] for c in client.get("/claims", headers=stranger,
                                    params={"limit": 100}).json()["results"]
    ]
    for who in (owner, claimant):
        assert claim["id"] in [
            c["id"] for c in client.get("/claims", headers=who,
                                        params={"limit": 100}).json()["results"]
        ]


def test_mine_only_still_narrows_to_claims_i_filed(client, auth_headers):
    owner, claimant = auth_headers(), auth_headers()
    item = _mk_item(client, owner)
    claim = _claim(client, item["id"], claimant)

    # The reporter is a party to it, but did not file it.
    assert claim["id"] not in [
        c["id"] for c in client.get("/claims", headers=owner,
                                    params={"mine_only": True, "limit": 100}).json()["results"]
    ]
    assert claim["id"] in [
        c["id"] for c in client.get("/claims", headers=claimant,
                                    params={"mine_only": True, "limit": 100}).json()["results"]
    ]
